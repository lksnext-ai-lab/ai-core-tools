# Diseño técnico: Agentes periódicos en Mattin AI sobre DBOS

**Proyecto:** Mattin AI (`lksnext-ai-lab/ai-core-tools`)
**Funcionalidad:** Ejecución periódica de agentes
**Motor de orquestación propuesto:** DBOS (embebido, biblioteca Python sobre PostgreSQL)
**Estado:** Superseded — ver `cambios-tareas-programadas.md`
**Relacionado con:** RFC `rfc-sandbox-providers.md` (rama `exp/sandbox`)

> Este diseño histórico queda sustituido por [`cambios-tareas-programadas.md`](cambios-tareas-programadas.md): la entidad de primer nivel es `ScheduledTask`, y sus ejecuciones se representan mediante conversaciones existentes.

---

## 1. Resumen ejecutivo

Se propone incorporar **DBOS** como motor de durabilidad y scheduling para soportar la ejecución periódica de agentes en Mattin AI. DBOS es una librería Python que se importa dentro del propio proceso del backend FastAPI y usa **PostgreSQL como única dependencia externa** (la misma base de datos ya utilizada por Mattin AI, en un esquema/base de datos lógica propia).

Esto implica que la funcionalidad se soporta:
- Sin ningún control plane ni servicio adicional que desplegar.
- Sin comunicación de red entre "worker" y "motor de orquestación": ambos viven en el mismo proceso.
- Sin gestión ni rotación de tokens de autenticación adicionales: la única credencial relevante es la propia cadena de conexión a Postgres.
- Sin contenedores nuevos en `docker-compose.yml`.

La arquitectura de dominio (modelo de datos de negocio, capa adaptadora, API REST, integración con el sandbox provider del RFC `exp/sandbox`) sigue el principio de aislamiento: el motor de orquestación queda encapsulado detrás de una capa de servicio propia, de forma que el resto del sistema (API, frontend, lógica de negocio de los agentes) no depende de los detalles internos de DBOS.

---

## 2. Contexto y objetivo

Mattin AI ya soporta la definición de agentes (LLM + RAG + Skills + MCP) ejecutados de forma síncrona, iniciados por el usuario o por eventos de la aplicación (chat, API). El objetivo de esta funcionalidad es añadir un **tercer modo de disparo: temporal/periódico**, de forma que un agente configurado por un usuario se ejecute automáticamente cada cierto intervalo (ej. "cada hora", "cada día a las 8:00", "cada 15 minutos") sin intervención manual.

### 2.1 Objetivos de diseño

- Permitir crear, pausar, reanudar, modificar y eliminar la programación de un agente desde la UI y desde la API, sin necesidad de redeploy.
- Garantizar que un fallo puntual (timeout de LLM, caída de un proveedor externo, reinicio del proceso) no pierda la ejecución: debe reintentarse de forma controlada.
- Dar visibilidad al usuario final de qué ejecuciones se han producido, su resultado y su duración.
- Evitar que un tenant con muchos agentes periódicos consuma recursos de forma desproporcionada frente a otros tenants (fairness).
- Reutilizar en la medida de lo posible la infraestructura ya desplegada (Postgres, Docker Compose).
- No acoplar la lógica de negocio del agente al motor de orquestación.

### 2.2 Fuera de alcance

- Orquestación de flujos multi-agente complejos con dependencias entre agentes (se deja para una fase posterior, reutilizando la misma infraestructura).
- Migración de la ejecución de agentes síncronos (chat) al mismo mecanismo de durabilidad — esta propuesta se limita a la ejecución periódica.
- Alta disponibilidad multi-región del componente de scheduling.

---

## 3. Arquitectura actual (resumen relevante)

| Componente | Tecnología |
|---|---|
| Backend | FastAPI (Python), Poetry, Alembic |
| Frontend | React + TypeScript |
| Persistencia | PostgreSQL + pgvector |
| Despliegue | Docker Compose, reverse proxy Caddy, imágenes en GHCR |
| Autenticación | OIDC (Entra ID) en producción, modo `FAKE` en desarrollo |
| Ejecución de agentes | LLM providers (OpenAI, Anthropic, Azure OpenAI, Mistral, Ollama) + RAG + MCP |
| En desarrollo | Arquitectura de Skills + sandbox provider (RFC `rfc-sandbox-providers.md`, rama `exp/sandbox`), integrando OpenSandbox/LangGraph |

