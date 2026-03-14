from unittest.mock import MagicMock

from services.app_service import AppService


def test_get_all_apps_delegates_to_repository():
    db = MagicMock()
    service = AppService(db)
    apps = [MagicMock(), MagicMock()]
    service.app_repo.get_all = MagicMock(return_value=apps)

    result = service.get_all_apps()

    assert result == apps
    service.app_repo.get_all.assert_called_once_with()
