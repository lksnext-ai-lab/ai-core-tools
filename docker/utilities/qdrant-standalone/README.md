# Qdrant standalone

Qdrant aislado con su Web UI. Útil para experimentar con la base vectorial sin levantar todo el stack de Mattin AI.

## Uso

```bash
cd docker/utilities/qdrant-standalone
docker compose up -d
```

- REST API: `http://localhost:6333`
- gRPC: `localhost:6334`
- Web UI: `http://localhost:6335`

## Parar

```bash
docker compose down        # Conserva los datos
docker compose down -v     # Borra también los datos
```
