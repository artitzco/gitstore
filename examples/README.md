# Examples

This folder is a self-contained demo for `gitstore`.

## Included scripts

- `upload_example.py`: encrypts and uploads `examples/data/sample_data`.
- `restore_example.py`: restores `sample_data_demo` using default restore behavior (`output_path=None`, `overwrite=False`).
- `destroy_example.py`: destroys `sample_data_demo` (including history purge).

## Sample data

- `data/sample_data/`: small folder used as upload input.
- `data/restored_sample_data/`: restore output folder.

## Expected password source

Set `GITSTORE_PASSWORD` in your environment, or pass `password=` in the classes.
