from pathlib import Path

from gitstore import restore_from_github


def main() -> None:
    """
    Restore example with explicit defaults.

    restore_from_github defaults:
    - password=None (uses GITSTORE_PASSWORD)
    - output_path=None
    - overwrite=False
    - force=False
    - use_urllib=False
    - request_timeout=60
    - password_env_var="GITSTORE_PASSWORD"
    """
    project_root = Path(__file__).resolve().parents[1]
    output_folder = project_root / "examples" / "data" / "restored_sample_data"

    restored_path = restore_from_github(
        github_raw_url="https://raw.githubusercontent.com/artitzco/gitstore/main/vault/sample_data_demo.asc",
        password=None,
        output_path=str(output_folder),
        overwrite=False,
        force=False,
        use_urllib=False,
        request_timeout=60,
        password_env_var="GITSTORE_PASSWORD",
    )
    print(restored_path)


if __name__ == "__main__":
    main()
