from __future__ import annotations

import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

PathInput = str | Path


def _run_git(repo: Path, args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=capture,
        text=capture,
    )


def normalize_github_file_url(url: str) -> str:
    raw_url = (url or "").strip()
    if not raw_url:
        raise ValueError("url is required.")

    parsed = urllib.parse.urlparse(raw_url)
    if parsed.netloc.lower() != "github.com":
        return raw_url

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[2] != "blob":
        return raw_url

    owner, repo, _, ref, *file_parts = parts
    file_path = "/".join(urllib.parse.quote(part) for part in file_parts)
    return f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{ref}/{file_path}"


def download_text_urllib(
    raw_url: str,
    timeout: int = 60,
    encoding: str = "utf-8",
    *,
    cache_bust: bool = False,
) -> str:
    url = raw_url
    if cache_bust:
        separator = "&" if urllib.parse.urlparse(raw_url).query else "?"
        url = f"{raw_url}{separator}gitstore_cache_bust={time.time_ns()}"
    request = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode(encoding)


def write_text_file(path: PathInput, content: str, encoding: str = "utf-8") -> str:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding=encoding, newline="\n") as file_obj:
        file_obj.write(content)
    return str(destination)


def _git_config_get(repo: Path, args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "config", "--get-regexp", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines


def resolve_push_remote(repo_dir: PathInput, push_remote_name: str | None = None) -> str:
    repo = Path(repo_dir).expanduser().resolve()
    if push_remote_name:
        return push_remote_name

    remote_lines = _git_config_get(repo, [r"^remote\..*\.url$"])
    candidates: list[tuple[str, str]] = []
    for line in remote_lines:
        key, url = line.split(" ", 1)
        remote_name = key.split(".")[1]
        candidates.append((remote_name, url))

    for remote_name, url in candidates:
        lowered = url.strip().lower()
        if lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("git@"):
            return remote_name

    if candidates:
        return candidates[0][0]

    raise ValueError(f"No git remotes are configured for repository: {repo}")


def git_add_commit_push(
    repo_dir: PathInput,
    paths_in_repo: list[str],
    commit_message: str,
    push_remote_name: str | None = None,
) -> None:
    repo = Path(repo_dir).expanduser().resolve()
    if not (repo / ".git").exists():
        raise FileNotFoundError(f"Not a git repository: {repo}")
    if not paths_in_repo:
        raise ValueError("paths_in_repo must not be empty.")

    remote_name = resolve_push_remote(repo, push_remote_name=push_remote_name)
    _run_git(repo, ["add", *paths_in_repo])
    _run_git(repo, ["commit", "-m", commit_message])
    _run_git(repo, ["push", remote_name, "HEAD"])
