from pathlib import Path

from gitstore import GitStoreUploader


def main() -> None:
    """
    Destroy example with explicit defaults.

    GitStoreUploader defaults:
    - password=None (uses GITSTORE_PASSWORD)
    - vault_dir="vault"
    - request_timeout=60
    - password_env_var="GITSTORE_PASSWORD"
    - security_level="high"

    destroy defaults:
    - commit_message=None (auto message)
    """
    project_root = Path(__file__).resolve().parents[1]

    uploader = GitStoreUploader(
        repo_path=str(project_root),
        password=None,
        vault_dir="vault",
        request_timeout=60,
        password_env_var="GITSTORE_PASSWORD",
        security_level="high",
    )

    uploader.destroy(
        name="sample_data_demo",
        commit_message=None,
    )
    print("Destroyed: sample_data_demo")


if __name__ == "__main__":
    main()
