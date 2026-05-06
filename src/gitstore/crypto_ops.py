from pathlib import Path

from .config import GitStoreConfig


def _crypto():
    try:
        from utilitz import crypto as utilitz_crypto
    except ImportError as exc:
        raise ImportError(
            "utilitz with crypto extras is required. Install with: pip install 'utilitz[crypto]'"
        ) from exc
    return utilitz_crypto


def _resolve_security(security_level: str):
    crypto = _crypto()
    level = (security_level or "standard").strip().lower()
    if level == "standard":
        return crypto.SECURITY_STANDARD
    if level == "high":
        return crypto.SECURITY_HIGH
    if level == "paranoid":
        return crypto.SECURITY_PARANOID
    raise ValueError("security_level must be 'standard', 'high', or 'paranoid'.")


def encrypt_file(
    source_path: str,
    config: GitStoreConfig,
    output_path: str | None = None,
    security_level: str = "high",
) -> str:
    path = Path(source_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    return _crypto().encrypt_file(
        file_path=str(path),
        password=config.password,
        output_path=output_path,
        security=_resolve_security(security_level),
    )


def encrypt_directory(
    source_directory: str,
    config: GitStoreConfig,
    output_path: str | None = None,
    security_level: str = "high",
) -> str:
    path = Path(source_directory).expanduser().resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Input directory not found: {path}")
    return _crypto().encrypt_directory(
        directory_path=str(path),
        password=config.password,
        output_path=output_path,
        security=_resolve_security(security_level),
    )


def decrypt_file(
    encrypted_path: str,
    config: GitStoreConfig,
    output_path: str | None = None,
    overwrite: bool = False,
) -> str:
    path = Path(encrypted_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Encrypted file not found: {path}")
    return _crypto().decrypt_file(
        encrypted_file=str(path),
        password=config.password,
        output_path=output_path,
        overwrite=overwrite,
    )


def decrypt_directory(
    encrypted_path: str,
    config: GitStoreConfig,
    output_path: str | None = None,
    overwrite: bool = False,
) -> str:
    path = Path(encrypted_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Encrypted file not found: {path}")
    return _crypto().decrypt_directory(
        encrypted_file=str(path),
        password=config.password,
        output_path=output_path,
        overwrite=overwrite,
    )


def decrypt_auto(
    encrypted_path: str,
    config: GitStoreConfig,
    output_path: str | None = None,
    overwrite: bool = False,
) -> str:
    try:
        return decrypt_file(
            encrypted_path=encrypted_path,
            config=config,
            output_path=output_path,
            overwrite=overwrite,
        )
    except ValueError as exc:
        if "directory archive" not in str(exc):
            raise
    return decrypt_directory(
        encrypted_path=encrypted_path,
        config=config,
        output_path=output_path,
        overwrite=overwrite,
    )
