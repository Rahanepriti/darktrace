import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


NONCE_SIZE = 12
KEY_SIZE = 32


def _get_key() -> bytes:
    """
    Load the AES-256 key from configuration.

    AES-256 requires exactly 32 bytes.
    """
    key = base64.urlsafe_b64decode(
        settings.aes_secret_key + "=" * (-len(settings.aes_secret_key) % 4)
    )

    if len(key) != KEY_SIZE:
        raise ValueError("AES secret key must decode to exactly 32 bytes")

    return key


def encrypt_message(plaintext: str) -> str:
    """
    Encrypt a plaintext message using AES-256-GCM.

    A fresh 12-byte nonce is generated for every message.

    Returns:
        Base64-encoded nonce + ciphertext + authentication tag.
    """
    key = _get_key()

    # AESGCM.generate_key(96) is not appropriate for a nonce.
    # Generate the nonce using the cryptographically secure RNG instead.
    import os

    nonce = os.urandom(NONCE_SIZE)

    aesgcm = AESGCM(key)

    ciphertext = aesgcm.encrypt(
        nonce,
        plaintext.encode("utf-8"),
        None,
    )

    encrypted = nonce + ciphertext

    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_message(encrypted_message: str) -> str:
    """
    Decrypt and authenticate an AES-256-GCM encrypted message.

    Raises:
        ValueError: if the encrypted message is invalid or authentication fails.
    """
    key = _get_key()

    try:
        encrypted = base64.urlsafe_b64decode(encrypted_message)

        if len(encrypted) <= NONCE_SIZE:
            raise ValueError("Encrypted message is too short")

        nonce = encrypted[:NONCE_SIZE]
        ciphertext = encrypted[NONCE_SIZE:]

        aesgcm = AESGCM(key)

        plaintext = aesgcm.decrypt(
            nonce,
            ciphertext,
            None,
        )

        return plaintext.decode("utf-8")

    except Exception as exc:
        raise ValueError("Message decryption or authentication failed") from exc
