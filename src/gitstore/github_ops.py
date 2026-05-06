import subprocess
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

    _run_git(repo, ["add", *paths_in_repo])
    _run_git(repo, ["commit", "-m", commit_message])
    _run_git(repo, ["push"])


def git_add_commit(
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


def git_stash_push(repo_path: str, message: str) -> bool:
    repo = Path(repo_path).expanduser().resolve()
    status = _run_git(repo, ["status", "--porcelain"], capture=True).stdout.strip()
    if not status:
        return False
    _run_git(repo, ["stash", "push", "-u", "-m", message])
    return True


def git_stash_pop(repo_path: str) -> None:
    repo = Path(repo_path).expanduser().resolve()
    _run_git(repo, ["stash", "pop"])


def git_purge_path_from_history(repo_path: str, path_in_repo: str) -> None:
    repo = Path(repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise FileNotFoundError(f"Not a git repository: {repo}")

    # Require clean working tree to avoid filter-branch failures and partial purges.
    status = _run_git(repo, ["status", "--porcelain"], capture=True).stdout.strip()
    if status:
        raise RuntimeError(
            "Working tree must be clean before purge. Commit or stash pending changes first."
        )

    # Rewrites history to remove the file from all commits.
    quoted_path = "'" + path_in_repo.replace("'", "'\"'\"'") + "'"
    _run_git(
        repo,
        [
            "filter-branch",
            "--force",
            "--index-filter",
            f"git rm -r --cached --ignore-unmatch -- {quoted_path}",
            "--prune-empty",
            "--tag-name-filter",
            "cat",
            "--",
            "--all",
        ],
    )

    # Remove backup refs created by filter-branch.
    refs_out = _run_git(repo, ["for-each-ref", "refs/original", "--format=%(refname)"], capture=True).stdout
    for ref in [line.strip() for line in refs_out.splitlines() if line.strip()]:
        _run_git(repo, ["update-ref", "-d", ref])

    # Clean unreachable objects.
    _run_git(repo, ["reflog", "expire", "--expire=now", "--all"])
    _run_git(repo, ["gc", "--prune=now", "--aggressive"])

    # Verify path is gone from reachable objects.
    rev_out = _run_git(repo, ["rev-list", "--all", "--objects"], capture=True).stdout
    if path_in_repo in rev_out:
        raise RuntimeError(f"Purge verification failed; path still reachable: {path_in_repo}")

    # Publish rewritten history after local verification succeeds.
    _run_git(repo, ["push", "origin", "--force", "--all"])
    _run_git(repo, ["push", "origin", "--force", "--tags"])

