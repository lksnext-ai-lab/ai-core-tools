"""Flexible App chat ("Chat") orchestration package.

Do NOT import submodules here (no re-exports): ``tools.agentTools`` imports
``services.internal_chat.resolved_config``, so importing the package must stay free of
``tools``/``sqlalchemy``/other ``services`` imports or an import cycle appears.
"""
