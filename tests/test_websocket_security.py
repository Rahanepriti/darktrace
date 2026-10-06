import json

import pytest

from app.crypto import encrypt_message, decrypt_message


def test_tampered_ciphertext_is_rejected():
    payload = {
        "worker_id": "cw-security-test",
        "status": "healthy",
        "timestamp": "2026-10-06T10:00:00Z",
        "queue_depth": 10,
        "last_successful_fetch": "2026-10-06T09:59:50Z",
    }

    encrypted = encrypt_message(json.dumps(payload))

    # Modify the encrypted message.
    tampered = encrypted[:-2] + "XX"

    with pytest.raises(
        ValueError,
        match="Message decryption or authentication failed",
    ):
        decrypt_message(tampered)
def test_wrong_key_message_is_rejected():
    import base64
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    payload = b'{"worker_id":"cw-wrong-key","status":"healthy"}'

    wrong_key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(wrong_key)

    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, payload, None)

    encrypted_message = base64.urlsafe_b64encode(
        nonce + ciphertext
    ).decode()

    with pytest.raises(
        ValueError,
        match="Message decryption or authentication failed",
    ):
        decrypt_message(encrypted_message)

def test_websocket_rejects_tampered_message_without_crashing():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with client.websocket_connect("/api/v1/ws/health") as websocket:
        websocket.send_text("this-is-not-valid-encrypted-data")

        # Send a valid encrypted heartbeat afterward.
        # If the WebSocket handler crashed, this second message
        # would not be processed.
        payload = {
            "worker_id": "cw-websocket-security",
            "status": "healthy",
            "timestamp": "2026-10-06T10:00:00Z",
            "queue_depth": 5,
            "last_successful_fetch": "2026-10-06T09:59:50Z",
        }

        websocket.send_text(
            encrypt_message(json.dumps(payload))
        )
