"""Mattin AI's A2A (Agent2Agent protocol) server integration.

AD-14: no module named ``a2a`` lives anywhere under ``backend/``, because
``backend/`` is on ``sys.path`` and a top-level ``backend/a2a/`` package would
shadow the ``a2a`` SDK package. All Mattin A2A code lives in this package
(``backend/services/a2a_server/``) and in ``backend/routers/a2a_server/``.
"""
