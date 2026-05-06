from pathlib import Path

from gitstore import GitStoreUploader


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    uploader = GitStoreUploader(
        repo_path=str(project_root)
    )

    uploader.destroy(
        name="sample_data_demo",
        commit_message=None,
    )
    print("Destroyed: sample_data_demo")


if __name__ == "__main__":
    main()
