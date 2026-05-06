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
    git_add_commit,
    git_add_commit_push,
    git_purge_path_from_history,
    git_stash_pop,
    git_stash_push,
)
from .crypto_ops import decrypt_directory, decrypt_file, encrypt_directory, encrypt_file

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


def _hash_key_id(secret: str) -> str:
    return hashlib.sha256(f"gitstore-hash-key:{secret}".encode("utf-8")).hexdigest()[:24]


class GitStoreUploader:
    def __init__(
        self,
        repo_path: str,
        password: str | None = None,
        vault_dir: str = "vault",
        request_timeout: int = 60,
        password_env_var: str = DEFAULT_PASSWORD_ENV_VAR,
        security_level: str = "high",
    ) -> None:
        if not repo_path:
            raise ValueError("repo_path is required for uploader.")
        resolved_password = _resolve_password(password, password_env_var)
        self.config = GitStoreConfig(password=resolved_password, request_timeout=request_timeout)
        self.repo_path = Path(repo_path).expanduser().resolve()
        self.vault_dir = vault_dir.strip().strip("/\\") or "vault"
        self._manifest_rel = f"{self.vault_dir}/index.json"
        self.password_env_var = password_env_var
        self.security_level = security_level

    def store(
        self,
        source_path: str,
        name: str,
        commit_message: str | None = None,
        replace_existing: bool = True,
        security_level: str | None = None,
    ) -> StoredArtifact:
        name = _validate_name(name)
        source = Path(source_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Input path not found: {source}")
        self._ensure_repo()

        is_directory = source.is_dir()
        source_hash = _hmac_source(source, self.config.password)
        manifest = self._load_manifest_local()
        existing_record = manifest.get(name)
        if existing_record:
            existing_source_hash = str(existing_record.get("source_hash", "")).lower()
            if existing_source_hash == source_hash.lower():
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
                raise ValueError(
                    f"Name '{name}' already exists. Use replace_existing=True to replace it."
                )

        level = security_level or self.security_level
        if is_directory:
            encrypted_path = Path(
                encrypt_directory(
                    source_directory=str(source),
                    config=self.config,
                    security_level=level,
                )
            )
        else:
            encrypted_path = Path(
                encrypt_file(
                    source_path=str(source),
                    config=self.config,
                    security_level=level,
                )
            )

        try:
            extension = "".join(encrypted_path.suffixes) or ".asc"
            artifact_hash = _hash_from_name_or_content(encrypted_path)
            artifact_filename = f"{name}{extension}"
            artifact_rel = f"{self.vault_dir}/{artifact_filename}"
            artifact_abs = self.repo_path / artifact_rel
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
            self._save_manifest_local(manifest)

            message = commit_message or f"gitstore: store '{name}'"
            paths_to_commit = [artifact_rel, self._manifest_rel]
            git_add_commit_push(
                repo_path=str(self.repo_path),
                paths_in_repo=paths_to_commit,
                commit_message=message,
            )
            print(
                f"[gitstore] Uploaded '{name}' -> '{artifact_rel}' "
                f"(hash={artifact_hash})."
            )
            return record
        finally:
            if encrypted_path.exists():
                encrypted_path.unlink()

    def destroy(self, name: str, commit_message: str | None = None) -> None:
        name = _validate_name(name)
        self._ensure_repo()
        stashed = git_stash_push(str(self.repo_path), "gitstore: temporary stash before destroy")
        try:
            self._destroy_clean(name=name, commit_message=commit_message)
        finally:
            if stashed:
                git_stash_pop(str(self.repo_path))

    def _destroy_clean(self, name: str, commit_message: str | None = None) -> None:
        manifest = self._load_manifest_local()
        if name not in manifest:
            raise KeyError(f"Name not found in manifest: {name}")
        record = manifest[name]
        artifact = record.get("artifact")
        if not artifact:
            raise ValueError(f"Invalid manifest record for name: {name}")

        artifact_rel = f"{self.vault_dir}/{artifact}"
        artifact_abs = self.repo_path / artifact_rel
        if artifact_abs.exists():
            artifact_abs.unlink()

        del manifest[name]
        self._save_manifest_local(manifest)

        message = commit_message or f"gitstore: destroy '{name}'"
        git_add_commit(
            repo_path=str(self.repo_path),
            paths_in_repo=[artifact_rel, self._manifest_rel],
            commit_message=message,
        )
        git_purge_path_from_history(repo_path=str(self.repo_path), path_in_repo=artifact_rel)
        print(f"[gitstore] Destroyed '{name}' and purged '{artifact_rel}' from history.")

    def destroy_artifact(
        self,
        artifact_filename: str,
        commit_message: str | None = None,
        purge_history: bool = True,
    ) -> None:
        if not artifact_filename or any(sep in artifact_filename for sep in ("/", "\\")):
            raise ValueError("artifact_filename must be a simple filename without path separators.")
        self._ensure_repo()
        stashed = git_stash_push(str(self.repo_path), "gitstore: temporary stash before destroy artifact")
        try:
            self._destroy_artifact_clean(
                artifact_filename=artifact_filename,
                commit_message=commit_message,
                purge_history=purge_history,
            )
        finally:
            if stashed:
                git_stash_pop(str(self.repo_path))

    def _destroy_artifact_clean(
        self,
        artifact_filename: str,
        commit_message: str | None = None,
        purge_history: bool = True,
    ) -> None:
        artifact_rel = f"{self.vault_dir}/{artifact_filename}"
        artifact_abs = self.repo_path / artifact_rel
        if not artifact_abs.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_abs}")

        artifact_abs.unlink()
        message = commit_message or f"gitstore: destroy artifact '{artifact_filename}'"
        git_add_commit(
            repo_path=str(self.repo_path),
            paths_in_repo=[artifact_rel],
            commit_message=message,
        )
        if purge_history:
            git_purge_path_from_history(repo_path=str(self.repo_path), path_in_repo=artifact_rel)
            print(f"[gitstore] Destroyed artifact and purged history: '{artifact_rel}'.")
        else:
            print(f"[gitstore] Destroyed artifact without history purge: '{artifact_rel}'.")

    def _ensure_repo(self) -> None:
        if not (self.repo_path / ".git").exists():
            raise FileNotFoundError(f"Not a git repository: {self.repo_path}")

    def _manifest_path(self) -> Path:
        return self.repo_path / self._manifest_rel

    def _load_manifest_local(self) -> dict:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Manifest format is invalid.")
        return data

    def _save_manifest_local(self, manifest: dict) -> None:
        manifest_path = self._manifest_path()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, indent=2, sort_keys=False)
            f.write("\n")


