import pytest
from app.crypto_utils import encrypt_json, decrypt_json, EncryptionError

def test_encryption_round_trip():
    key = b"x" * 32
    message = b'{"worker_id":"cw-1"}'
    assert decrypt_json(encrypt_json(message, key), key) == message

def test_tampered_message_rejected():
    key = b"x" * 32
    token = encrypt_json(b"secret heartbeat", key)
    import base64
    raw = bytearray(base64.b64decode(token))
    raw[-1] ^= 1
    tampered = base64.b64encode(raw).decode()
    with pytest.raises(EncryptionError):
        decrypt_json(tampered, key)
