from unittest.mock import patch

from routers.internal import system_one_services as module


def test_a_server_error_logs_only_the_exception_type_never_message_or_traceback():
    with patch.object(module, "logger") as log:
        error = module._server_error("saving", RuntimeError("password=hunter2"), app_id=1)
    assert error.status_code == 500 and "hunter2" not in str(error.detail)
    assert not log.error.call_args.kwargs.get("exc_info")
    assert "hunter2" not in str(log.error.call_args)