Actualmente no existe ningún componente de scheduling ni de ejecución en segundo plano: toda ejecución de agente es iniciada síncronamente por una petición HTTP. El backend ya es un proceso Python de larga duración (Uvicorn), condición necesaria para embeber DBOS en él.

---

## 4. Arquitectura propuesta

### 4.1 Vista de componentes

```mermaid
flowchart TB
    subgraph UI["Frontend (React)"]
        A1[Editor de Agente]
        A2[Panel de Programación]
        A3[Historial de Ejecuciones]
    end

    subgraph BE["Backend Mattin AI (FastAPI + DBOS embebido)"]
        B1[API REST: /agents/:id/schedule]
        B2[Servicio de Scheduling<br/>agent_scheduler_service.py]
        B3[DBOS runtime<br/>en el mismo proceso Uvicorn]
        B4["@DBOS.workflow periodic_agent_run"]
        B5[Servicio de ejecución de agentes<br/>ya existente]
    end

    subgraph SANDBOX["Sandbox Provider (RFC exp/sandbox)"]
        S1[OpenSandbox / LangGraph]
        S2[Skills]
    end

    subgraph DB["PostgreSQL Mattin AI"]
        D1[(agents, agent_schedules,<br/>agent_run_summary)]
        D2[(pgvector)]
        D3[(esquema 'dbos':<br/>workflow_status, workflow_schedules)]
    end

    A2 -->|crear/pausar/editar schedule| B1
    A3 -->|consultar historial| B1
    B1 --> B2
    B2 -->|DBOS.apply_schedules / pause / resume| B3
    B3 -->|dispara en cron, en el mismo proceso| B4
    B4 -->|invoca| B5
    B5 -->|ejecuta Skill| S1
    S1 --> S2
    B4 -->|persiste resultado resumido| D1
    B3 -->|checkpointing de estado| D3
    B5 -.->|lee contexto agente| D1
    B5 -.-> D2
```

No hay ningún componente nuevo desplegado: DBOS vive dentro del proceso `backend`, y su estado se guarda en un esquema (`dbos`) dentro del mismo servidor PostgreSQL ya usado por Mattin AI, o en una base de datos lógica separada dentro de esa misma instancia (ver §5.2).

### 4.2 Principio de diseño: aislamiento del dominio frente al motor de orquestación

**DBOS no conoce el modelo de dominio de Mattin AI**. Su responsabilidad se limita a: ejecutar la función periódica con garantías de "exactamente una vez por intervalo", checkpointing de su estado, y reintentos configurables. Toda la lógica de negocio (qué agente ejecutar, con qué contexto, qué Skills invocar, cómo interpretar el resultado) vive en el backend de Mattin AI, en una capa de servicio que actúa como **adaptador**.

Esto permite:
- Sustituir el motor de orquestación en el futuro sin tocar la lógica de agentes.
- Testear la lógica de ejecución de un agente sin depender del runtime de scheduling (mockeando el adaptador).
- Mantener el modelo de permisos y multi-tenancy de Mattin AI como fuente de verdad.

Se establece como regla de código: **solo el módulo `backend/scheduling/periodic_agent_task.py` importa `dbos`** directamente. Ningún otro módulo del backend debe hacerlo, para evitar que la lógica de negocio quede acoplada a los decoradores del runtime en puntos dispersos del código.

---

## 5. Diseño detallado

### 5.1 Modelo de datos (Mattin AI)

Nuevas tablas (migraciones Alembic):

```sql
-- Programación de un agente periódico
CREATE TABLE agent_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    orchestrator_schedule_name TEXT NOT NULL UNIQUE, -- identificador determinista, ver 5.5
    cron_expression TEXT NOT NULL,                    -- p.ej. '0 8 * * *'
    timezone TEXT NOT NULL DEFAULT 'UTC',
    input_context JSONB,                              -- contexto fijo que recibe el agente en cada tick
    status TEXT NOT NULL DEFAULT 'active',             -- active | paused | deleted
    max_concurrent_runs INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resumen local de ejecuciones, propiedad de Mattin AI, independiente del
-- motor de orquestación subyacente
CREATE TABLE agent_run_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_schedule_id UUID NOT NULL REFERENCES agent_schedules(id) ON DELETE CASCADE,
    orchestrator_run_id TEXT NOT NULL,
    scheduled_time TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,   -- queued | running | succeeded | failed | retrying
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    output_summary JSONB
);

CREATE INDEX idx_agent_run_summary_schedule ON agent_run_summary(agent_schedule_id, scheduled_time DESC);
```

