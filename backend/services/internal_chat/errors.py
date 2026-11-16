"""Errors of the flexible App chat."""
from utils.error_handlers import ConflictError, NotFoundError

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
    """A turn of this conversation is already in flight (NFR-6: one turn at a time per conversation).

    Mapped to HTTP 409 ``CONVERSATION_BUSY`` with a ``Retry-After`` header before any stream starts.
    """

    headers = {"Retry-After": str(BUSY_RETRY_AFTER_SECONDS)}

    def __init__(self) -> None:
        super().__init__(BUSY_MESSAGE, "CONVERSATION_BUSY")
