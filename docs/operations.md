# Operating the application

## Local demo

Run `python -m brickline.serve --demo` and open `http://127.0.0.1:8106`. The six-property Northline account has separate Analyst (`alex`) and Reviewer (`jordan`) identities. The Other portfolio account has its own records. The demo seeds each account once; restarting preserves accepted snapshots, documents, briefs, and actions.

To start a fresh isolated demo, select a new database path with `--db runtime/fresh.db`. Existing databases are not reset automatically. Choose another local port with `--port` if 8106 is occupied.

For local generation, install Ollama and pull `qwen2.5:3b`, then pass `--model qwen2.5:3b`. `BRICKLINE_OLLAMA_URL` configures an operator-controlled endpoint; browser users cannot submit arbitrary model URLs. Provider requests time out after 60 seconds and admission is limited to two concurrent drafts per process. Failed generations preserve the verified evidence workflow with an explicit fallback.

## Container and hosted mode

`docker compose up --build` runs as UID 10001, uses a read-only root filesystem, drops capabilities, and persists `/data` in a named volume. The compose file publishes only `127.0.0.1:8106`. It explicitly enables synthetic demo identities. Do not make this demo port publicly reachable.

The image's default mode requires `BRICKLINE_KEYS_JSON` and does not seed data. Configure it through your secret manager as a JSON mapping from high-entropy keys (at least 24 characters) to objects with `tenant`, `user`, and `role` fields. Supported roles are `analyst` and `reviewer`. At least two different named users are needed for publication and brief approval. Set `BRICKLINE_DB` to a writable persistent location. A new tenant first stages and independently publishes a portfolio import through the API; the web portfolio view requires an accepted snapshot.

Before external operation, add managed identity, TLS termination, upstream request limits, secret rotation, encrypted storage/backups, monitoring, and deployment-specific review. The application does not claim that these organizational controls have been deployed. Use one API worker for the process-local model admission limit. Do not put the SQLite file on a shared network filesystem.

## Health, logging and diagnosis

- `/health` checks that the database can be opened; it exposes no portfolio data.
- `/openapi.json` describes the API; requests use the `X-API-Key` header.
- Uvicorn records HTTP access. Responses include application duration in `Server-Timing`. The activity ledger records tenant-scoped workflow events.
- A 409 means the expected version or source fingerprint changed. Reload and explicitly review the current state.
- A 422 during validation includes business-data errors. Fix the workbook, preserving explicit zero accounts and reporting months.
- A rejected model draft means provider or schema/citation checks failed. The verified figures and passages remain available.
- A stale brief withholds its body after source revision or revocation. Create a new brief; do not restore revoked text in an exported memo.

## Backup and recovery

Use SQLite's online backup API rather than copying a live WAL file. For example, connect to the configured database and a new backup path with Python `sqlite3`, then call `source.backup(destination)`. Copy the resulting backup to encrypted external storage under the deployment's retention policy. Restore into a new path, restart with that path, and compare the active dataset, portfolio figures, and latest workflow events before directing users to it.

The reproducible local study exercises backup and restoration of the seeded portfolio and a versioned action. That is a functional check, not a recovery-time or durability SLA. The current schema is version 1; future schema changes require an explicit migration and a tested backup before rollout.