**Por qué un espejo local (`agent_run_summary`) en vez de consultar el estado interno del runtime en cada petición del frontend:**
- Evita acoplar la UI de Mattin AI a las tablas internas del motor de orquestación.
- Permite aplicar el modelo de permisos de Mattin AI (un usuario solo ve el historial de su workspace) sin exponer detalles internos del runtime a los usuarios finales.
- Simplifica agregaciones y filtros propios de negocio (ej. "agentes con más fallos esta semana").
- Mantiene la posibilidad de cambiar de motor de orquestación en el futuro sin migrar ni reinterpretar el histórico expuesto al usuario.

### 5.2 Infraestructura

No se añade ningún servicio nuevo al `docker-compose.yml`. Los únicos cambios de infraestructura son:

```yaml
services:
  backend:
    # servicio ya existente — sin contenedores nuevos
    environment:
      DBOS_DATABASE_URL: postgresql://mattin:${DATABASE_PASSWORD}@postgres:5432/mattin_ai_dbos
    depends_on: [postgres]
```

DBOS crea y gestiona sus propias tablas internas (`workflow_status`, `workflow_schedules`, `operation_outputs`, etc.) mediante sus propias migraciones automáticas al arrancar. Se recomienda:

- Una **base de datos lógica dedicada** (`mattin_ai_dbos`) en el mismo servidor Postgres que ya operáis, para no mezclar el ciclo de vida/migraciones internas de DBOS con el esquema Alembic de Mattin AI, evitando conflictos de nombres de tabla y facilitando el backup diferenciado del historial de ejecuciones (más volátil) frente a los datos de negocio.
- No es obligatorio un servidor Postgres físicamente distinto: al no haber un motor de orquestación externo con necesidades de rendimiento propias, compartir instancia física reduce la superficie operativa. Si el volumen de ejecuciones periódicas crece mucho, se puede migrar esa base de datos lógica a una instancia separada sin cambios de código (solo la cadena de conexión).

### 5.3 Dónde vive el código de ejecución

El runtime de DBOS se inicializa una vez por proceso Python (`DBOS()` / `DBOS.launch()` en el ciclo de arranque de FastAPI, típicamente en el evento `startup`). Si en el futuro se necesita escalar la ejecución de agentes independientemente de la API HTTP, la vía es:

- Levantar una **segunda instancia del mismo backend** (misma imagen, mismo código) dedicada solo a ejecutar workflows, sin exponer el puerto HTTP público, apuntando a la misma base de datos DBOS. El checkpointing en Postgres es lo que permite que cualquier proceso recupere/continúe una ejecución, así que múltiples réplicas pueden coordinarse sobre la misma base de datos sin trabajo adicional.
- Esto se deja preparado como nota de escalabilidad para una fase posterior, no como parte del alcance inicial: no requiere cambiar el comando de arranque del contenedor, solo desplegar una réplica adicional.

### 5.4 Separación entre orquestación durable y pasos con efectos externos

DBOS distingue entre `@DBOS.workflow()` (orquestación durable, determinista) y `@DBOS.step()` (para las llamadas "impuras": al LLM, al sandbox provider, a APIs externas). Se recomienda envolver la invocación al servicio de ejecución de agentes —o, como mínimo, la llamada al sandbox provider dentro de ella— como un `@DBOS.step()` explícito, para que sus reintentos se gestionen de forma independiente del resto del workflow.

```python
# backend/scheduling/periodic_agent_task.py
from datetime import datetime
from dbos import DBOS

@DBOS.step(retries_allowed=True, max_attempts=3, interval_seconds=5, backoff_rate=2.0)
async def invoke_agent_step(agent_id: str, workspace_id: str, input_context: dict):
    return await agent_execution_service.run_agent(
        agent_id=agent_id, workspace_id=workspace_id, trigger="scheduled", context=input_context,
    )


@DBOS.workflow(max_recovery_attempts=3)
async def periodic_agent_run(scheduled_time: datetime, actual_time: datetime, agent_schedule_id: str):
    # El contexto de negocio (agent_id, workspace_id, input_context) se recupera
    # desde agent_schedules usando agent_schedule_id, en vez de pasarse como
    # argumento libre — así el workflow es reproducible ante reintentos
    # (idempotencia: misma entrada -> mismo resultado esperado)
    schedule = await agent_schedule_repo.get(agent_schedule_id)

    run_summary = await agent_run_service.start_run(
        schedule_id=agent_schedule_id,
        orchestrator_run_id=DBOS.workflow_id,
        scheduled_time=scheduled_time,
    )

    try:
        result = await invoke_agent_step(
            agent_id=schedule.agent_id,
            workspace_id=schedule.workspace_id,
            input_context=schedule.input_context,
        )
        await agent_run_service.mark_succeeded(run_summary.id, output=result)
        return result

    except Exception as exc:
        await agent_run_service.mark_failed(run_summary.id, error=str(exc))
        raise
```

