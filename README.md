# gitstore

`gitstore` is a focused Python package for one goal:

- upload encrypted files/folders to a GitHub-backed repo
- restore them later by logical name from GitHub raw URLs

## Installation

```bash
pip install gitstore
```

## Dependency on `utilitz`

This project depends on:

- `utilitz[crypto]`
- `requests`

## Project Structure

```text
gitstore/
  src/gitstore/
    __init__.py
    client.py
    config.py
    crypto_ops.py
    github_ops.py
  pyproject.toml
  README.md
```

## Core API

```python
from gitstore import GitStoreUploader, GitStoreDownloader
```

## Upload

```python
from gitstore import GitStoreUploader

uploader = GitStoreUploader(
    repo_path="C:/repos/my-publish-repo",  # optional, defaults to current working directory
    security_level="high",                 # default
)

record = uploader.store(
    source_path="C:/data/documento.pdf",   # file or directory
    name="documento_ventas_q2",            # logical name only
    replace_existing=True,                   # default: replace and purge previous history
    commit_message=None,                     # default: automatic message
)
print(record)
```

## Download

```python
from gitstore import GitStoreDownloader

downloader = GitStoreDownloader(
    raw_base_url="https://raw.githubusercontent.com/USER/REPO/main",
)

output_path = downloader.restore(
    name="documento_ventas_q2",
    output_path="C:/restore/documento.pdf",
    overwrite=True,
)
print(output_path)
```

## Destroy

```python
from gitstore import GitStoreUploader

uploader = GitStoreUploader(repo_path="C:/repos/my-publish-repo")
uploader.destroy(name="documento_ventas_q2")
```

`destroy(...)` removes the current artifact and rewrites Git history for that artifact path.

## Password Source

Both classes auto-detect password from:

- `GITSTORE_PASSWORD`

If `password` is not passed, the environment variable is used.
