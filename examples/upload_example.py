from pathlib import Path

from gitstore import GitStoreUploader


def main() -> None:
    """
    Upload example with explicit defaults.

    GitStoreUploader defaults:
    - password=None (uses GITSTORE_PASSWORD)
    - vault_dir="vault"
    - request_timeout=60
    - password_env_var="GITSTORE_PASSWORD"
    - security_level="high"

    store defaults:
    - commit_message=None (auto message)
    - replace_existing=True
    - security_level=None (inherits uploader security_level)
    """
    project_root = Path(__file__).resolve().parents[1]
    sample_folder = project_root / "examples" / "data" / "sample_data"

    uploader = GitStoreUploader(
        repo_path=str(project_root),
        password=None,
        vault_dir="vault",
        request_timeout=60,
        password_env_var="GITSTORE_PASSWORD",
        security_level="high",
    )

    record = uploader.store(
        source_path=str(sample_folder),
        name="sample_data_demo",
        commit_message=None,
        replace_existing=True,
        security_level=None,
    )
    print(record)


if __name__ == "__main__":
    main()
