import unittest
from unittest.mock import Mock,patch
from alpha_demo import credentials

class CredentialStorageTests(unittest.TestCase):
    def test_save_load_forget_use_only_dedicated_vault_item(self):
        store=Mock();store.get_password.return_value='test-secret'
        with patch.object(credentials,'backend',return_value=store):
            credentials.save('test-secret');self.assertEqual(credentials.load(),'test-secret');credentials.forget()
        store.set_password.assert_called_once_with(credentials.SERVICE,credentials.ACCOUNT,'test-secret')
        store.delete_password.assert_called_once_with(credentials.SERVICE,credentials.ACCOUNT)
    def test_backend_error_never_repeats_secret(self):
        store=Mock();store.set_password.side_effect=RuntimeError('private-key')
        with patch.object(credentials,'backend',return_value=store):
            with self.assertRaises(ValueError) as error:credentials.save('private-key')
        self.assertNotIn('private-key',str(error.exception))
    def test_invalid_key_never_saved(self):
        with patch.object(credentials,'backend') as backend:
            with self.assertRaises(ValueError):credentials.save('bad\nkey')
            backend.assert_not_called()