### 5.5 Registro y gestión de la programación (cron dinámico)

DBOS permite registrar y modificar schedules en caliente contra una tabla propia (`workflow_schedules`), sin necesidad de reiniciar el proceso:

```python
# backend/scheduling/agent_scheduler_service.py
from dbos import DBOS

class AgentSchedulerService:

    async def create_schedule(self, agent_id, workspace_id, cron_expression, timezone, input_context, created_by):
        # 1. Validar permisos del usuario sobre el agente/workspace
        # 2. Validar la expresión cron y límites de negocio
        #    (frecuencia mínima según plan del tenant)
        schedule = await self.repo.create(
            agent_id=agent_id, workspace_id=workspace_id, cron_expression=cron_expression,
            timezone=timezone, input_context=input_context, created_by=created_by,
        )

        # 3. Registrar el schedule en DBOS (tabla workflow_schedules)
        DBOS.apply_schedules([{
            "schedule_name": schedule.orchestrator_schedule_name,  # f"agent-schedule-{schedule.id}"
            "workflow_fn": periodic_agent_run,
            "schedule": cron_expression,
            "cron_timezone": timezone,
            "context": str(schedule.id),  # agent_schedule_id, recuperado dentro del workflow
        }])
        return schedule

    async def pause_schedule(self, schedule_id):
        # DBOS permite pausar/reanudar schedules por nombre sin recrearlos
        ...

    async def resume_schedule(self, schedule_id): ...
    async def delete_schedule(self, schedule_id): ...
    async def update_schedule(self, schedule_id, **changes):
        # apply_schedules es idempotente por schedule_name: actualiza si ya
        # existe, en vez de duplicar
        ...
```

**Ventaja operativa relevante:** como los schedules se guardan en una tabla de Postgres y no en la configuración de arranque de un proceso externo, sobreviven a redeploys del backend sin ninguna acción adicional — un hilo interno de DBOS los recarga periódicamente.

