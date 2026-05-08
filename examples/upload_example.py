from pathlib import Path

from gitstore import upload_to_github


def main() -> None:
    """
    Upload example with explicit defaults.

    upload_to_github defaults:
    - password=None (uses GITSTORE_PASSWORD)
    - vault_dir="vault"
    - request_timeout=60
    - password_env_var="GITSTORE_PASSWORD"
    - security_level="high"
    - commit_message=None (auto message)
    - replace_existing=True
    - force=False
    """
    project_root = Path(__file__).resolve().parents[1]
    sample_folder = project_root / "examples" / "data" / "sample_data"

    record = upload_to_github(
        source_path=str(sample_folder),
        name="sample_data_demo",
        repo_path=str(project_root),
        password=None,
        vault_dir="vault",
        request_timeout=60,
        password_env_var="GITSTORE_PASSWORD",
        security_level="high",
        commit_message=None,
        replace_existing=True,
        force=False,
    )
    print(record)


if __name__ == "__main__":
    main()
