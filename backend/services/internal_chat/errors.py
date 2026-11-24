"""Errors of the flexible App chat."""
from utils.error_handlers import AppError, ConflictError, NotFoundError

NOT_FOUND_MESSAGE = "Resource not found"


class ChatResourceNotFoundError(NotFoundError):
    """Single answer for every "missing / not yours / other App / disabled" case of the Chat.

    The message is fixed on purpose and no ``resource`` is recorded: it must not reveal which resource
    failed, its id, or whether it exists in another App (a probing oracle across tenants).
    """

    def __init__(self) -> None:
        super().__init__(NOT_FOUND_MESSAGE)



BUSY_MESSAGE = "Another message of this conversation is still being answered"
BUSY_RETRY_AFTER_SECONDS = 5


class ChatConversationBusyError(ConflictError):
    """A turn of this conversation is already in flight (one turn at a time per conversation).

    Mapped to HTTP 409 ``CONVERSATION_BUSY`` with a ``Retry-After`` header before any stream starts.
    """

    headers = {"Retry-After": str(BUSY_RETRY_AFTER_SECONDS)}

    def __init__(self) -> None:
        super().__init__(BUSY_MESSAGE, "CONVERSATION_BUSY")


STEP_LIMIT_MESSAGE = (
    "The assistant reached its step limit before finishing. The conversation was kept: "
    "send a follow-up message (for example \"continue\") to resume."
)
STEP_LIMIT_ERROR_CODE = "STEP_LIMIT_REACHED"


class ChatStepLimitError(AppError):
    """The turn ran out of graph steps (``GraphRecursionError``). HTTP 422 ``STEP_LIMIT_REACHED``.

    The text is fixed (never built from the exception). The conversation, its checkpoint, files and sandbox are
    kept so the user can continue.
    """

    def __init__(self) -> None:
        super().__init__(STEP_LIMIT_MESSAGE, STEP_LIMIT_ERROR_CODE, 422)


TOO_MANY_FILES_ERROR_CODE = "TOO_MANY_FILES"


class ChatTooManyFilesError(AppError):
    """One message carries more files than ``CHAT_MAX_FILES_PER_TURN``. HTTP 422 ``TOO_MANY_FILES``.

    Raised before any claim / stream starts, so ``/stream`` answers with a plain HTTP 422 body too.
    """

    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        super().__init__(f"Too many files in one message (maximum {maximum})", TOO_MANY_FILES_ERROR_CODE, 422)
