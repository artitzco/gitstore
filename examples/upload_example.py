from pathlib import Path

from gitstore import GitStoreUploader


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sample_folder = project_root / "examples" / "data" / "sample_data"

    uploader = GitStoreUploader(
        repo_path=str(project_root),
        security_level="high",
    )

    record = uploader.store(
        source_path=str(sample_folder),
        name="sample_data_demo",
        replace_existing=True,
        commit_message=None,
    )
    print(record)


if __name__ == "__main__":
    main()
