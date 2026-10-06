import base64

import pytest

from app.crypto.aes_gcm import (CryptoError, CryptoService, KeyRing, NONCE_SIZE, decode_key, decrypt,
                                encode_key, encrypt, generate_key)
from tests.conftest import StaticKeyProvider, random_key


def ring(version=1, key=None):
    return KeyRing({version: key or random_key()}, version)


def test_roundtrip():
    r = ring()
    token = encrypt(r, b'{"hello":"world"}')
    d = decrypt(r, token)
    assert d.plaintext == b'{"hello":"world"}' and d.key_version == 1


def test_wrong_key_rejected():
    token = encrypt(ring(), b"secret")
    with pytest.raises(CryptoError):
        decrypt(ring(), token)


def test_tampered_ciphertext_rejected():
    r = ring()
    raw = bytearray(base64.urlsafe_b64decode(encrypt(r, b"payload") + "=="))
    for idx in (2, 2 + NONCE_SIZE + 1, len(raw) - 1):  # nonce, ciphertext, tag
        bad = bytearray(raw)
        bad[idx] ^= 0x01
        with pytest.raises(CryptoError):
            decrypt(r, base64.urlsafe_b64encode(bytes(bad)).decode())


def test_tampered_key_version_header_rejected():
    r = KeyRing({1: random_key(), 2: random_key()}, 1)
    raw = bytearray(base64.urlsafe_b64decode(encrypt(r, b"x") + "=="))
    raw[1] = 2  # claim a different key version
    with pytest.raises(CryptoError):
        decrypt(r, base64.urlsafe_b64encode(bytes(raw)).decode())


def test_unique_nonce_per_message():
    r = ring()
    nonces = {decrypt(r, encrypt(r, b"same")).nonce for _ in range(500)}
    assert len(nonces) == 500
    assert encrypt(r, b"same") != encrypt(r, b"same")


@pytest.mark.parametrize("bad", ["", "!!!notbase64!!!", "AAAA", "A" * 10, "short"])
def test_invalid_ciphertext(bad):
    with pytest.raises(CryptoError):
        decrypt(ring(), bad)


def test_unknown_key_version_rejected():
    token = encrypt(ring(version=7), b"x")
    with pytest.raises(CryptoError):
        decrypt(ring(version=1), token)


def test_key_must_be_256_bits():
    with pytest.raises(CryptoError):
        KeyRing({1: b"x" * 16}, 1)
    with pytest.raises(CryptoError):
        decode_key("CHANGE_ME")
    k = generate_key()
    assert decode_key(encode_key(k)) == k
    assert decode_key(k.hex()) == k
    assert decode_key(base64.urlsafe_b64encode(k).decode().rstrip("=")) == k  # unpadded base64url


def test_repr_never_leaks_key():
    k = random_key()
    assert encode_key(k) not in repr(KeyRing({1: k}, 1)) and k.hex() not in repr(KeyRing({1: k}, 1))


def test_rotation_old_messages_still_decrypt_and_new_use_new_key():
    k1, k2 = random_key(), random_key()
    old = encrypt(KeyRing({1: k1}, 1), b"old")
    holder = {"ring": KeyRing({1: k1}, 1)}

    class P:
        def load(self):
            return holder["ring"]

    t = {"now": 0.0}
    svc = CryptoService(P(), refresh_seconds=10, clock=lambda: t["now"])
    assert svc.active_version == 1
    holder["ring"] = KeyRing({1: k1, 2: k2}, 2)  # operator rotates in the secret store
    t["now"] = 11  # next refresh
    assert svc.active_version == 2
    assert decrypt(holder["ring"], svc.encrypt(b"new")).key_version == 2
    assert svc.decrypt(old).plaintext == b"old"
