# Sandbox v2 — Auditoría post-merge (hallazgos críticos y altos)

**Contexto:** `feature/sandbox-v2-core` (PR #209) se mergeó a `develop` el 2026-08-02
(squash, tip `2f57c4e2`). Esta auditoría es una segunda pasada, hecha probando la app
ya desplegada con la configuración documentada en `CLAUDE.md`, sobre el estado actual
de `develop` (tip `ff687192` a fecha de este documento). Los hallazgos originales de
la revisión de PR (IDOR cross-tenant, SSRF, escape de red, etc.) ya se arreglaron
antes del merge y no se repiten aquí — esto es una lista nueva, encontrada después.

Cada hallazgo fue verificado leyendo el código real (no reconstruido de memoria) y,
donde fue posible, contrastado con evidencia en `logs/app.log` / `logs/app_errors.log`
del entorno de pruebas.

**Rama de este documento:** `fix/sandbox-critical-followups` (creada desde `develop`).
Este documento es solo análisis — ningún fix incluido aún.

---

## 🔴 Críticos

### CRÍTICO-1 — Un agente con Code Interpreter devuelve 500 si no arrancas el perfil `opensandbox`

`docker compose up -d` (el comando documentado en `CLAUDE.md`) **no** arranca el
servicio `opensandbox` — está detrás de `profiles: [opensandbox]` en
`docker/docker-compose.yaml`. Pero `SANDBOX_DEFAULT_PROVIDER` ya vale `opensandbox`
por defecto (mismo fichero, línea ~94).

Reproducido:
```
POST /internal/apps/3/agents/24/chat
→ 500 {"detail":"Agent execution failed: Network connectivity error: [Errno -3] Temporary failure in name resolution"}
```

Cualquier agente con `enable_code_interpreter=true` deja de funcionar con un 500
completo, sin degradación.

**Causa raíz confirmada:** `backend/tools/sandbox/factory.py`'s
`resolve_provider_and_service_id()` solo lanza `SandboxProviderUnavailableError`
cuando el *nombre* del provider no está registrado/permitido — no hace ninguna
comprobación de red (confirmado por su propio docstring). Como `opensandbox` sí
está registrado como clase, la resolución "tiene éxito" y el fallo real (DNS/conexión,
porque el contenedor `opensandbox` nunca arrancó) explota más tarde dentro de
`create_sandbox()`, sin que ningún `except SandboxProviderUnavailableError` lo
capture (los sitios que sí manejan ese error están en
`backend/tools/agentTools.py:268,406,827` y
`backend/services/agent_execution_service.py:603` — ninguno cubre este caso).
Sube como excepción genérica hasta `agent_execution_service.py:408` →
`HTTPException(500, f"Agent execution failed: {str(e)}")` (ver también ALTO-8).

También confirmado: ya no queda ningún provider `subprocess`/`python_repl` local de
fallback — solo quedan comentarios que documentan que existió y fue retirado
(`backend/tools/sandbox/provider.py:66`, `backend/tools/sandbox/builtin_tools.py:6`).

**Por qué es crítico:** rompe el flujo de arranque *documentado* del proyecto, no
un caso límite. Cualquier despliegue nuevo que siga `CLAUDE.md` al pie de la letra
lo dispara en el primer chat con un agente code-interpreter.

---

### CRÍTICO-2 — Sandbox compartido entre usuarios distintos (`anon_{agent_id}`)

`backend/services/agent_execution_service.py:614`:
```python
sandbox_session_key = SandboxSessionService.session_key(agent_id, effective_conv_id)
```
Se llama sin el tercer argumento `session_id`. `SandboxSessionService.session_key()`
(`backend/services/sandbox_session_service.py:603-619`) cae a `anon_{agent_id}`
cuando `conversation_id` es `None` — es decir, para agentes `has_memory=false`,
embeds públicos, o marketplace.

Comparación reveladora: el `working_dir` **local** para el mismo caso sí incluye
`user_id` (`agent_execution_service.py:547-550`:
`f"agent_{agent_id}_user_{user_id}_app_{app_id_ctx}"`), pero esa variable nunca se
propaga al `session_key` del sandbox.

Evidencia observada:
```
working_dir=data/tmp/persistent/agent_24_user_1_app_3   ← el dir local SÍ lleva user_id
creating sandbox for anon_24                              ← la sesión de sandbox NO
```

**Por qué es crítico:** dos usuarios distintos contra el mismo agente comparten el
mismo contenedor y el mismo workspace remoto — los ficheros que sube el usuario A
los puede ver/leer el usuario B. Es una fuga de aislamiento multi-tenant real, no
solo un bug funcional.

---

### CRÍTICO-3 — El reintento por "checkpoint obsoleto" borra la conversación entera

`backend/services/agent_cache_service.py:11-13`:
```python
def is_missing_tool_output_error(exc: BaseException) -> bool:
    return "No tool output found for function call" in str(exc)
```

Si el error del proveedor LLM contiene ese substring →
`CheckpointerCacheService.invalidate_checkpointer_async()` →
`checkpointer.adelete_thread(thread_id)` (línea 150). `adelete_thread` borra **todo
el thread**, no solo el checkpoint incompleto. `get_conversation_history` lee de ese
mismo checkpointer (usado por el playground para cargar el histórico), así que el
usuario pierde el historial visible, no solo la memoria interna del agente.

Está en los dos caminos de ejecución:
- `agent_execution_service.py:1618-1631` (chat no-streaming)
- `agent_streaming_service.py:225-241` (chat streaming)

**Bug adicional en streaming:** `accumulated_content` (`agent_streaming_service.py:200`)
se inicializa una única vez antes del `try`/`for attempt`, y **no se resetea** antes
del `continue` (línea ~236). El reintento vuelve a acumular tokens sobre el contenido
del intento fallido → respuesta duplicada, tanto emitida al cliente como persistida.

**Evidencia en producción — no es hipotético.** Encontrado en `logs/app.log` del
entorno de pruebas: **20 disparos reales** de este mismo path, todos para
`agent 1 / session 297`, repartidos entre el 2026-07-20 y el 2026-08-02 (ejemplo:
línea 8427 `Detected incomplete tool-call checkpoint for agent 1 session 297;
deleting checkpoint and retrying turn once`). Cada disparo es una pérdida de
historial de esa sesión.

**Por qué es crítico:** de los tres, es el de mayor radio de impacto — afecta a
*cualquier* agente con memoria, tenga o no sandbox habilitado, y ya se ha disparado
repetidamente en un entorno real, no en un escenario construido para el test.

---

## 🟠 Altos (contexto — no forman parte del plan de fixes de esta rama, documentados para la siguiente pasada)

- **ALTO-4** — `test_connection_with_config` (`backend/services/sandbox_service_service.py:443`)
  bloquea el event loop con `future.result(timeout=20)` síncrono, llamado directamente
  (sin `run_in_threadpool`) desde rutas `async def`
  (`backend/routers/internal/sandbox_services.py:112`, `backend/routers/internal/admin.py:1261`).
- **ALTO-5** — mismo código: si el timeout expira, el `handle` (asignado en el hilo
  del executor) sigue `None` en el hilo principal cuando se evalúa el `finally`
  (línea ~473) → el sandbox se crea igual en segundo plano y nunca se destruye.
- **ALTO-6** — `SANDBOX_TEST_CONNECTION_ALLOW_PRIVATE` viene comentada (`false`) en
  `docker/.env.example:190`; con el default, el guarda SSRF bloquea también guardar
  (no solo probar) el propio `opensandbox:8080` interno del compose.
- **ALTO-7** — `docker/opensandbox/sandbox.toml:109-110`: `[ingress] mode = "direct"`
  publica puertos aleatorios en `0.0.0.0` del host por cada sandbox, contradiciendo
  el aislamiento documentado.
- **ALTO-8** — `agent_execution_service.py:408`: `detail=f"Agent execution failed: {str(e)}"`
  filtra el mensaje crudo de la excepción (sockets Docker, IDs de contenedor) al cliente.
- **ALTO-9** — workers de uvicorn muriendo durante actividad de sandbox — reportado,
  sin traza en los logs de este checkout, pendiente de reproducir antes de poder
  diagnosticar causa raíz.

## 🟡 Medios (idem — no bloquean, documentados para trazabilidad)

- **MEDIO-10** — reaper cross-worker race (`UVICORN_WORKERS` default 2, registro de
  sesiones en memoria de proceso).
- **MEDIO-11** — `opensandbox_provider.py:394-418`: fallo parcial al crear el contexto
  de un lenguaje se traga con un `logger.warning` y el sandbox se marca "ready" igualmente.
- **MEDIO-12** — `alembic downgrade -1` ambiguo tras la migración de merge
  (comportamiento esperable de Alembic ante un `down_revision` en tupla; no verificado
  en vivo en esta pasada).
- **MEDIO-13** — inconsistencias de configuración entre `.env.example`, `docker-compose.yaml`,
  `system_defaults.yaml` y `backend/utils/config.py` (imagen de code-interpreter distinta,
  `SANDBOX_MAX_CONCURRENT_SESSIONS` no leído, ajustes de `system_defaults.yaml` sin efecto).
- **MEDIO-14** — el panel de ejecución de código no recibe eventos `code_output`;
  causa probable: `get_stream_writer()` (`tool_factory.py:184-197`) falla
  silenciosamente cuando se llama desde el hilo de ejecución de la tool, no desde el
  contexto async del grafo.

---

## Alcance de esta rama

Esta rama (`fix/sandbox-critical-followups`) aborda **solo los tres críticos**
(CRÍTICO-1, 2, 3). Los altos/medios quedan documentados arriba para una pasada
posterior — mezclar los nueve en una sola rama haría el diff difícil de revisar y
retrasaría el fix de los críticos, que son los que tienen impacto de seguridad/pérdida
de datos en producción ahora mismo.
