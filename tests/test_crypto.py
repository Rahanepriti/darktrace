import pytest

from app.crypto import encrypt_message, decrypt_message


def test_encryption_round_trip():
    message = "hello darktrace"

    encrypted = encrypt_message(message)
    decrypted = decrypt_message(encrypted)

    assert decrypted == message


def test_same_message_produces_different_ciphertext():
    message = "hello darktrace"

    encrypted_1 = encrypt_message(message)
    encrypted_2 = encrypt_message(message)

    assert encrypted_1 != encrypted_2


def test_tampered_message_is_rejected():
    message = "hello darktrace"

    encrypted = encrypt_message(message)

    tampered = encrypted[:-2] + "XX"

    with pytest.raises(ValueError, match="Message decryption or authentication failed"):
        decrypt_message(tampered)
