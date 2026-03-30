from unittest.mock import MagicMock

from services.media_service import MediaService


class TestMediaServiceListMedia:
    def test_list_media_delegates_to_repository(self, mocker):
        db = MagicMock()
        expected = [MagicMock(), MagicMock()]

        list_mock = mocker.patch(
            "services.media_service.MediaRepository.list_by_repository_and_folder",
            return_value=expected,
        )

        result = MediaService.list_media(repository_id=10, folder_id=3, db=db)

        assert result == expected
        list_mock.assert_called_once_with(repository_id=10, folder_id=3, db=db)

    def test_list_media_supports_root_folder_filter(self, mocker):
        db = MagicMock()
        list_mock = mocker.patch(
            "services.media_service.MediaRepository.list_by_repository_and_folder",
            return_value=[],
        )

        MediaService.list_media(repository_id=20, folder_id=0, db=db)

        list_mock.assert_called_once_with(repository_id=20, folder_id=0, db=db)
