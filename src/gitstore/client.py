from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import GitStoreConfig
from .crypto_ops import decrypt_directory, encrypt_prepared_directory, prepare_directory_input
from .github_ops import (
    download_text_urllib,
    git_add_commit_push,
    normalize_github_file_url,
    resolve_push_remote,
    write_text_file,
)
from .state import find_download, find_upload, load_state, save_state, upsert_download, upsert_upload

PathInput = str | Path
DEFAULT_PASSWORD_ENV_VAR = "GITSTORE_PASSWORD"
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_NAME_RULES_MESSAGE = (
    "name must be a simple identifier using only letters, numbers, dots, "
    "underscores, and hyphens. It must start with a letter or number and must "
    "not contain spaces or path separators."
)


@dataclass(frozen=True)
class StoredArtifact:
    artifact_name: str
    artifact_hash: str
    content_hash: str
    timestamp: str
    artifact_path: str


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


def _clean_vault_subdir(vault_subdir: str) -> str:
    return vault_subdir.strip().strip("/\\") or "vault"


def _manifest_url_for_artifact(raw_url: str) -> str:
    return raw_url.rsplit("/", 1)[0] + "/index.json"


def _artifact_name_from_url(raw_url: str) -> str:
    filename = raw_url.rsplit("/", 1)[-1]
    return filename[:-4] if filename.endswith(".asc") else filename


