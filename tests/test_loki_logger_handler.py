import queue
import unittest
from unittest.mock import patch, MagicMock
import logging
from loki_logger_handler.formatters.plain_formatter import PlainFormatter
from loki_logger_handler.loki_client import LokiClient
from loki_logger_handler.loki_logger_handler import LokiLoggerHandler, BufferEntry
from loki_logger_handler.models import Stream, LokiRequest, LogEntry

class TestLokiLoggerHandler(unittest.TestCase):

    def setUp(self):
        self.url = "http://loki.example.com"
        self.labels = {"app": "test_app", "environment": "testing"}
        self.auth = ("test_user_id", "test_api_key")
        self.handler = LokiLoggerHandler(self.url, self.labels, auth=self.auth)

    def test_init(self):
        self.assertEqual(self.handler.labels, self.labels)
        self.assertEqual(self.handler.timeout, 10)
        self.assertIsInstance(self.handler.logger_formatter, PlainFormatter)
        self.assertIsInstance(self.handler.loki_client, LokiClient)
        self.assertIsInstance(self.handler.buffer, queue.Queue)

    @patch('loki_logger_handler.loki_logger_handler.BufferEntry')
    def test_emit(self, mock_buffer_entry):
        record = MagicMock(spec=logging.LogRecord)
        record.created = 1234567890.0
        record.levelname = "INFO"
        record.getMessage.return_value = "Test message"

        with patch.object(self.handler.buffer, 'put') as mock_put:
            self.handler.emit(record)

            mock_buffer_entry.assert_called_once_with(1234567890.0, "INFO", "Test message")
            mock_put.assert_called_once()

    @patch('loki_logger_handler.loki_logger_handler.LokiClient.send')
    def test_flush(self, mock_send):
        # Add some test entries to the buffer
        self.handler.buffer.put(BufferEntry(1234567890.0, "INFO", "Test message 1"))
        self.handler.buffer.put(BufferEntry(1234567891.0, "ERROR", "Test message 2"))

        self.handler.flush()

        # Check if LokiClient.send was called with the correct LokiRequest
        mock_send.assert_called_once()
        request_arg = mock_send.call_args[0][0]
        self.assertIsInstance(request_arg, LokiRequest)
        
        # Verify the contents of the LokiRequest
        streams = request_arg.streams
        self.assertEqual(len(streams), 2)  # One for INFO, one for ERROR
        
        info_stream = next(s for s in streams if s.labels['level'] == 'INFO')
        error_stream = next(s for s in streams if s.labels['level'] == 'ERROR')
        
        self.assertEqual(info_stream.labels, {"level": "INFO", "app": "test_app", "environment": "testing"})
        self.assertEqual(error_stream.labels, {"level": "ERROR", "app": "test_app", "environment": "testing"})
        
        self.assertEqual(len(info_stream.values), 1)
        self.assertEqual(len(error_stream.values), 1)
        
        self.assertEqual(info_stream.values[0].message, "Test message 1")
        self.assertEqual(error_stream.values[0].message, "Test message 2")

        expected_serialized = (
            '{"streams": ['
            '{"stream": {"level": "INFO", "app": "test_app", "environment": "testing"}, '
            '"values": [["1234567890000000000", "Test message 1"]]}, '
            '{"stream": {"level": "ERROR", "app": "test_app", "environment": "testing"}, '
            '"values": [["1234567891000000000", "Test message 2"]]}'
            ']}'
        )
        self.assertEqual(request_arg.serialize(), expected_serialized)

    def test_flush_empty_buffer(self):
        with patch('loki_logger_handler.loki_logger_handler.LokiClient.send') as mock_send:
            self.handler.flush()
            mock_send.assert_not_called()

    def test_init_with_auth(self):
        handler = LokiLoggerHandler(self.url, self.labels, auth=self.auth)
        self.assertEqual(handler.loki_client.headers["Authorization"], f"Bearer {self.auth[0]}:{self.auth[1]}")

    def test_init_without_auth(self):
        handler = LokiLoggerHandler(self.url, self.labels)
        self.assertNotIn("Authorization", handler.loki_client.headers)

if __name__ == '__main__':
    unittest.main()
