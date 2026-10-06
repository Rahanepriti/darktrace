from __future__ import annotations

import base64
import os

_TEST_KEY = os.urandom(32)
os.environ.setdefault("AES_KEY_V1", base64.b64encode(_TEST_KEY).decode("ascii"))
os.environ.setdefault("ACTIVE_AES_KEY_VERSION", "v1")

import pytest


@pytest.fixture
def test_key() -> bytes:
    return _TEST_KEY


@pytest.fixture
def key_resolver(test_key: bytes):
    def resolver(version: str):
        if version == "v1":
            return test_key
        return None

    return resolver
