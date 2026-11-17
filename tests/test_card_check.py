import unittest
from unittest.mock import patch
from alpha_demo.card_check import check, classify, summarize_sector

class CardCheckTests(unittest.TestCase):
    def test_zero_is_not_upload_ready(self):
        with patch('alpha_demo.card_check.identify', return_value=(253952, 'robot')):
            result=check('/dev/mock', lambda d,s: {'sector':s, **summarize_sector(bytes(512))})
        self.assertEqual(result['status'], 'zero_data_returned')
        self.assertFalse(result['safe_to_upload'])
        self.assertEqual([s['sector'] for s in result['samples']], [0,2048,126976,253951])

    def test_stop_on_failed_read(self):
        with patch('alpha_demo.card_check.identify', return_value=(253952, 'robot')):
            result=check('/dev/mock', lambda d,s: {'sector':s, 'error':'timeout'})
        self.assertEqual(len(result['samples']), 1)
        self.assertEqual(result['status'], 'read_failed')

    def test_nonzero_not_proof_of_filesystem(self):
        self.assertEqual(classify([summarize_sector(b'X'+bytes(511))]), 'data_found_filesystem_not_yet_verified')

    def test_changed_device_not_read(self):
        with patch('alpha_demo.card_check.identify', side_effect=[(8,'robot'), (8,'other')]):
            with self.assertRaises(RuntimeError):
                check('/dev/mock', lambda *args:self.fail('Must not read changed disk'))

    def test_short_read_is_failure(self):
        self.assertEqual(classify([summarize_sector(bytes(20))]), 'read_failed')
