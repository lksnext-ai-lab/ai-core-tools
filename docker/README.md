# Despliegue Docker single-host

Despliegue con **Caddy** como reverse proxy. Sirve tanto para **desarrollo local** en el portátil como para **servidores cliente** (demos, formaciones, pilotos). La única diferencia entre escenarios es el contenido del `.env`.

## Arquitectura

```
Usuario
  │
  ▼
[ Caddy :80 ]  ← único puerto expuesto al host
  │
  ├── /internal/*, /public/*, /mcp/*, /docs/*, /scalar, /static/*, /openapi-*.json, /health
  │        └─► backend:8000
  │
  └── resto (SPA)
           └─► frontend:80

Red interna de Docker (mattin-network):
  postgres:5432 ← sin publicar al host
  qdrant:6333   ← sin publicar al host
```

Frontend y backend viajan por el mismo origen → **sin CORS**, sin necesidad de rebuildear el frontend entre entornos (`VITE_API_BASE_URL=""` usa rutas relativas).

## Dos formas de obtener las imágenes

| | Opción A — Pull desde GHCR | Opción B — Build en local |
|---|---|---|
| Cuándo | Cliente, demos, CI de producción | Dev local con cambios de código |
| Qué hace | Descarga las imágenes prebuildeadas del registry público | Construye `backend` y `frontend` desde los Dockerfiles del repo |
| Ventaja | Rápido, determinista, no necesita código fuente | Incluye tus cambios locales sin publicar |
| Comando | `docker compose pull && docker compose up -d` | `docker compose up -d --build` |

Las imágenes publicadas viven en:
- `ghcr.io/lksnext-ai-lab/mattinai-backend:${IMAGE_TAG}`
- `ghcr.io/lksnext-ai-lab/mattinai-frontend:${IMAGE_TAG}`

El tag por defecto es `develop` (último build de la rama `develop`). En servidores de cliente se recomienda **pinear un SHA** (`IMAGE_TAG=sha-c1feaaf`) para evitar actualizaciones accidentales al hacer `docker compose pull`.

## Uso

### A. Despliegue tirando de GHCR (recomendado para cliente)

```bash
cd docker
cp .env.example .env
# Editar .env:
#   FRONTEND_URL=http://<ip-o-dominio>
#   DATABASE_PASSWORD=<robusta>
#   SECRET_KEY=<hex aleatorio>
#   AICT_OMNIADMINS=<emails del cliente>
#   OPENAI_API_KEY=<...>
#   IMAGE_TAG=sha-<commit>   # o "develop" para el último
docker compose pull backend frontend
docker compose up -d
```

Accede a `http://<ip-del-servidor>/` (o `http://localhost/` en local).
Pide al administrador de red del cliente que abra el **80/tcp** hacia el servidor.

> Si las imágenes del registry son privadas, autentícate antes con
> `docker login ghcr.io -u <usuario-github>` usando un Personal Access Token
> con scope `read:packages`.

### B. Dev local con cambios de código

```bash
cd docker
cp .env.example .env
# Editar .env: OPENAI_API_KEY, AICT_OMNIADMINS, SECRET_KEY, DATABASE_PASSWORD
docker compose up -d --build
```

`--build` reconstruye las imágenes desde los Dockerfiles y las etiqueta como
`ghcr.io/lksnext-ai-lab/mattinai-backend:develop` (queda local, no se publica).

Accede a `http://localhost/`.

## Comandos habituales

```bash
# Ver estado
docker compose ps

# Logs en vivo (todos)
docker compose logs -f

# Logs solo del backend
docker compose logs -f backend

# Reiniciar un servicio concreto
docker compose restart backend

# Parar
docker compose down

# Parar y BORRAR volúmenes (¡se pierden datos!)
docker compose down -v

# Rebuild tras cambios de código (opción B)
docker compose up -d --build

# Actualizar a la última imagen publicada (opción A)
docker compose pull backend frontend
docker compose up -d
```

## Primer login (modo FAKE)

En `AICT_LOGIN=FAKE` el usuario debe existir previamente en la tabla `"User"`. Tras el primer `up`:

```bash
docker exec -it mattin-postgres psql -U mattin -d mattin_ai -c \
  "INSERT INTO \"User\" (email, name, create_date, is_active, auth_method, email_verified)
   VALUES ('tu@email.com', 'Tu Nombre', NOW(), true, 'dev', true);"
```

Para insertar varios de golpe:

```bash
docker exec -i mattin-postgres psql -U mattin -d mattin_ai <<EOF
INSERT INTO "User" (email, name, create_date, is_active, auth_method, email_verified) VALUES
  ('user1@cliente.com', 'User 1', NOW(), true, 'dev', true),
  ('user2@cliente.com', 'User 2', NOW(), true, 'dev', true)
ON CONFLICT DO NOTHING;
EOF
```

## Acceso a la base de datos desde fuera

Postgres **no** está publicado al host por seguridad. Tres formas de acceder:

1. **Desde el servidor, psql del contenedor** (rápido):
   ```bash
   docker exec -it mattin-postgres psql -U mattin -d mattin_ai
   ```

2. **Tunel SSH desde tu equipo** (recomendado para DBeaver/pgAdmin):
   ```bash
   ssh -L 5432:localhost:5432 usuario@<ip-servidor>
   ```
   Requiere añadir `ports: ["127.0.0.1:5432:5432"]` al servicio postgres del compose.

3. **DBeaver con tunel SSH integrado**: en la conexión Postgres configura la pestaña SSH con el host del servidor. Sin publicar ningún puerto.

## Paso a HTTPS

Cuando el cliente tenga dominio interno y abra el 443:

1. Edita el `Caddyfile`:
   ```
   mattinai.cliente.local {
       tls internal    # cert de la CA interna de Caddy (autofirmado)
       encode zstd gzip
       @backend path /internal/* /public/* /mcp/* /docs/* /scalar /openapi-*.json /static/* /health
       handle @backend { reverse_proxy backend:8000 }
       handle { reverse_proxy frontend:80 }
   }
   ```
2. En el compose, publica también el 443:
   ```yaml
   caddy:
     ports:
       - "80:80"
       - "443:443"
   ```
3. Si el cliente tiene PKI corporativa, monta el cert del cliente en el contenedor y sustituye `tls internal` por `tls /etc/caddy/cert.pem /etc/caddy/key.pem`.

## Utilities aisladas

En [`utilities/`](./utilities/) hay compose files para servicios aislados que no forman parte del stack principal (p. ej. Qdrant standalone con su web UI para experimentación).

## Para producción seria (K8s)

Este despliegue es para **single-host**: dev local, POCs, pilotos, demos de cliente. Para producción con alta disponibilidad, múltiples réplicas, TLS automático con Let's Encrypt, backups gestionados, etc., usar los Helm charts en el repo `mattinai-infra`.
