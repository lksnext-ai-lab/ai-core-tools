"""The A2A (Agent2Agent protocol) HTTP surface (step_017, AD-4, AD-14).

Exports `a2a_router`, mounted from `backend/main.py` with no prefix (the
routes carry their own absolute paths: `/a2a/v1/...` and the root
`/.well-known/agent-card.json`), next to the internal/public/MCP routers.

AD-14: no module named `a2a` anywhere under `backend/` -- this package is
named `a2a_server`, mirroring `services/a2a_server/`, precisely so it can
never shadow the `a2a-sdk` package on `sys.path`.
"""

from routers.a2a_server.router import a2a_router

__all__ = ["a2a_router"]
