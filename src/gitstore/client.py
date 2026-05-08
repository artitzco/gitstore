import json
import os
import shutil
import tempfile
import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import GitStoreConfig
from .github_ops import (
    download_raw_file,
    download_raw_file_urllib,
    git_add_commit_push,
    normalize_github_file_url,
)
from .crypto_ops import decrypt_auto, encrypt_directory, encrypt_file

DEFAULT_PASSWORD_ENV_VAR = "GITSTORE_PASSWORD"
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_NAME_RULES_MESSAGE = (
    "name must be a simple identifier using only letters, numbers, dots, "
    "underscores, and hyphens. It must start with a letter or number and must "
    "not contain spaces or path separators."
)


@dataclass(frozen=True)
class StoredArtifact:
    name: str
    artifact: str
    artifact_hash: str
    source_hash: str
    is_directory: bool
    created_at_utc: str


def _resolve_password(password: str | None, password_env_var: str) -> str:
    resolved_password = password or os.getenv(password_env_var)
    if not resolved_password:
        raise ValueError(
            "Password was not provided and no environment variable was found. "
            f"Set '{password_env_var}' or pass password explicitly."
        )
    return resolved_password


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError(_NAME_RULES_MESSAGE)
    if name != name.strip():
        raise ValueError(_NAME_RULES_MESSAGE)
    if any(sep in name for sep in ("/", "\\")):
        raise ValueError(_NAME_RULES_MESSAGE)
    if not _VALID_NAME_RE.fullmatch(name):
        raise ValueError(_NAME_RULES_MESSAGE)
    return name


def _hash_from_name_or_content(encrypted_path: Path) -> str:
    # utilitz default output name pattern: -confidential-<24hex>.asc
    m = re.search(r"-confidential-([0-9a-fA-F]{24})", encrypted_path.name)
    if m:
        return m.group(1).lower()

    hasher = hashlib.sha256()
    with open(encrypted_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:24]


def _hmac_source(path: Path, secret: str) -> str:
    key = hashlib.sha256(secret.encode("utf-8")).digest()

    if path.is_file():
        mac = hmac.new(key, digestmod=hashlib.sha256)
        mac.update(b"F:")
        mac.update(path.name.encode("utf-8"))
        mac.update(b"\0")
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                mac.update(chunk)
        return mac.hexdigest()

    if not path.is_dir():
        raise FileNotFoundError(f"Input path not found: {path}")

    mac = hmac.new(key, digestmod=hashlib.sha256)
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = file_path.relative_to(path).as_posix()
        mac.update(b"F:")
        mac.update(rel.encode("utf-8"))
        mac.update(b"\0")
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                mac.update(chunk)
        mac.update(b"\n")
    return mac.hexdigest()


def restore_from_github(
    github_raw_url: str,
    password: str | None = None,
    output_path: str | None = None,
    overwrite: bool = False,
    force: bool = False,
    use_urllib: bool = False,
    request_timeout: int = 60,
    password_env_var: str = DEFAULT_PASSWORD_ENV_VAR,
) -> str:
    resolved_password = _resolve_password(password, password_env_var)
    config = GitStoreConfig(password=resolved_password, request_timeout=request_timeout)
    raw_url = normalize_github_file_url(github_raw_url)
    if output_path is not None and not overwrite and not force:
        existing_output = Path(output_path).expanduser().resolve()
        if existing_output.exists():
            remote_record = _load_remote_record_for_artifact(raw_url, request_timeout)
            remote_source_hash = str(remote_record.get("source_hash") or "").lower()
            if remote_source_hash and _hmac_source(existing_output, config.password).lower() == remote_source_hash:
                print(f"[gitstore] Skip download: '{raw_url}' already restored at '{existing_output}'.")
                return str(existing_output)

    temp_dir = Path(tempfile.mkdtemp(prefix="gitstore_restore_"))
    temp_file = temp_dir / "artifact.asc"
    cleanup_temp_dir = output_path is not None
    try:
        if use_urllib:
            download_raw_file_urllib(raw_url, str(temp_file), timeout=request_timeout)
        else:
            download_raw_file(raw_url, str(temp_file), timeout=request_timeout)
        restored_path = decrypt_auto(
            encrypted_path=str(temp_file),
            config=config,
            output_path=output_path,
            overwrite=overwrite,
        )
        print(f"[gitstore] Downloaded and restored '{raw_url}' -> '{restored_path}'.")
        return restored_path
    finally:
        temp_file.unlink(missing_ok=True)
        if cleanup_temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def restore_from_file(
    encrypted_file_path: str,
    password: str | None = None,
    output_path: str | None = None,
    overwrite: bool = False,
    password_env_var: str = DEFAULT_PASSWORD_ENV_VAR,
) -> str:
    resolved_password = _resolve_password(password, password_env_var)
    config = GitStoreConfig(password=resolved_password, request_timeout=60)
    encrypted_file = Path(encrypted_file_path).expanduser().resolve()
    if not encrypted_file.is_file():
        raise FileNotFoundError(f"Encrypted file not found: {encrypted_file}")
    restored_path = decrypt_auto(
        encrypted_path=str(encrypted_file),
        config=config,
        output_path=output_path,
        overwrite=overwrite,
    )
    print(f"[gitstore] Restored local artifact '{encrypted_file}' -> '{restored_path}'.")
    return restored_path


