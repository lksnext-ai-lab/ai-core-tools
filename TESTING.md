# Testing

Guia de testing para AI Core Tools. Cubre la arquitectura de tests, cómo ejecutarlos y las medidas de seguridad para proteger la base de datos de desarrollo.

## Requisitos

- Python 3.11+
- Poetry (dependencias de test en grupo `test`)
- Docker (para la base de datos de test)

Instalar dependencias de test:

```bash
poetry install --with test
```

## Estructura de tests

```
tests/
├── conftest.py                          # Fixtures globales (DB, client, auth, auto-markers)
├── factories.py                         # Factories (factory-boy) para generar datos de test
├── integration/                         # Tests de integración (requieren BD)
│   ├── export_import/                   # Tests de export/import
│   │   └── conftest.py                  # Fixtures específicas de export/import
│   ├── routers/
│   │   ├── internal/                    # Tests de endpoints internos
│   │   └── public/                      # Tests de endpoints públicos
│   └── services/                        # Tests de servicios con BD
└── unit/                                # Tests unitarios (sin BD)
    ├── routers/                         # Tests de capa de routing
    ├── schemas/                         # Tests de validación de schemas
    ├── services/                        # Tests de lógica de negocio
    └── utils/                           # Tests de utilidades
```

## Tipos de tests

### Unit tests (`tests/unit/`)

No requieren base de datos ni servicios externos. Testean lógica de negocio, validaciones de schemas y separación de capas usando mocks.

```bash
pytest -m unit
```

### Integration tests (`tests/integration/`)

Requieren una base de datos PostgreSQL de test. Testean flujos completos a través de la API: autenticación, autorización (RBAC/IDOR), operaciones CRUD, y export/import.

```bash
pytest -m integration
```

Los markers `unit` e `integration` se aplican automáticamente según el directorio del fichero de test.

## Cómo ejecutar tests

### Opción 1: Script automático (recomendado)

El script levanta la BD de test, ejecuta pytest y para la BD al terminar:

```bash
# Todos los tests
./scripts/test.sh

# Solo unit tests (no levanta BD)
./scripts/test.sh -m unit

# Solo integration tests
./scripts/test.sh -m integration

# Tests con coverage
./scripts/test.sh --cov=backend --cov-report=html

# Tests que coincidan con un patrón
./scripts/test.sh -k test_agents_authorization
```

### Opción 2: Manual con Docker Compose

```bash
# 1. Levantar la BD de test (puerto 5433, datos efímeros con tmpfs)
docker compose --profile test up -d db_test

# 2. Ejecutar tests
pytest

# 3. Parar la BD de test
docker compose --profile test stop db_test
```

### Opción 3: Solo unit tests (sin Docker)

```bash
pytest -m unit
```

No necesita base de datos. Ideal para feedback rápido durante el desarrollo.

## Base de datos de test

La BD de test es un contenedor PostgreSQL independiente, definido en `docker-compose.yaml` bajo el perfil `test`:

| Propiedad | Valor |
|-----------|-------|
| Puerto | **5433** (dev usa 5432) |
| Base de datos | `test_db` |
| Usuario | `test_user` |
| Contraseña | `test_pass` |
| Almacenamiento | `tmpfs` (se borra al parar el contenedor) |
| Imagen | `pgvector/pgvector:pg17` |

La BD de test **nunca** se levanta con `docker compose up` normal — requiere `--profile test`.

## Aislamiento de datos entre tests

Cada test se ejecuta dentro de una transacción de conexión con `SAVEPOINT`:

1. Se abre una transacción (`BEGIN`)
2. La sesión de SQLAlchemy usa `join_transaction_mode="create_savepoint"` — los `session.commit()` del código de producción emiten `SAVEPOINT` en vez de `COMMIT`
3. Al terminar el test, se hace `ROLLBACK` de toda la transacción
4. Ningún dato persiste entre tests

