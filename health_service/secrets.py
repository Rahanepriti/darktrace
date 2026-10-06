from __future__ import annotations

import base64
import os
from typing import Optional, Protocol


class SecretProvider(Protocol):
    def get_key(self, version: str) -> Optional[bytes]: ...

    def get_active_version(self) -> str: ...


class EnvSecretProvider:
    def __init__(
        self,
        env_prefix: str,
        active_version_env: str,
        default_version: str,
    ) -> None:
        self._env_prefix = env_prefix
        self._active_version_env = active_version_env
        self._default_version = default_version

    def get_key(self, version: str) -> Optional[bytes]:
        raw = os.environ.get(f"{self._env_prefix}{version.upper()}")
        if raw is None:
            return None
        try:
            return base64.b64decode(raw)
        except (ValueError, TypeError):
            return None

    def get_active_version(self) -> str:
        return os.environ.get(self._active_version_env, self._default_version)


class VaultSecretProvider:
    def __init__(self, vault_client, mount_path: str, secret_name: str) -> None:
        self._vault_client = vault_client
        self._mount_path = mount_path
        self._secret_name = secret_name

    def get_key(self, version: str) -> Optional[bytes]:
        raise NotImplementedError(
            "Wire this to the organization's Vault-class secret store client "
            "(read versioned secret at mount_path/secret_name, decode base64 payload)"
        )

    def get_active_version(self) -> str:
        raise NotImplementedError(
            "Wire this to the organization's Vault-class secret store client "
            "(read the active-version metadata pointer for secret_name)"
        )


def build_key_resolver(provider: SecretProvider):
    def resolver(version: str) -> Optional[bytes]:
        return provider.get_key(version)

    return resolver
