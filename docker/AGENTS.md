# AGENTS.md — Docker / local deployment

Applies to `docker/`. Inherits the root `AGENTS.md`.

Single-host deployment with **Caddy** as reverse proxy. The same setup serves local development and client servers — only `.env` changes.

```bash
cd docker
cp .env.example .env          # set keys and AICT_OMNIADMINS
docker compose up -d --build
docker compose logs -f backend
docker compose down -v        # stops and destroys volumes
```

Services: `caddy`, `backend`, `frontend`, `postgres`, `qdrant`, plus `db_test` under the `test` profile. Isolated utilities (Qdrant web UI and similar) live in `docker/utilities/`.

## Invariants

- **Only one host port is published** (Caddy, `${HTTP_PORT}`, default 80). Backend, frontend, Postgres and Qdrant stay on the internal network. Do not add host port mappings to those services.
- **No `container_name:` on any service.** Several stacks run side by side on a dev machine (see below); a fixed container name makes the second one fail to start. Let Compose derive names from the project name, and reference services by service name (`docker compose exec backend ...`), never by container name.
- Access: `http://localhost/` locally, `http://<server-ip>/` on a client host. Swagger at `/docs/internal` and `/docs/public` from the same origin.
- `.env` is never committed. Change `.env.example` when you add a variable, and document it in the root `AGENTS.md` / `CLAUDE.md` env section.
- `db_test` belongs to the `test` profile and must not start with the default `up`.

## Local multi-environment

A dev machine runs several Mattin versions at once (demo on `:develop`, a working-tree build, a client's pinned tag). The isolation unit is the Compose **project name**, which prefixes containers, networks and volumes. Each environment is an `envs/<name>.env` layered over `envs/base.env`, driven by `mattin.ps1`; see `README.md` § "Varios Mattin a la vez".

This constrains changes here:

- Anything that must differ per environment goes through a variable in `envs/*.env`, never hardcoded in `docker-compose.yaml`.
- New named volumes are automatically per-environment. New **bind mounts** are not — they are shared by every stack on the host, so gate them behind a variable with the bind path as default (see `BACKEND_DATA`).
- Resources named outside the project namespace (the `sandbox-workloads` network) are shared across stacks. Adding another means adding another collision. `mattin-code-interpreter` and `mattin-opensandbox-server` are namespaced via `IMAGE_TAG` like backend/frontend (see below), not an outside-namespace collision on their own.
- `IMAGE_TAG` is what keeps a local `--build` from overwriting a published image — this now applies to all four images published from this repo (backend, frontend, opensandbox-server, code-interpreter; see `.github/workflows/opensandbox-ci.yml`). Do not default a work environment to `develop`.

## Rules

- Multi-stage builds; keep runtime images slim. Do not install build toolchains into the runtime stage.
- Pin base image tags — no floating `latest`.
- Run as a non-root user in the runtime stage.
- Secrets arrive through environment variables or mounted files, never baked into a layer and never in an `ARG`.
- Named volumes for Postgres and Qdrant data; deleting a volume is destructive — confirm before suggesting `down -v`.
- Healthchecks on every long-running service; `depends_on` with `condition: service_healthy` where startup order matters.
- Keep `.dockerignore` aligned with what the build actually needs — it is the main lever on build context size.
- Caddyfile changes: validate the config and keep the reverse-proxy routes consistent with the frontend router's base paths.

Verify Compose and Caddy directive syntax with the Context7 MCP rather than from memory.
