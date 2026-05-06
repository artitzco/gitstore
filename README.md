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
    repo_path="C:/repos/my-publish-repo",  # required
    security_level="high",                 # default
)

record = uploader.store(
    source_path="C:/data/documento.pdf",  # file or directory
    name="documento_ventas_q2",           # logical name only
    replace_existing=True,                # default
    commit_message=None,                  # default: automatic message
)
print(record)
```

Upload behavior:

- computes `source_hash` from source content before encryption
- skips upload if same `name` already has same `source_hash`
- stores artifact as `vault/<name>.asc`
- stores metadata in `vault/index.json`
- removes temporary encrypted file after processing

## Download

```python
from gitstore import GitStoreDownloader

downloader = GitStoreDownloader(
    raw_base_url="https://raw.githubusercontent.com/USER/REPO/main",
)

output_path = downloader.restore(
    name="documento_ventas_q2",
    # output_path is optional
    # overwrite defaults to False
)
print(output_path)
```

Download behavior:

- downloads artifact from `raw_base_url`
- restores with `utilitz.crypto` (`overwrite=False` by default)
- writes local restore registry to `.gitstore.json` at the same level as restored output
- local registry is a list of metadata entries
- skips download if same `name` + `artifact_hash` is already restored and output still exists

## Destroy

```python
from gitstore import GitStoreUploader

uploader = GitStoreUploader(repo_path="C:/repos/my-publish-repo")
uploader.destroy(name="documento_ventas_q2")
```

`destroy(...)` removes the current artifact and rewrites Git history for that artifact path.

For legacy/untracked artifacts not present in `index.json`:

```python
uploader.destroy_artifact("old_file.asc")
```

## Password Source

Both classes auto-detect password from:

- `GITSTORE_PASSWORD`

If `password` is not passed, the environment variable is used.
