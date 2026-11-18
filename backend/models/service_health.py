from sqlalchemy import Column, DateTime, Text, event, inspect


# Settings whose change can fix a failing service: editing any of them clears the recorded error.
_CONNECTION_FIELDS = ("api_key", "endpoint", "extra_config", "provider", "api_version")


class ServiceHealthMixin:
    """Last provider failure that needs action on the service itself (bad key, quota).

    Set by ``ServiceHealthService.record_failure`` when indexing or media processing is
    rejected by the provider; cleared on the next successful call or when the connection
    settings are edited.
    """

    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime, nullable=True)


def _clear_error_on_reconfigure(mapper, connection, target):
    state = inspect(target)
    if any(state.attrs[field].history.has_changes() for field in _CONNECTION_FIELDS):
        target.last_error = None
        target.last_error_at = None


def track_service_health(model) -> None:
    """Clear ``last_error`` whenever ``model``'s connection settings are saved with changes."""
    event.listen(model, "before_update", _clear_error_on_reconfigure)
