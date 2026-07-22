# Baota Compose Deployment Bundle Implementation Plan

> **For Codex:** Use the executing-plans skill to implement each task in order and stop if any validation fails.

**Goal:** Produce a server-ready Neo4j dump and secret-safe Docker Compose configuration for the existing LingJing AI image, PostgreSQL 18 dump, and Neo4j 2026.05.0 Enterprise data.

**Architecture:** Run `app`, `postgres`, and `neo4j` on one private Compose network. Persist both databases and the application's writable data in named volumes, bind public HTTP services only to loopback, and keep all credentials outside `docker-compose.yml` in ignored environment files.

**Tooling:** Docker Compose, Neo4j Admin 2026.05.0, PowerShell, Python 3.12, Git.

---

## Task 1: Establish safe preconditions

**Files:**
- Verify: `neo4j.dump`
- Verify: `docker-compose.yml`
- Verify: `.env`
- Verify: `app.env`
- Modify: `.gitignore`

1. Confirm the Neo4j Desktop DBMS process is stopped and ports 7474/7687 are not listening.
2. Confirm the source database directory `data/databases/neo4j` exists and contains files.
3. Confirm `neo4j.dump`, `docker-compose.yml`, and `app.env` do not already exist; stop rather than overwrite an unexpected artifact.
4. Read only environment/configuration key names and presence flags; never print values.
5. Copy the existing `.env` to one explicit timestamped file under `C:\tmp` and compare SHA-256 hashes before replacing it.
6. Add `app.env` and `*.dump` to `.gitignore`; retain the existing `.env` rule.

## Task 2: Export and inspect the Neo4j database

**Files:**
- Create: `neo4j.dump`

1. Launch the bundled `neo4j-admin.ps1` through a child `cmd.exe` environment where the duplicate `Path`/`PATH` entries are normalized.
2. Run `neo4j-admin database dump neo4j --to-path=<project-root>` without overwrite mode.
3. Assert the command exits successfully and `neo4j.dump` is non-empty.
4. Run `neo4j-admin database load neo4j --from-path=<project-root> --info` to verify that the archive is readable without restoring it.
5. Record only archive size, SHA-256, and non-secret metadata.

## Task 3: Generate secret files without exposing values

**Files:**
- Create temporarily: `scripts/_generate_deployment_env.py`
- Replace: `.env`
- Create: `app.env`

1. Add a temporary, secret-free generator script with `apply_patch`.
2. Read the existing `.env` and `config.yml` inside the script.
3. Preserve existing application/API/map settings in `app.env`, force `KG_ENABLED=true`, set `NEO4J_URI=bolt://neo4j:7687`, and set `REDIS_ENABLED=false` because this deployment has no Redis service.
4. Generate `.env` for Compose with `COMPOSE_PROJECT_NAME`, PostgreSQL settings, an URL-encoded container `DATABASE_URL` using host `postgres`, the fixed Neo4j Enterprise image, license acceptance, and Neo4j credentials.
5. Use atomic same-directory replacements and restrictive local file permissions where supported.
6. Print only written key names and counts, not values.
7. Delete only the single explicit temporary generator file after successful generation.

## Task 4: Create the Compose topology

**Files:**
- Create: `docker-compose.yml`

1. Define `postgres:18` with a named volume at `/var/lib/postgresql`, a health check, and no published database port.
2. Define `${NEO4J_IMAGE}` with license acceptance, authentication, database/log volumes, the read-only `neo4j.dump` bind mount, a health check, and only `127.0.0.1:7474:7474` for optional Browser access.
3. Define `lingjing-ai:2026-07-22` with `app.env`, Compose-injected `DATABASE_URL`, internal Neo4j settings, persistent `/app/data` and `/app/qdrant_db` volumes, database health dependencies, and `127.0.0.1:8000:8000`.
4. Put all three services on one private bridge network and add restart policies.
5. Keep the YAML free of literal credentials and explanatory comments limited to both purpose and rationale.

## Task 5: Validate the deployment bundle

**Files:**
- Verify: `neo4j.dump`
- Verify: `docker-compose.yml`
- Verify: `.env`
- Verify: `app.env`
- Verify: `.gitignore`

1. Parse both env files with a validator that reports only missing/duplicate keys and host/port assertions.
2. Assert the PostgreSQL URL targets `postgres:5432`, Neo4j targets `neo4j:7687`, KG is enabled, Redis is disabled, and no `DATABASE_URL` exists in `app.env`.
3. Run `docker compose config --quiet` and inspect rendered service/image/volume/port facts without printing the rendered environment.
4. Search `docker-compose.yml` for known secret values by hash-safe comparison and assert no match.
5. Run `git check-ignore` for `.env`, `app.env`, and `neo4j.dump`.
6. Run focused application settings tests to ensure the new deployment files do not change source behavior.
7. Report file sizes, hashes where useful, validation results, and the external `.env` backup path.

## Task 6: Record the change

**Files:**
- Modify: `daily-modify/2026-07-22.md`

1. Add a daily modification entry listing the deployment artifacts and why they were generated.
2. Re-run the final validation commands after the log change.
3. Leave unrelated user changes untouched and do not stage or commit deployment secrets or dump files.
