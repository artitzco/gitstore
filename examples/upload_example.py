from pathlib import Path

from gitstore import upload_to_github


def main() -> None:
    """
    Directory upload example with explicit defaults.

    upload_to_github parameters:
    - local_dir: directory to package, hash, and encrypt; str or pathlib.Path
    - name: artifact name; saved as <name>.asc
    - repo_dir: local git repository that receives the vault files; str or pathlib.Path
    - password=EXAMPLE_PASSWORD
    - vault_subdir="vault"
    - request_timeout=60
    - password_env_var="GITSTORE_PASSWORD"
    - commit_message=None: uses an automatic message
    - replace_existing=True
    - force=False: skips only when local content_hash is unchanged
    - include_patterns=None
    - exclude_patterns=None
    - gitstore_path=None: uses ~/.gitstore.json
    - push_remote_name=None
    - salt_size=16
    - iterations=600_000
    - key_length=32
    - hash_name="sha256"
    """
    project_root = Path(__file__).resolve().parents[1]
    local_dir = project_root / "examples" / "sample_data"

    record = upload_to_github(
        local_dir=local_dir,
        name="sample_data_demo",
        repo_dir=project_root,
        password="gitstore-example-9dK4vQp2Lm7xR8sN",
        vault_subdir="vault",
        request_timeout=60,
        password_env_var="GITSTORE_PASSWORD",
        commit_message=None,
        replace_existing=True,
        force=False,
        include_patterns=None,
        exclude_patterns=None,
        gitstore_path=None,
        push_remote_name=None,
        salt_size=16,
        iterations=600_000,
        key_length=32,
        hash_name="sha256",
    )
    print(record)


if __name__ == "__main__":
    main()