Esto permite testear flujos completos (incluyendo commits del código de producción) sin efectos secundarios.

## Protecciones contra la BD de desarrollo

El sistema tiene tres niveles de protección para evitar que los tests toquen la BD de desarrollo:

### 1. Validación de URL

`conftest.py` valida que `TEST_DATABASE_URL` no apunte a la BD de desarrollo antes de ejecutar nada:

- Rechaza URLs con puerto `5432`
- Rechaza URLs que contengan nombres de BD de desarrollo (`mattin_ai`, `iacore`)

### 2. Forzado de variable de entorno

Antes de importar cualquier módulo de backend, `conftest.py` sobreescribe `SQLALCHEMY_DATABASE_URI` con la URL de test. Esto previene que `database.py` (que crea el engine al importarse) se conecte a la BD de desarrollo.

### 3. Verificación runtime

El fixture `test_engine` ejecuta `SELECT current_database()` después de conectar y **aborta** si el nombre de la BD no es `test_db` o `mattin_test_temp`.

## Cuándo ejecutar tests

| Momento | Qué ejecutar | Comando |
|---------|-------------|---------|
| Durante desarrollo | Unit tests | `pytest -m unit` |
| Antes de push | Todos los tests | `./scripts/test.sh` |
| CI/CD (Jenkins) | Todos los tests | Automático (stage "Run Tests") |

## CI/CD (Jenkins)

El `Jenkinsfile` incluye un stage **"Run Tests"** que se ejecuta antes de construir las imágenes Docker:

1. Levanta un contenedor PostgreSQL efímero con `tmpfs`
2. Construye una imagen de test runner (`backend/Dockerfile.test`)
3. Ejecuta pytest con JUnit XML y coverage XML
4. Publica resultados en la UI de Jenkins
5. Alimenta el reporte de coverage a SonarQube
6. Limpia contenedores e imágenes

Si los tests fallan, el pipeline se detiene y no se construyen ni despliegan imágenes.

## Escribir nuevos tests

### Test unitario

Colocar en `tests/unit/`. No necesita fixtures de BD:

```python
# tests/unit/services/test_my_service.py

class TestMyService:
    def test_something(self):
        result = my_function("input")
        assert result == "expected"
```

### Test de integración

Colocar en `tests/integration/`. Usar los fixtures `db`, `client`, `owner_headers`:

```python
# tests/integration/routers/internal/test_my_endpoint.py

class TestMyEndpoint:
    def test_authorized_access(self, client, owner_headers, fake_app):
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/my-endpoint",
            headers=owner_headers,
        )
        assert response.status_code == 200

    def test_unauthorized_access(self, client, auth_headers, fake_app):
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/my-endpoint",
            headers=auth_headers,  # user sin rol en fake_app
        )
        assert response.status_code == 403
```

### Fixtures disponibles

| Fixture | Scope | Descripción |
|---------|-------|-------------|
| `db` | function | Sesión de BD con rollback automático |
| `client` | function | `TestClient` de FastAPI con `get_db` sobreescrito |
| `fake_user` | function | Usuario de test |
| `fake_app` | function | App de test (propiedad de `fake_user`) |
| `fake_agent` | function | Agente de test en `fake_app` |
| `fake_ai_service` | function | Servicio AI de test |
| `fake_api_key` | function | API key de test |
| `auth_headers` | function | Headers con Bearer token para `fake_user` |
| `owner_headers` | function | Headers con Bearer token + rol OWNER en `fake_app` |

### Factories disponibles

Definidas en `tests/factories.py` (factory-boy):

- `UserFactory`
- `AppFactory`
- `AIServiceFactory`
- `AgentFactory`
- `APIKeyFactory`
- `AppCollaboratorFactory`

Uso:

```python
from tests.factories import UserFactory, AppFactory, configure_factories

def test_with_factories(db):
    configure_factories(db)
    user = UserFactory(email="custom@test.com")
    app = AppFactory(owner=user)
```
