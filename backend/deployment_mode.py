import os


_REQUIRED_SAAS_ENV_VARS = [
    "STRIPE_API_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_ID_STARTER",
    "STRIPE_PRICE_ID_PRO",
    "EMAIL_FROM",
]


def is_saas_mode() -> bool:
    """Return True when AICT_DEPLOYMENT_MODE is set to 'saas'."""
    return os.getenv("AICT_DEPLOYMENT_MODE", "self_managed").lower() == "saas"


def is_self_managed() -> bool:
    """Return True when running in self-managed (default) mode."""
    return not is_saas_mode()


def validate_saas_env() -> None:
    """Validate that all required SaaS environment variables are set.

    Raises RuntimeError with a descriptive message listing any missing vars.
    Should only be called when is_saas_mode() is True.
    """
    missing = [var for var in _REQUIRED_SAAS_ENV_VARS if not os.getenv(var)]
    if missing:
        raise RuntimeError(
            "SaaS mode is enabled (AICT_DEPLOYMENT_MODE=saas) but the following "
            "required environment variables are missing: "
            + ", ".join(missing)
            + ". Please set these variables before starting the application."
        )
