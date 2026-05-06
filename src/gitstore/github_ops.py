import subprocess
from pathlib import Path

import requests


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

    subprocess.run(["git", "add", *paths_in_repo], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", commit_message], cwd=repo, check=True)
    subprocess.run(["git", "push"], cwd=repo, check=True)


def git_purge_path_from_history(repo_path: str, path_in_repo: str) -> None:
    repo = Path(repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise FileNotFoundError(f"Not a git repository: {repo}")

    # Rewrites history to remove the file from all commits, then force-pushes.
    subprocess.run(
        [
            "git",
            "filter-branch",
            "--force",
            "--index-filter",
            f"git rm -r --cached --ignore-unmatch -- {path_in_repo}",
            "--prune-empty",
            "--tag-name-filter",
            "cat",
            "--",
            "--all",
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "push", "origin", "--force", "--all"], cwd=repo, check=True)
    subprocess.run(["git", "push", "origin", "--force", "--tags"], cwd=repo, check=True)

