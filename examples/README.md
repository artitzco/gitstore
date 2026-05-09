# Examples

This folder keeps only the v1.0.0 directory workflow.

## Included scripts

- `upload_example.py`: encrypts `examples/sample_data`, writes `vault/sample_data_demo.asc`, updates `vault/index.json`, records local upload state, and commits only those vault files.
- `restore_example.py`: restores the remote `sample_data_demo.asc` artifact with `urllib`, `Decryptor.to_directory(...)`, and local download state.

The upload example is self-contained. The restore example expects the sample artifact to exist in the remote repository after an upload and push.
`upload_example.py` passes explicit security parameters such as `salt_size`, `iterations`, `key_length`, and `hash_name` so the settings are visible without reintroducing legacy security levels.
Both scripts use the same hard-coded password exclusively for the example.

## Sample data

- `sample_data/README.txt`: small project note.
- `sample_data/config/settings.json`: example structured file.
- `sample_data/notes/todo.txt`: nested text file to show directory packaging.

## Password

The examples use `gitstore-example-9dK4vQp2Lm7xR8sN` directly so the demo does not depend on `GITSTORE_PASSWORD`.
Use `GITSTORE_PASSWORD` or another secret source in real projects.
