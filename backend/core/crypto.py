"""
Encryption / decryption utilities using Fernet (AES-128-CBC + HMAC).

On first run a random key is generated and saved to ``<DATA_DIR>/secret.key``.
Subsequent runs re-use the same key so existing data remains decryptable.

IMPORTANT: Protect ``secret.key`` — anyone who has it can decrypt the stored
credentials.  In production, consider using a proper secrets manager (e.g.
HashiCorp Vault, AWS Secrets Manager).
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet

_fernet: Fernet | None = None
_key_path: Path | None = None


def init_crypto(data_dir: str | Path) -> None:
    """
    Initialise the module-level Fernet cipher.

    * If ``ENCRYPTION_KEY`` environment variable is set, uses it (Enterprise mode).
    * If ``<data_dir>/secret.key`` exists, loads the key from it.
    * Otherwise generates a new key and writes it to that file.
    """
    global _fernet, _key_path

    # Phase 1: External Secrets Management
    from backend.core.config import Config

    if Config.ENCRYPTION_KEY:
        _fernet = Fernet(Config.ENCRYPTION_KEY.encode("ascii"))
        return

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    _key_path = data_dir / "secret.key"

    if _key_path.exists():
        key = _key_path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        # Write with restrictive permissions (owner-only on Unix; best-effort
        # on Windows).
        _key_path.write_bytes(key)
        try:
            os.chmod(_key_path, 0o600)
        except OSError:
            pass  # Windows may not support chmod

    _fernet = Fernet(key)


def _get_fernet() -> Fernet:
    if _fernet is None:
        raise RuntimeError("Crypto not initialised — call init_crypto(data_dir) first.")
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string → URL-safe base64 token (str)."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a token produced by ``encrypt()`` → original plaintext."""
    return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