class GitStoreDownloader:
    def __init__(
        self,
        raw_base_url: str,
        password: str | None = None,
        vault_dir: str = "vault",
        request_timeout: int = 60,
        password_env_var: str = DEFAULT_PASSWORD_ENV_VAR,
    ) -> None:
        if not raw_base_url:
            raise ValueError("raw_base_url is required for downloader.")
        resolved_password = _resolve_password(password, password_env_var)
        self.config = GitStoreConfig(password=resolved_password, request_timeout=request_timeout)
        self.raw_base_url = raw_base_url.rstrip("/")
        self.vault_dir = vault_dir.strip().strip("/\\") or "vault"
        self._manifest_rel = f"{self.vault_dir}/index.json"
        self.password_env_var = password_env_var

    def restore(
        self,
        name: str,
        output_path: str | None = None,
        overwrite: bool = False,
    ) -> str:
        name = _validate_name(name)
        record = self._get_manifest_record(name)
        artifact = record["artifact"]
        artifact_hash = str(record.get("artifact_hash") or "")
        is_directory = bool(record["is_directory"])
        current_key_id = _hash_key_id(self.config.password)
        local_index_path, expected_existing = self._local_registry_paths(
            output_path=output_path,
            is_directory=is_directory,
            name=name,
        )
        local_index = self._load_local_download_index(local_index_path)
        already_restored = False
        for item in local_index:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "") != name:
                continue
            if str(item.get("artifact_hash") or "") != artifact_hash:
                continue
            if str(item.get("hash_key_id") or "") != current_key_id:
                # Password changed: force restore again.
                continue
            recorded_path = str(item.get("restored_path") or "")
            recorded_exists = Path(recorded_path).exists() if recorded_path else False
            expected_exists = expected_existing.exists() if expected_existing else False
            if expected_exists or recorded_exists:
                already_restored = True
                break
        if already_restored:
            print(
                f"[gitstore] Skip download: '{name}' already restored "
                f"(hash={artifact_hash})."
            )
            return str(expected_existing)

        temp_dir = Path(tempfile.mkdtemp(prefix="gitstore_restore_"))
        temp_file = temp_dir / "artifact.enc"
        try:
            raw_url = f"{self.raw_base_url}/{self.vault_dir}/{artifact}"
            download_raw_file(raw_url, str(temp_file), timeout=self.config.request_timeout)
            if is_directory:
                restored_path = decrypt_directory(
                    encrypted_path=str(temp_file),
                    config=self.config,
                    output_path=output_path,
                    overwrite=overwrite,
                )
            else:
                restored_path = decrypt_file(
                    encrypted_path=str(temp_file),
                    config=self.config,
                    output_path=output_path,
                    overwrite=overwrite,
                )
            local_index.append({
                "name": name,
                "artifact": artifact,
                "artifact_hash": artifact_hash,
                "hash_key_id": current_key_id,
                "is_directory": is_directory,
                "created_at_utc": str(record.get("created_at_utc", "")),
                "restored_path": restored_path,
                "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            self._save_local_download_index(local_index_path, local_index)
            print(
                f"[gitstore] Downloaded and restored '{name}' -> '{restored_path}' "
                f"(hash={artifact_hash})."
            )
            return restored_path
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _get_manifest_record(self, name: str) -> dict:
        manifest_url = f"{self.raw_base_url}/{self._manifest_rel}"
        temp_dir = Path(tempfile.mkdtemp(prefix="gitstore_manifest_"))
        temp_manifest = temp_dir / "index.json"
        try:
            download_raw_file(manifest_url, str(temp_manifest), timeout=self.config.request_timeout)
            with open(temp_manifest, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        if name not in manifest:
            raise KeyError(f"Name not found in manifest: {name}")
        record = manifest[name]
        if not isinstance(record, dict) or "artifact" not in record or "is_directory" not in record:
            raise ValueError(f"Invalid manifest record for name: {name}")
        return record

    def _local_registry_paths(
        self,
        output_path: str | None,
        is_directory: bool,
        name: str,
    ) -> tuple[Path, Path | None]:
        if output_path:
            out = Path(output_path).expanduser().resolve()
            target = out
        else:
            # Conservative default when no explicit output path is passed.
            base = Path.cwd().resolve()
            target = base / name

        # Keep metadata file at the same level as the restored artifact.
        base_dir = target.parent
        idx = base_dir / ".gitstore.json"
        return idx, target

    def _load_local_download_index(self, index_path: Path) -> list[dict]:
        if not index_path.exists():
            return []
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Invalid local download index format: {index_path}")
        return [item for item in data if isinstance(item, dict)]

    def _save_local_download_index(self, index_path: Path, data: list[dict]) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")

