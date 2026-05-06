# Examples

This folder is a self-contained demo for `gitstore`.

## Included scripts

- `upload_example.py`: encrypts and uploads `examples/data/sample_data` with `upload_to_github`.
- `restore_example.py`: downloads and restores an encrypted GitHub file with `download_from_github`.

## Sample data

- `data/sample_data/`: small folder used as upload input.
- `data/restored_sample_data/`: restore output folder.

## Expected password source

Set `GITSTORE_PASSWORD` in your environment, or pass `password=` in the classes.
