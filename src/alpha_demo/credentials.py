"""Gemini credentials in the OS Secret Service, never in project files."""
SERVICE='Alpha1S Studio'
ACCOUNT='Gemini API key'


def backend():
    try:
        # Explicit backend: never fall back to plaintext third-party keyrings.
        from keyring.backends.SecretService import Keyring
        store=Keyring()
        if store.priority<=0:raise RuntimeError()
        return store
    except Exception:
        raise ValueError('System password vault unavailable. Use a session key; nothing was saved.') from None


def load():
    try:return backend().get_password(SERVICE,ACCOUNT) or ''
    except Exception:raise ValueError('Could not unlock the password vault. Enter a session key instead.') from None


def save(key):
    if not isinstance(key,str) or not key.strip() or len(key)>512 or any(ord(c)<33 or ord(c)>126 for c in key.strip()):
        raise ValueError('Enter a valid Gemini API key first.')
    try:backend().set_password(SERVICE,ACCOUNT,key.strip())
    except Exception:raise ValueError('Could not save to the password vault. Your key remains session-only.') from None


def forget():
    try:
        store=backend()
        if store.get_password(SERVICE,ACCOUNT):store.delete_password(SERVICE,ACCOUNT)
    except Exception:raise ValueError('Could not remove the saved key. Unlock your password vault and try again.') from None