def _load_remote_record_for_artifact(raw_url: str, request_timeout: int) -> dict:
    manifest_url = raw_url.rsplit("/", 1)[0] + "/index.json"
    artifact_name = raw_url.rsplit("/", 1)[-1]
    temp_dir = Path(tempfile.mkdtemp(prefix="gitstore_manifest_"))
    temp_manifest = temp_dir / "index.json"
    try:
        try:
            download_raw_file(manifest_url, str(temp_manifest), timeout=request_timeout)
            with open(temp_manifest, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            return {}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if not isinstance(manifest, dict):
        return {}
    for record in manifest.values():
        if isinstance(record, dict) and record.get("artifact") == artifact_name:
            return record
    return {}


def upload_to_github(
    source_path: str,
    name: str,
    repo_path: str,
    password: str | None = None,
    vault_dir: str = "vault",
    request_timeout: int = 60,
    password_env_var: str = DEFAULT_PASSWORD_ENV_VAR,
    security_level: str = "high",
    commit_message: str | None = None,
    replace_existing: bool = True,
    force: bool = False,
) -> StoredArtifact:
    if not repo_path:
        raise ValueError("repo_path is required.")

    name = _validate_name(name)
    resolved_password = _resolve_password(password, password_env_var)
    config = GitStoreConfig(password=resolved_password, request_timeout=request_timeout)
    repo = Path(repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise FileNotFoundError(f"Not a git repository: {repo}")

    vault = vault_dir.strip().strip("/\\") or "vault"
    manifest_rel = f"{vault}/index.json"
    manifest_path = repo / manifest_rel

    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Input path not found: {source}")

    is_directory = source.is_dir()
    source_hash = _hmac_source(source, config.password)
    manifest = _load_manifest_local(manifest_path)
    existing_record = manifest.get(name)
    if existing_record:
        existing_source_hash = str(existing_record.get("source_hash", "")).lower()
        if existing_source_hash == source_hash.lower() and not force:
            print(
                f"[gitstore] Skip upload: '{name}' already up to date "
                f"(source_hash={source_hash[:24]})."
            )
            return StoredArtifact(
                name=name,
                artifact=str(existing_record["artifact"]),
                artifact_hash=str(existing_record.get("artifact_hash", "")),
                source_hash=existing_source_hash,
                is_directory=bool(existing_record["is_directory"]),
                created_at_utc=str(existing_record["created_at_utc"]),
            )
        if not replace_existing:
            raise ValueError(f"Name '{name}' already exists. Use replace_existing=True to replace it.")

    if is_directory:
        encrypted_path = Path(
            encrypt_directory(
                source_directory=str(source),
                config=config,
                security_level=security_level,
            )
        )
    else:
        encrypted_path = Path(
            encrypt_file(
                source_path=str(source),
                config=config,
                security_level=security_level,
            )
        )

    try:
        extension = "".join(encrypted_path.suffixes) or ".asc"
        artifact_hash = _hash_from_name_or_content(encrypted_path)
        artifact_filename = f"{name}{extension}"
        artifact_rel = f"{vault}/{artifact_filename}"
        artifact_abs = repo / artifact_rel
        artifact_abs.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(encrypted_path, artifact_abs)

        record = StoredArtifact(
            name=name,
            artifact=artifact_filename,
            artifact_hash=artifact_hash,
            source_hash=source_hash,
            is_directory=is_directory,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        manifest[name] = {
            "name": record.name,
            "artifact": record.artifact,
            "artifact_hash": record.artifact_hash,
            "source_hash": record.source_hash,
            "is_directory": record.is_directory,
            "created_at_utc": record.created_at_utc,
        }
        _save_manifest_local(manifest_path, manifest)

        message = commit_message or f"gitstore: store '{name}'"
        paths_to_commit = [artifact_rel, manifest_rel]
        git_add_commit_push(
            repo_path=str(repo),
            paths_in_repo=paths_to_commit,
            commit_message=message,
        )
        print(f"[gitstore] Uploaded '{name}' -> '{artifact_rel}' (hash={artifact_hash}).")
        return record
    finally:
        if encrypted_path.exists():
            encrypted_path.unlink()


def _load_manifest_local(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        return {}
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Manifest format is invalid.")
    return data


def _save_manifest_local(manifest_path: Path, manifest: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, sort_keys=False)
        f.write("\n")

