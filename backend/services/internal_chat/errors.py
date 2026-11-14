"""Errors of the flexible App chat."""
from utils.error_handlers import NotFoundError

NOT_FOUND_MESSAGE = "Resource not found"


class ChatResourceNotFoundError(NotFoundError):
    """Single answer for every "missing / not yours / other App / disabled" case of the Chat.

    The message is fixed on purpose and no ``resource`` is recorded: it must not reveal which resource
    failed, its id, or whether it exists in another App (a probing oracle across tenants).
    """

    def __init__(self) -> None:
        super().__init__(NOT_FOUND_MESSAGE)

