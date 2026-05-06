from pathlib import Path

from gitstore import restore_from_file


def main() -> None:
    """
    Local restore example (no network) with explicit defaults.

    restore_from_file defaults:
    - password=None (uses GITSTORE_PASSWORD)
    - output_path=None
    - overwrite=False
    - password_env_var="GITSTORE_PASSWORD"
    """
    project_root = Path(__file__).resolve().parents[1]
    local_encrypted_file = project_root / "vault" / "sample_data_demo.asc"
    output_folder = project_root / "examples" / "data" / "restored_sample_data"

    restored_path = restore_from_file(
        encrypted_file_path=str(local_encrypted_file),
        password=None,
        output_path=str(output_folder),
        overwrite=False,
        password_env_var="GITSTORE_PASSWORD",
    )
    print(restored_path)


if __name__ == "__main__":
    main()
