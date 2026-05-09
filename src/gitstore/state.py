from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PathInput = str | Path


def default_gitstore_path() -> Path:
    return Path.home() / ".gitstore.json"


def load_state(gitstore_path: PathInput | None = None) -> dict[str, list[dict[str, Any]]]:
    path = Path(gitstore_path).expanduser() if gitstore_path else default_gitstore_path()
    if not path.exists():
        return {"uploads": [], "downloads": []}

    with open(path, "r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise ValueError("Local gitstore state format is invalid.")

    uploads = data.get("uploads", [])
    downloads = data.get("downloads", [])
    if not isinstance(uploads, list) or not isinstance(downloads, list):
        raise ValueError("Local gitstore state format is invalid.")
    if not all(isinstance(record, dict) for record in uploads + downloads):
        raise ValueError("Local gitstore state format is invalid.")
    return {"uploads": uploads, "downloads": downloads}


def save_state(state: dict[str, list[dict[str, Any]]], gitstore_path: PathInput | None = None) -> str:
    path = Path(gitstore_path).expanduser() if gitstore_path else default_gitstore_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as file_obj:
        json.dump(state, file_obj, indent=2, sort_keys=False)
        file_obj.write("\n")
    return str(path)


def find_upload(
    state: dict[str, list[dict[str, Any]]],
    *,
    local_dir: str,
    repo_dir: str,
    vault_subdir: str,
    artifact_name: str,
) -> dict[str, Any] | None:
    for record in state["uploads"]:
        if (
            record.get("local_dir") == local_dir
            and record.get("repo_dir") == repo_dir
            and record.get("vault_subdir") == vault_subdir
            and record.get("artifact_name") == artifact_name
        ):
            return record
    return None


def upsert_upload(
    state: dict[str, list[dict[str, Any]]],
    record: dict[str, Any],
) -> None:
    existing = find_upload(
        state,
        local_dir=str(record["local_dir"]),
        repo_dir=str(record["repo_dir"]),
        vault_subdir=str(record["vault_subdir"]),
        artifact_name=str(record["artifact_name"]),
    )
    if existing is None:
        state["uploads"].append(record)
        return
    existing.clear()
    existing.update(record)


def find_download(
    state: dict[str, list[dict[str, Any]]],
    *,
    local_dir: str,
    source_url: str,
) -> dict[str, Any] | None:
    for record in state["downloads"]:
        if record.get("local_dir") == local_dir and record.get("source_url") == source_url:
            return record
    return None


def upsert_download(
    state: dict[str, list[dict[str, Any]]],
    record: dict[str, Any],
) -> None:
    existing = find_download(
        state,
        local_dir=str(record["local_dir"]),
        source_url=str(record["source_url"]),
    )
    if existing is None:
        state["downloads"].append(record)
        return
    existing.clear()
    existing.update(record)
