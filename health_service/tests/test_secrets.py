import base64
import os

from health_service.secrets import EnvSecretProvider, build_key_resolver


def test_env_secret_provider_reads_active_version(monkeypatch):
    monkeypatch.setenv("ACTIVE_AES_KEY_VERSION", "v3")
    provider = EnvSecretProvider("AES_KEY_", "ACTIVE_AES_KEY_VERSION", "v1")
    assert provider.get_active_version() == "v3"


def test_env_secret_provider_resolves_key_by_version(monkeypatch):
    raw_key = os.urandom(32)
    monkeypatch.setenv("AES_KEY_V7", base64.b64encode(raw_key).decode("ascii"))
    provider = EnvSecretProvider("AES_KEY_", "ACTIVE_AES_KEY_VERSION", "v1")
    assert provider.get_key("v7") == raw_key


def test_env_secret_provider_returns_none_for_missing_version():
    provider = EnvSecretProvider("AES_KEY_", "ACTIVE_AES_KEY_VERSION", "v1")
    assert provider.get_key("v404") is None


def test_build_key_resolver_delegates_to_provider(monkeypatch):
    raw_key = os.urandom(32)
    monkeypatch.setenv("AES_KEY_V1", base64.b64encode(raw_key).decode("ascii"))
    provider = EnvSecretProvider("AES_KEY_", "ACTIVE_AES_KEY_VERSION", "v1")
    resolver = build_key_resolver(provider)
    assert resolver("v1") == raw_key
