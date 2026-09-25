class SkillServiceError(Exception):
    """Base class for typed skill service errors. Not a ValueError.

    ``status_code`` is a class attribute: routers map the exception CLASS to an HTTP status.
    """

    status_code: int = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class SkillImportError(SkillServiceError):
    """A skill package is invalid (400)."""

    status_code = 400


class SkillValidationError(SkillServiceError):
    """A skill field failed validation (400)."""

    status_code = 400


class SkillForbiddenError(SkillServiceError):
    """The operation targets a system skill through an app-scoped path (403)."""

    status_code = 403


class SkillConflictError(SkillServiceError):
    """The operation conflicts with the current state of the data, e.g. duplicate name or skill in use (409)."""

    status_code = 409


class SkillBusyError(SkillServiceError):
    """Too many concurrent skill imports; retry later (429)."""

    status_code = 429


class SkillPersistenceError(SkillServiceError):
    """Unexpected persistence failure (500). The detail is safe to show; the cause is logged server-side."""

    status_code = 500
