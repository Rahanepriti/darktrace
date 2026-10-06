"""
Quick standalone verification for crypto_utils.py before building anything on top of it. 
Run with: python tests/test_crypto_utils.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crypto_utils import encrypt, decrypt, generate_key, DecryptionError


def test_round_trip():
    key = generate_key()
    plaintext = b'{"crawler_id": "c1", "status": "ok", "ts": 1234567890}'

    blob = encrypt(plaintext, key)
    result = decrypt(blob, key)

    assert result == plaintext, f"round trip mismatch: {result} != {plaintext}"
    print("[PASS] round trip: encrypt -> decrypt returns original plaintext")


def test_tampered_message_rejected():
    key = generate_key()
    plaintext = b"hello crawler"
    blob = encrypt(plaintext, key)

    # Flip one byte inside the ciphertext portion (past the 12-byte nonce).
    tampered = bytearray(blob)
    tampered[20] ^= 0xFF
    tampered = bytes(tampered)

    try:
        decrypt(tampered, key)
        raise AssertionError("tampered message was NOT rejected -- this must raise DecryptionError")
    except DecryptionError:
        print("[PASS] tampered message: decrypt() correctly raised DecryptionError")


def test_wrong_key_rejected():
    key_a = generate_key()
    key_b = generate_key()
    plaintext = b"hello crawler"
    blob = encrypt(plaintext, key_a)

    try:
        decrypt(blob, key_b)
        raise AssertionError("wrong key was NOT rejected -- this must raise DecryptionError")
    except DecryptionError:
        print("[PASS] wrong key: decrypt() correctly raised DecryptionError")


def test_nonce_is_random_each_call():
    key = generate_key()
    plaintext = b"same message twice"
    blob1 = encrypt(plaintext, key)
    blob2 = encrypt(plaintext, key)

    assert blob1 != blob2, "two encrypt() calls produced identical output -- nonce is not random!"
    print("[PASS] nonce randomness: two encrypt() calls of the same plaintext differ")


if __name__ == "__main__":
    test_round_trip()
    test_tampered_message_rejected()
    test_wrong_key_rejected()
    test_nonce_is_random_each_call()
    print("\nAll crypto_utils tests passed.")
