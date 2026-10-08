"""
Secrets Manager — Security Layer

Handles secure storage and retrieval of secrets (API keys, tokens,
credentials) used by CLI agents. Secrets are never stored in plaintext.
Environment variables are the preferred runtime injection method.
"""

import os
import json
import base64
import hashlib
import secrets
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class SecretMetadata:
    """Metadata record for a stored secret (never contains the actual value)."""
    key: str
    hint: str          # Last 4 chars of the value for identification
    created_at: str
    last_accessed: Optional[str] = None
    scope: str = "global"  # global | project | session


class SecretsManager:
    """
    Manages secrets for the CLIVERSE environment.

    SECURITY PRINCIPLES:
    - Secrets are never logged or included in audit events as plaintext.
    - In-memory storage is cleared on process exit.
    - For production use, integrate with OS keychain or HashiCorp Vault.
    - The metadata index never contains actual secret values.

    Usage:
        sm = SecretsManager(storage_path=".envcore/secrets")
        sm.store("OPENAI_API_KEY", "sk-...", scope="global")
        key = sm.get("OPENAI_API_KEY")
    """

    SENSITIVE_PATTERNS = [
        "KEY", "SECRET", "PASSWORD", "TOKEN", "PASS",
        "CREDENTIAL", "AUTH", "PRIVATE", "ACCESS",
    ]

    def __init__(self, storage_path: str = ".envcore/secrets"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        # In-memory store — not persisted to disk in plaintext
        self._vault: dict[str, str] = {}
        self._metadata: dict[str, SecretMetadata] = {}
        self._load_from_env()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def store(self, key: str, value: str, scope: str = "global") -> bool:
        """
        Store a secret in the in-memory vault.
        Metadata (without value) is persisted to disk.
        """
        from datetime import datetime, timezone
        self._vault[key] = value
        hint = f"...{value[-4:]}" if len(value) >= 4 else "****"
        meta = SecretMetadata(
            key=key,
            hint=hint,
            created_at=datetime.now(timezone.utc).isoformat(),
            scope=scope,
        )
        self._metadata[key] = meta
        self._persist_metadata()
        return True

    def get(self, key: str) -> Optional[str]:
        """Retrieve a secret. Updates last_accessed timestamp."""
        from datetime import datetime, timezone
        # Check in-memory vault first
        if key in self._vault:
            if key in self._metadata:
                self._metadata[key].last_accessed = datetime.now(timezone.utc).isoformat()
                self._persist_metadata()
            return self._vault[key]
        # Fall back to environment variable
        return os.environ.get(key)

    def delete(self, key: str) -> bool:
        """Remove a secret from vault and metadata."""
        removed = False
        if key in self._vault:
            del self._vault[key]
            removed = True
        if key in self._metadata:
            del self._metadata[key]
            self._persist_metadata()
            removed = True
        return removed

    def exists(self, key: str) -> bool:
        """Check if a secret exists (vault or environment)."""
        return key in self._vault or os.environ.get(key) is not None

    def list_keys(self) -> list[SecretMetadata]:
        """Return metadata for all known secrets (no values exposed)."""
        return list(self._metadata.values())

    def is_sensitive_key(self, key: str) -> bool:
        """Detect if a key name suggests it holds a sensitive value."""
        key_upper = key.upper()
        return any(pattern in key_upper for pattern in self.SENSITIVE_PATTERNS)

    def redact(self, text: str) -> str:
        """
        Scan text and redact any known secret values.
        Used by the audit logger to sanitize output.
        """
        for secret_value in self._vault.values():
            if secret_value and len(secret_value) > 4:
                text = text.replace(secret_value, "[REDACTED]")
        return text

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _load_from_env(self) -> None:
        """Pre-register env vars that look like secrets into metadata (not vault)."""
        from datetime import datetime, timezone
        for key, value in os.environ.items():
            if self.is_sensitive_key(key):
                hint = f"...{value[-4:]}" if len(value) >= 4 else "****"
                self._metadata[key] = SecretMetadata(
                    key=key,
                    hint=hint,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    scope="environment",
                )

    def _persist_metadata(self) -> None:
        """Save secret metadata (no values) to disk for inspection."""
        meta_file = self.storage_path / "secrets_metadata.json"
        data = {k: vars(v) for k, v in self._metadata.items()}
        meta_file.write_text(json.dumps(data, indent=2))
