import subprocess
import urllib.request
from pathlib import Path

import requests


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
    if "github.com/" in raw_url and "/blob/" in raw_url:
        return raw_url.replace("https://github.com/", "https://raw.githubusercontent.com/").replace(
            "/blob/",
            "/",
            1,
        )
    return raw_url


def download_raw_file(raw_url: str, output_path: str, timeout: int = 60) -> str:
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(raw_url, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
    return str(destination)


def download_raw_file_urllib(raw_url: str, output_path: str, timeout: int = 60) -> str:
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(raw_url, timeout=timeout) as response:
        content = response.read()
    with open(destination, "wb") as f:
        f.write(content)
    return str(destination)


def git_add_commit_push(
    repo_path: str,
    paths_in_repo: list[str],
    commit_message: str,
) -> None:
    repo = Path(repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise FileNotFoundError(f"Not a git repository: {repo}")
    if not paths_in_repo:
        raise ValueError("paths_in_repo must not be empty.")

    _run_git(repo, ["add", *paths_in_repo])
    _run_git(repo, ["commit", "-m", commit_message])
    _run_git(repo, ["push"])

