from pathlib import Path

from gitstore import restore_from_github


def main() -> None:
    """
    Remote directory restore example with explicit defaults.

    restore_from_github parameters:
    - github_raw_url: raw URL or github.com/.../blob/... URL
    - password=EXAMPLE_PASSWORD
    - local_dir=None: creates a temporary restore directory; str or pathlib.Path
    - overwrite=False
    - force=False: skips only when local download state matches remote artifact_hash
    - request_timeout=60
    - password_env_var="GITSTORE_PASSWORD"
    - gitstore_path=None: uses ~/.gitstore.json
    """
    project_root = Path(__file__).resolve().parents[1]
    local_dir = project_root / "examples" / "restored_directory"

    restored_path = restore_from_github(
        github_raw_url="https://raw.githubusercontent.com/artitzco/gitstore/main/vault/sample_data_demo.asc",
        password="gitstore-example-9dK4vQp2Lm7xR8sN",
        local_dir=local_dir,
        overwrite=False,
        force=False,
        request_timeout=60,
        password_env_var="GITSTORE_PASSWORD",
        gitstore_path=None,
    )
    print(restored_path)


if __name__ == "__main__":
    main()