### 5.6 API REST expuesta al frontend

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/agents/{agent_id}/schedules` | Crea una programación periódica |
| `GET` | `/agents/{agent_id}/schedules` | Lista las programaciones del agente |
| `PATCH` | `/agents/{agent_id}/schedules/{schedule_id}` | Modifica cron, contexto o estado (pausar/reanudar) |
| `DELETE` | `/agents/{agent_id}/schedules/{schedule_id}` | Elimina la programación |
| `GET` | `/agents/{agent_id}/schedules/{schedule_id}/runs` | Historial paginado de ejecuciones (lee `agent_run_summary`) |

Estos endpoints solo hablan con `AgentSchedulerService` y el repositorio de `agent_run_summary`; nunca exponen identificadores internos del runtime al frontend. Al estar la API completamente desacoplada del motor de orquestación, el diseño de UI (pantallas, componentes, estados) definido para esta funcionalidad es válido sin modificaciones.

### 5.7 Multi-tenancy, fairness y límites

Para evitar que un tenant con muchos agentes periódicos consuma recursos de forma desproporcionada, se propone:

- **DBOS Queues por workspace:** colas persistentes en Postgres con `concurrency_limit` configurable. Cada workspace obtiene una cola lógica acorde a su plan, y `invoke_agent_step` se encola en ella en vez de ejecutarse directamente, garantizando que ningún tenant monopoliza la capacidad de ejecución.
- **Rate limiting dinámico por tenant:** comprobación explícita en `AgentSchedulerService.create_schedule` (recuento de ejecuciones del workspace en la última ventana temporal, usando `agent_run_summary`) antes de permitir una nueva programación o de lanzar una ejecución.
- **Frecuencia mínima permitida:** validación de negocio en `AgentSchedulerService` (por ejemplo, no permitir cron de menos de 1 minuto en tiers no-enterprise), independiente de lo que el runtime permitiría técnicamente.
- **Aislamiento de fallos:** `max_attempts` a nivel de step (§5.4) más el límite de concurrencia por cola aseguran que ningún agente "atascado" compite indefinidamente por todos los recursos disponibles.

### 5.8 Observabilidad para el usuario final

- El panel "Historial de Ejecuciones" en el frontend consulta `GET /agents/{id}/schedules/{id}/runs`, que lee de `agent_run_summary`.
- El propio workflow (`periodic_agent_run`) mantiene esta tabla sincronizada en cada transición de estado (inicio, éxito, fallo), sin necesidad de que el frontend consulte tablas internas del runtime.
- Para uso interno del equipo de plataforma (depuración de incidencias, revisión de reintentos), se recomienda construir una vista de administración ligera dentro del propio backoffice de Mattin AI sobre la misma tabla `agent_run_summary`, enriquecida si es necesario con el detalle técnico del error (campo no expuesto a usuarios finales).

### 5.9 Seguridad

- La única credencial relevante para esta funcionalidad es la cadena de conexión a Postgres (`DBOS_DATABASE_URL`), gestionada con el mismo mecanismo de secretos que el resto de la aplicación — no se introduce ninguna credencial de tipo nuevo.
- No hay superficie de red adicional que asegurar: no existe ningún puerto ni servicio nuevo expuesto entre contenedores.
- El proceso que ejecuta los workflows comparte el mismo contexto de credenciales de proveedores LLM y acceso al sandbox provider que el resto del backend — no se introducen nuevas superficies de credenciales.
- Los `input_context` de cada schedule pueden contener datos de negocio del workspace: se persisten cifrados en reposo si el resto del esquema de Mattin AI ya aplica ese estándar (alinear con la política de datos existente).

---

## 6. Plan de implementación por fases

| Fase | Alcance | Entregable |
|---|---|---|
| **0. Spike** | Añadir `dbos` como dependencia del backend, probar un `@DBOS.workflow()` programado en local contra la Postgres de desarrollo | Confirmar viabilidad técnica y curva de aprendizaje del SDK |
| **1. Infraestructura** | Crear la base de datos lógica `mattin_ai_dbos`; añadir `DBOS_DATABASE_URL` a la configuración de todos los entornos | Sin contenedores nuevos que desplegar |
| **2. Modelo de datos y servicio adaptador** | Migraciones Alembic (`agent_schedules`, `agent_run_summary`) + `AgentSchedulerService` + workflow `periodic_agent_run` + step `invoke_agent_step` | Backend capaz de crear/pausar schedules vía código, sin UI |
| **3. API REST** | Endpoints de §5.6, con validaciones de negocio y permisos | API completa, testeable con pytest |
| **4. Frontend** | Panel de programación en el editor de agente + historial de ejecuciones | Funcionalidad visible para el usuario final |
| **5. Multi-tenancy y límites** | DBOS Queues por workspace + validación de frecuencia mínima | Producción-ready para múltiples tenants |
| **6. Observabilidad interna** | Vista de administración ligera sobre `agent_run_summary`, alertas (Slack/PagerDuty) sobre fallos repetidos de un schedule | Soporte operativo |

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Ausencia de dashboard nativo dificulta la depuración de incidencias complejas | Instrumentar `agent_run_summary` con suficiente detalle (número de intento, error completo en un campo aparte no expuesto a usuarios finales) desde el principio |
| Fairness multi-tenant requiere código propio explícito | Priorizar la Fase 5 (DBOS Queues por workspace) antes de abrir la funcionalidad a todos los tenants, no dejarla como mejora futura |
| Acoplar el proceso de negocio al mismo runtime que la API HTTP puede afectar a la disponibilidad de la API si el volumen de agentes periódicos crece mucho | Diseñar desde el principio la posibilidad de separar en una réplica dedicada del backend solo para ejecución de workflows (§5.3), aunque no se active en el lanzamiento inicial |
| Un agente con Skill no idempotente sufre efectos secundarios duplicados ante reintentos | Diseñar los Skills invocados desde agentes periódicos para ser idempotentes, o usar claves de idempotencia propias |
| Tentación de decorar directamente funciones de negocio con decoradores del runtime en puntos dispersos del código | Revisión de código: solo `periodic_agent_task.py` importa `dbos`; `AgentSchedulerService` es el único punto de contacto con el resto del sistema |
| Crecimiento de `agent_run_summary` a largo plazo | Política de retención (purgar/archivar ejecuciones antiguas más allá de N días) |

---

## 8. Anexo: variables de entorno nuevas

```
DBOS_DATABASE_URL=postgresql://mattin:${DATABASE_PASSWORD}@postgres:5432/mattin_ai_dbos
AICT_MIN_SCHEDULE_INTERVAL_SECONDS=60   # límite de negocio, no del motor de orquestación
```
