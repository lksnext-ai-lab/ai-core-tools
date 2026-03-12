from unittest.mock import MagicMock, patch

from services.media_service import MediaService


def test_list_media_delegates_to_repository():
    db = MagicMock()
    media_items = [MagicMock(), MagicMock()]

    with patch(
        "services.media_service.MediaRepository.list_by_repository_and_folder",
        return_value=media_items,
    ) as mock_repo:
        result = MediaService.list_media(repository_id=12, folder_id=5, db=db)

    assert result == media_items
    mock_repo.assert_called_once_with(12, 5, db)


def test_list_media_supports_root_folder_filter():
    db = MagicMock()
    media_items = [MagicMock()]

    with patch(
        "services.media_service.MediaRepository.list_by_repository_and_folder",
        return_value=media_items,
    ) as mock_repo:
        result = MediaService.list_media(repository_id=12, folder_id=0, db=db)

    assert result == media_items
    mock_repo.assert_called_once_with(12, 0, db)
