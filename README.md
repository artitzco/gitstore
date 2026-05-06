# gitstore

`gitstore` is a focused Python package for one goal:

- upload encrypted files/folders to a GitHub-backed repo
- download and restore encrypted GitHub files later

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
from gitstore import upload_to_github, restore_from_github, restore_from_file
```

## Upload

```python
from gitstore import upload_to_github

record = upload_to_github(
    source_path="C:/data/documento.pdf",  # file or directory
    name="documento_ventas_q2",           # logical name only
    repo_path="C:/repos/my-publish-repo", # required
    password=None,                        # default: uses GITSTORE_PASSWORD
    vault_dir="vault",                    # default
    request_timeout=60,                   # default
    security_level="high",                # default
    replace_existing=True,                # default
    force_upload=False,                   # default
    commit_message=None,                  # default: automatic message
)
print(record)
```

Upload behavior:

- computes `source_hash` from source content before encryption
- skips upload if same `name` already has same `source_hash`
- set `force_upload=True` to upload even when the current source matches the remote metadata
- stores artifact as `vault/<name>.asc`
- stores metadata in `vault/index.json`
- removes temporary encrypted file after processing

## Valid Names

`name` is the logical identifier used to upload an artifact.
It is intentionally strict to keep Git paths predictable:

- allowed characters: letters, numbers, dots, underscores, and hyphens
- must start with a letter or number
- spaces and path separators are not allowed

Valid examples:

```text
documento_ventas_q2
maindb-version-0.1
backup.2026_05
```

Invalid examples:

```text
maindb -version 0.1
../secret
folder/documento
```

## Download

```python
from gitstore import restore_from_github

output_path = restore_from_github(
    github_url="https://github.com/USER/REPO/blob/main/vault/documento_ventas_q2.asc",
    password=None,      # default: uses GITSTORE_PASSWORD
    output_path=None,   # default: restores in the current working directory
    overwrite=False,    # default
    force_download=False, # default
)
print(output_path)
```

Local restore (no network):

```python
from gitstore import restore_from_file

output_path = restore_from_file(
    encrypted_file_path="C:/downloads/documento_ventas_q2.asc",
    password=None,      # default: uses GITSTORE_PASSWORD
    output_path=None,   # optional
    overwrite=False,    # default
)
print(output_path)
```

Tip:

- use `restore_from_file(...)` when the target machine has SSL/certificate restrictions and you prefer manual transfer of the `.asc` file.

Download behavior:

- accepts normal GitHub file URLs (`github.com/.../blob/...`) and raw URLs
- skips download when `output_path` already exists and matches the remote `source_hash` in `vault/index.json`
- set `force_download=True` to download even when the local output appears aligned
- downloads the encrypted `.asc` file to a temporary location
- restores files or directories automatically with `utilitz.crypto`
- removes the temporary encrypted file after restore
- supports local decode with `restore_from_file(...)` when manual download is preferred

## Password Source

`upload_to_github`, `restore_from_github`, and `restore_from_file` auto-detect password from:

- `GITSTORE_PASSWORD`

If `password` is not passed, the environment variable is used.