def _load_manifest_local(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        return []
    with open(manifest_path, "r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, list) or not all(isinstance(record, dict) for record in data):
        raise ValueError("Manifest format is invalid.")
    return data


def _save_manifest_local(manifest_path: Path, manifest: list[dict[str, Any]]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as file_obj:
        json.dump(manifest, file_obj, indent=2, sort_keys=False)
        file_obj.write("\n")


def _upsert_manifest_record(manifest: list[dict[str, Any]], record: dict[str, str]) -> None:
    for index, existing in enumerate(manifest):
        if existing.get("artifact_name") == record["artifact_name"]:
            manifest[index] = record
            return
    manifest.append(record)


def _load_remote_manifest(raw_url: str, request_timeout: int) -> list[dict[str, Any]]:
    try:
        manifest_text = download_text_urllib(
            _manifest_url_for_artifact(raw_url),
            timeout=request_timeout,
            cache_bust=True,
        )
    except Exception:
        return []
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError:
        return []
    return manifest if isinstance(manifest, list) else []


def _remote_record_for_artifact(raw_url: str, request_timeout: int) -> dict[str, Any]:
    artifact_name = _artifact_name_from_url(raw_url)
    for record in _load_remote_manifest(raw_url, request_timeout):
        if isinstance(record, dict) and record.get("artifact_name") == artifact_name:
            return record
    return {}


def upload_to_github(
    local_dir: PathInput,
    name: str,
    repo_dir: PathInput,
    password: str | None = None,
    vault_subdir: str = "vault",
    request_timeout: int = 60,
    password_env_var: str = DEFAULT_PASSWORD_ENV_VAR,
    commit_message: str | None = None,
    replace_existing: bool = True,
    force: bool = False,
    include_patterns: str | list[str] | tuple[str, ...] | None = None,
    exclude_patterns: str | list[str] | tuple[str, ...] | None = None,
    gitstore_path: PathInput | None = None,
    push_remote_name: str | None = None,
    salt_size: int = 16,
    iterations: int = 600_000,
    key_length: int = 32,
    hash_name: str = "sha256",
) -> StoredArtifact:
    if not repo_dir:
        raise ValueError("repo_dir is required.")

    artifact_name = _validate_name(name)
    resolved_password = _resolve_password(password, password_env_var)
    config = GitStoreConfig(password=resolved_password,
                            request_timeout=request_timeout)
    resolved_repo_path = Path(repo_dir).expanduser().resolve()
    if not (resolved_repo_path / ".git").exists():
        raise FileNotFoundError(f"Not a git repository: {resolved_repo_path}")

    local_path = Path(local_dir).expanduser().resolve()
    if not local_path.is_dir():
        raise FileNotFoundError(f"Input directory not found: {local_path}")

    vault = _clean_vault_subdir(vault_subdir)
    manifest_rel = f"{vault}/index.json"
    manifest_path = resolved_repo_path / manifest_rel
    artifact_filename = f"{artifact_name}.asc"
    artifact_rel = f"{vault}/{artifact_filename}"
    artifact_abs = resolved_repo_path / artifact_rel

    prepared_input = prepare_directory_input(
        local_dir=local_path,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )

    state = load_state(gitstore_path)
    resolved_repo_dir = str(resolved_repo_path)
    resolved_local_dir = str(local_path)
    upload_record = find_upload(
        state,
        local_dir=resolved_local_dir,
        repo_dir=resolved_repo_dir,
        vault_subdir=vault,
        artifact_name=artifact_name,
    )
    if upload_record and upload_record.get("content_hash") == prepared_input.content_hash and not force:
        manifest = _load_manifest_local(manifest_path)
        manifest_record = next(
            (record for record in manifest if record.get(
                "artifact_name") == artifact_name),
            {},
        )
        print(f"[gitstore] Skip upload: '{artifact_name}' already up to date.")
        return StoredArtifact(
            artifact_name=artifact_name,
            artifact_hash=str(manifest_record.get("artifact_hash", "")),
            content_hash=prepared_input.content_hash,
            timestamp=str(upload_record.get("timestamp", "")),
            artifact_path=str(artifact_abs),
        )

    manifest = _load_manifest_local(manifest_path)
    if any(record.get("artifact_name") == artifact_name for record in manifest) and not replace_existing:
        raise ValueError(
            f"Name '{artifact_name}' already exists. Use replace_existing=True to replace it.")

    crypto_result = encrypt_prepared_directory(
        prepared_input,
        config=config,
        encryption_params={
            "salt_size": salt_size,
            "iterations": iterations,
            "key_length": key_length,
            "hash_name": hash_name,
        },
    )
    write_text_file(artifact_abs, crypto_result.encrypted_text,
                    encoding="utf-8")
    manifest_record = {
        "artifact_name": artifact_name,
        "artifact_hash": crypto_result.artifact_hash,
        "timestamp": crypto_result.timestamp,
    }
    _upsert_manifest_record(manifest, manifest_record)
    _save_manifest_local(manifest_path, manifest)

    message = commit_message or f"gitstore: store '{artifact_name}'"
    remote_name = resolve_push_remote(
        resolved_repo_path,
        push_remote_name=push_remote_name,
    )
    git_add_commit_push(
        repo_dir=resolved_repo_path,
        paths_in_repo=[artifact_rel, manifest_rel],
        commit_message=message,
        push_remote_name=remote_name,
    )
    state_record = {
        "repo_dir": resolved_repo_dir,
        "vault_subdir": vault,
        "local_dir": resolved_local_dir,
        "artifact_name": artifact_name,
        "content_hash": crypto_result.content_hash,
        "timestamp": crypto_result.timestamp,
    }
    upsert_upload(state, state_record)
    save_state(state, gitstore_path)

    print(f"[gitstore] Uploaded '{artifact_name}' -> '{artifact_rel}'.")
    return StoredArtifact(
        artifact_name=artifact_name,
        artifact_hash=crypto_result.artifact_hash,
        content_hash=crypto_result.content_hash,
        timestamp=crypto_result.timestamp,
        artifact_path=str(artifact_abs),
    )


def restore_from_github(
    github_raw_url: str,
    password: str | None = None,
    local_dir: PathInput | None = None,
    overwrite: bool = False,
    force: bool = False,
    request_timeout: int = 60,
    password_env_var: str = DEFAULT_PASSWORD_ENV_VAR,
    gitstore_path: PathInput | None = None,
) -> str:
    resolved_password = _resolve_password(password, password_env_var)
    config = GitStoreConfig(password=resolved_password,
                            request_timeout=request_timeout)
    raw_url = normalize_github_file_url(github_raw_url)
    if local_dir:
        destination = Path(local_dir).expanduser().resolve()
    else:
        destination = Path(tempfile.mkdtemp(
            prefix="gitstore_restore_")) / _artifact_name_from_url(raw_url)
    resolved_local_dir = str(destination)

    remote_record = _remote_record_for_artifact(raw_url, request_timeout)
    remote_artifact_hash = str(remote_record.get("artifact_hash", ""))
    state = load_state(gitstore_path)
    download_record = find_download(
        state, local_dir=resolved_local_dir, source_url=raw_url)
    if (
        download_record
        and remote_artifact_hash
        and download_record.get("artifact_hash") == remote_artifact_hash
        and destination.exists()
        and not force
    ):
        print(
            f"[gitstore] Skip download: '{raw_url}' already restored at '{destination}'.")
        return resolved_local_dir

    encrypted_text = download_text_urllib(raw_url, timeout=request_timeout, cache_bust=True)
    restored_path = decrypt_directory(
        encrypted_text=encrypted_text,
        config=config,
        local_dir=destination,
        overwrite=overwrite,
    )

    upsert_download(
        state,
        {
            "local_dir": str(Path(restored_path).resolve()),
            "source_url": raw_url,
            "artifact_hash": remote_artifact_hash,
            "timestamp": str(remote_record.get("timestamp", "")),
        },
    )
    save_state(state, gitstore_path)
    print(
        f"[gitstore] Downloaded and restored '{raw_url}' -> '{restored_path}'.")
    return restored_path


def restore_from_file(
    encrypted_file_path: PathInput,
    password: str | None = None,
    local_dir: PathInput | None = None,
    overwrite: bool = False,
    password_env_var: str = DEFAULT_PASSWORD_ENV_VAR,
) -> str:
    resolved_password = _resolve_password(password, password_env_var)
    config = GitStoreConfig(password=resolved_password, request_timeout=60)
    encrypted_file = Path(encrypted_file_path).expanduser().resolve()
    if not encrypted_file.is_file():
        raise FileNotFoundError(f"Encrypted file not found: {encrypted_file}")
    with open(encrypted_file, "r", encoding="utf-8") as file_obj:
        encrypted_text = file_obj.read()
    destination = local_dir
    if destination is None:
        destination = Path(tempfile.mkdtemp(prefix="gitstore_restore_")) / encrypted_file.stem
    restored_path = decrypt_directory(
        encrypted_text=encrypted_text,
        config=config,
        local_dir=destination,
        overwrite=overwrite,
    )
    print(f"[gitstore] Restored local artifact '{encrypted_file}' -> '{restored_path}'.")
    return restored_path
