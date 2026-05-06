from pathlib import Path

from gitstore import GitStoreDownloader


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_folder = project_root / "examples" / "data" / "restored_sample_data"

    downloader = GitStoreDownloader(
        raw_base_url="https://raw.githubusercontent.com/artitzco/gitstore/main",
    )

    restored_path = downloader.restore(
        name="sample_data_demo",
        output_path=str(output_folder),
        overwrite=True,
    )
    print(restored_path)


if __name__ == "__main__":
    main()
