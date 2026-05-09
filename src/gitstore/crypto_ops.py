from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Any

from .config import GitStoreConfig

PathInput = str | Path


@dataclass(frozen=True)
class EncryptionResult:
    encrypted_text: str
    artifact_hash: str
    content_hash: str
    timestamp: str


@dataclass(frozen=True)
class PreparedDirectory:
    path: Path
    crypto_input: Any
    content_hash: str


def _crypto():
    try:
        from utilitz import crypto as utilitz_crypto
    except ImportError as exc:
        raise ImportError(
            "utilitz with crypto extras is required. Install with: pip install 'utilitz[crypto]'"
        ) from exc
    return utilitz_crypto


def _timestamp(value: Any) -> str:
    if hasattr(value, "astimezone"):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def encrypt_directory(
    local_dir: PathInput,
    config: GitStoreConfig,
    *,
    include_patterns: str | list[str] | tuple[str, ...] | None = None,
    exclude_patterns: str | list[str] | tuple[str, ...] | None = None,
    encryption_params: dict[str, Any] | None = None,
) -> EncryptionResult:
    prepared = prepare_directory_input(
        local_dir,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )
    return encrypt_prepared_directory(
        prepared,
        config,
        encryption_params=encryption_params,
    )


def prepare_directory_input(
    local_dir: PathInput,
    *,
    include_patterns: str | list[str] | tuple[str, ...] | None = None,
    exclude_patterns: str | list[str] | tuple[str, ...] | None = None,
) -> PreparedDirectory:
    path = Path(local_dir).expanduser().resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Input directory not found: {path}")

    crypto = _crypto()
    crypto_input = crypto.CryptoInput.from_directory(
        str(path),
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )
    return PreparedDirectory(
        path=path,
        crypto_input=crypto_input,
        content_hash=crypto_input.content_hash,
    )


def encrypt_prepared_directory(
    prepared: PreparedDirectory,
    config: GitStoreConfig,
    *,
    encryption_params: dict[str, Any] | None = None,
) -> EncryptionResult:
    crypto = _crypto()
    encryptor = crypto.Encryptor(prepared.crypto_input).encrypt(
        config.password,
        **(encryption_params or {}),
    )
    output = encryptor.output
    if output is None:
        raise ValueError("Encryption did not produce an output.")

    return EncryptionResult(
        encrypted_text=output.to_string(encoding="utf-8"),
        artifact_hash=output.content_hash,
        content_hash=prepared.content_hash,
        timestamp=_timestamp(output.created_at),
    )


def decrypt_directory(
    encrypted_text: str,
    config: GitStoreConfig,
    local_dir: PathInput | None = None,
    *,
    overwrite: bool = False,
) -> str:
    decryptor = _crypto().Decryptor.from_string(encrypted_text, encoding="utf-8")
    decryptor.decrypt(config.password)
    return decryptor.to_directory(
        local_dir,
        exact_path=True,
        create_parent=True,
        overwrite=overwrite,
    )
