import json
import os
import shutil
import tempfile
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import GitStoreConfig
from .github_ops import download_raw_file, git_add_commit_push, git_purge_path_from_history
from .crypto_ops import decrypt_directory, decrypt_file, encrypt_directory, encrypt_file

DEFAULT_PASSWORD_ENV_VAR = "GITSTORE_PASSWORD"


@dataclass(frozen=True)
class StoredArtifact:
    name: str
    artifact: str
    artifact_hash: str
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
        source = Path(source_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Input path not found: {source}")
        if not name or any(sep in name for sep in ("/", "\\")):
            raise ValueError("name must be a simple identifier without path separators.")
        self._ensure_repo()

        is_directory = source.is_dir()
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

            manifest = self._load_manifest_local()
            existing_record = manifest.get(name)
            if existing_record:
                existing_hash = str(existing_record.get("artifact_hash", "")).lower()
                if existing_hash == artifact_hash:
                    # Same content already stored for the same logical name.
                    print(
                        f"[gitstore] Skip upload: '{name}' already up to date "
                        f"(hash={artifact_hash})."
                    )
                    return StoredArtifact(
                        name=name,
                        artifact=str(existing_record["artifact"]),
                        artifact_hash=existing_hash,
                        is_directory=bool(existing_record["is_directory"]),
                        created_at_utc=str(existing_record["created_at_utc"]),
                    )
                if not replace_existing:
                    raise ValueError(
                        f"Name '{name}' already exists. Use replace_existing=True to replace it."
                    )

            shutil.copy2(encrypted_path, artifact_abs)

            record = StoredArtifact(
                name=name,
                artifact=artifact_filename,
                artifact_hash=artifact_hash,
                is_directory=is_directory,
                created_at_utc=datetime.now(timezone.utc).isoformat(),
            )
            manifest[name] = {
                "name": record.name,
                "artifact": record.artifact,
                "artifact_hash": record.artifact_hash,
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
        self._ensure_repo()
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
        git_add_commit_push(
            repo_path=str(self.repo_path),
            paths_in_repo=[artifact_rel, self._manifest_rel],
            commit_message=message,
        )
        git_purge_path_from_history(repo_path=str(self.repo_path), path_in_repo=artifact_rel)
        print(f"[gitstore] Destroyed '{name}' and purged '{artifact_rel}' from history.")

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
        record = self._get_manifest_record(name)
        artifact = record["artifact"]
        artifact_hash = str(record.get("artifact_hash") or "")
        is_directory = bool(record["is_directory"])
        local_index_path, expected_existing = self._local_registry_paths(
            output_path=output_path,
            is_directory=is_directory,
            name=name,
        )
        local_index = self._load_local_download_index(local_index_path)
        local_record = local_index.get(name)
        if (
            local_record
            and str(local_record.get("artifact_hash") or "") == artifact_hash
            and expected_existing
            and expected_existing.exists()
        ):
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
            local_index[name] = {
                "name": name,
                "artifact": artifact,
                "artifact_hash": artifact_hash,
                "is_directory": is_directory,
                "created_at_utc": str(record.get("created_at_utc", "")),
                "restored_path": restored_path,
                "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            }
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

        base_dir = target if is_directory else target.parent
        idx = base_dir / ".gitstore" / "index.json"
        return idx, target

    def _load_local_download_index(self, index_path: Path) -> dict:
        if not index_path.exists():
            return {}
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid local download index format: {index_path}")
        return data

    def _save_local_download_index(self, index_path: Path, data: dict) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")

