from gitstore import GitStoreDownloader


def main() -> None:
    """
    Restore example with explicit defaults.

    GitStoreDownloader defaults:
    - password=None (uses GITSTORE_PASSWORD)
    - vault_dir="vault"
    - request_timeout=60
    - password_env_var="GITSTORE_PASSWORD"

    restore defaults:
    - output_path=None
    - overwrite=False
    """
    downloader = GitStoreDownloader(
        raw_base_url="https://raw.githubusercontent.com/artitzco/gitstore/main",
        password=None,
        vault_dir="vault",
        request_timeout=60,
        password_env_var="GITSTORE_PASSWORD",
    )

    restored_path = downloader.restore(
        name="sample_data_demo",
        output_path=None,
        overwrite=False,
    )
    print(restored_path)


if __name__ == "__main__":
    main()
