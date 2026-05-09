# gitstore

`gitstore` encrypts directories with `utilitz.crypto` and exchanges the encrypted text artifacts through GitHub-backed repositories.

## Installation

```bash
pip install gitstore
```

## Dependency on `utilitz`

This project depends on:

- `utilitz[crypto]` 0.9.1 or newer

## Core API

```python
from gitstore import upload_to_github, restore_from_github, restore_from_file
```

## Upload a Directory

```python
from gitstore import upload_to_github

record = upload_to_github(
    local_dir="C:/data/my_directory",
    name="my_backup_2026_05",
    repo_dir="C:/repos/my-vault-repo",
    password=None,
    vault_subdir="vault",
    request_timeout=60,
    commit_message=None,
    replace_existing=True,
    force=False,
    include_patterns=None,
    exclude_patterns=None,
    gitstore_path=None,
    salt_size=16,
    iterations=100_000,
    key_length=32,
    hash_name="sha256",
)
print(record)
```

Path parameters such as `local_dir`, `repo_dir`, and `gitstore_path` accept either strings or `pathlib.Path` objects.

Upload behavior:

- builds a `utilitz.crypto.CryptoInput` from the source directory
- compares the input `content_hash` with local state in `~/.gitstore.json`
- skips encryption and upload when the local content is unchanged, unless `force=True`
- encrypts with the security parameters passed through to `utilitz.crypto.Encryptor.encrypt(...)`
- writes the encrypted UTF-8 text manually as `vault/<name>.asc`
- stores only `artifact_name`, `artifact_hash`, and `timestamp` in `vault/index.json`
- keeps the private `content_hash` only in local state
- runs `git add`, `git commit`, and `git push` only for the `.asc` artifact and `index.json`

## Encryption Parameters

`gitstore` does not keep legacy security levels such as `standard`, `high`, or `paranoid`.
Encryption settings are exposed as named `upload_to_github(...)` parameters and passed directly to `utilitz.crypto.Encryptor.encrypt(...)`.

Supported parameters in `utilitz[crypto]` 0.9.1:

- `salt_size`: default `16`
- `iterations`: default `100_000`
- `key_length`: default `32`
- `hash_name`: only `"sha256"` is supported

The defaults match `utilitz[crypto]` 0.9.1.

## Restore a Directory

```python
from gitstore import restore_from_github

restored_path = restore_from_github(
    github_raw_url="https://raw.githubusercontent.com/USER/REPO/main/vault/my_backup_2026_05.asc",
    password=None,
    local_dir="C:/restore/my_backup_2026_05",
    overwrite=False,
    force=False,
    request_timeout=60,
    gitstore_path=None,
)
print(restored_path)
```

`local_dir` accepts either a string or a `pathlib.Path` object.

Restore behavior:

- accepts raw GitHub URLs and normalizes `github.com/.../blob/...` URLs to raw URLs
- downloads text artifacts with `urllib`
- compares the remote `artifact_hash` from `index.json` with local download state
- skips the download when the destination exists and the artifact hash is unchanged, unless `force=True`
- downloads the remote artifact when the hash changed, then delegates existing-destination handling to `utilitz`
- uses `force=True` only to bypass the skip check; `overwrite` still controls whether the destination may be replaced
- decrypts with `utilitz.crypto.Decryptor`
- restores only with `Decryptor.to_directory(...)`

Local restore from an already downloaded `.asc` file remains available:

```python
from gitstore import restore_from_file

restored_path = restore_from_file(
    encrypted_file_path="C:/downloads/my_backup_2026_05.asc",
    password=None,
    local_dir="C:/restore/my_backup_2026_05",
    overwrite=False,
)
print(restored_path)
```

## Valid Names

`name` is the artifact identifier. It is intentionally strict to keep Git paths predictable:

- allowed characters: letters, numbers, dots, underscores, and hyphens
- must start with a letter or number
- spaces and path separators are not allowed

Valid examples:

```text
documento_ventas_q2
maindb-version-0.1
backup.2026_05
```

## JSON Formats

Remote `vault/index.json`:

```json
[
  {
    "artifact_name": "my_backup_2026_05",
    "artifact_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "timestamp": "2026-05-08T21:10:00Z"
  }
]
```

Local `~/.gitstore.json`:

```json
{
  "uploads": [
    {
      "repo_dir": "C:/repos/my-vault-repo",
      "vault_subdir": "vault",
      "local_dir": "C:/data/my_directory",
      "artifact_name": "my_backup_2026_05",
      "content_hash": "d57e5433434d3d2c1234...",
      "timestamp": "2026-05-08T21:10:00Z"
    }
  ],
  "downloads": [
    {
      "local_dir": "C:/restore/my_backup_2026_05",
      "source_url": "https://raw.githubusercontent.com/USER/REPO/main/vault/my_backup_2026_05.asc",
      "artifact_hash": "e3b0c44298fc1c149afb...",
      "timestamp": "2026-05-08T21:15:00Z"
    }
  ]
}
```

## Password Source

`upload_to_github`, `restore_from_github`, and `restore_from_file` auto-detect password from:

- `GITSTORE_PASSWORD`

If `password` is not passed, the environment variable is used.
