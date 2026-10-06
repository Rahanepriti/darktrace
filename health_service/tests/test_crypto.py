import base64
import json

import pytest

from health_service.crypto import DecryptionError, InvalidKeyError, decrypt_message, encrypt_message


def test_round_trip_encrypt_decrypt(test_key, key_resolver):
    plaintext = b'{"worker_id": "cw-1", "status": "healthy"}'
    envelope = encrypt_message(plaintext, test_key, "v1")
    recovered = decrypt_message(envelope, key_resolver)
    assert recovered == plaintext


def test_each_message_uses_a_fresh_nonce(test_key):
    envelope_a = json.loads(encrypt_message(b"payload-a", test_key, "v1"))
    envelope_b = json.loads(encrypt_message(b"payload-a", test_key, "v1"))
    assert envelope_a["nonce"] != envelope_b["nonce"]


def test_tampered_ciphertext_is_rejected(test_key, key_resolver):
    envelope = json.loads(encrypt_message(b"authentic payload", test_key, "v1"))
    tampered_bytes = bytearray(base64.b64decode(envelope["ciphertext"]))
    tampered_bytes[0] ^= 0xFF
    envelope["ciphertext"] = base64.b64encode(bytes(tampered_bytes)).decode("ascii")

    with pytest.raises(DecryptionError):
        decrypt_message(json.dumps(envelope), key_resolver)


def test_wrong_key_rejects_message(test_key):
    import os

    envelope = encrypt_message(b"payload", test_key, "v1")
    wrong_key = os.urandom(32)

    def wrong_resolver(version: str):
        return wrong_key

    with pytest.raises(DecryptionError):
        decrypt_message(envelope, wrong_resolver)


def test_unknown_key_version_is_rejected(test_key):
    envelope = encrypt_message(b"payload", test_key, "v99")

    def resolver(version: str):
        return None

    with pytest.raises(DecryptionError):
        decrypt_message(envelope, resolver)


def test_malformed_envelope_is_rejected(key_resolver):
    with pytest.raises(DecryptionError):
        decrypt_message("not even json", key_resolver)


def test_wrong_key_size_is_rejected():
    with pytest.raises(InvalidKeyError):
        encrypt_message(b"payload", b"too-short", "v1")


def test_key_rotation_resolver_supports_multiple_versions():
    import os

    key_v1 = os.urandom(32)
    key_v2 = os.urandom(32)

    def resolver(version: str):
        return {"v1": key_v1, "v2": key_v2}.get(version)

    envelope_old = encrypt_message(b"from the old key", key_v1, "v1")
    envelope_new = encrypt_message(b"from the new key", key_v2, "v2")

    assert decrypt_message(envelope_old, resolver) == b"from the old key"
    assert decrypt_message(envelope_new, resolver) == b"from the new key"
