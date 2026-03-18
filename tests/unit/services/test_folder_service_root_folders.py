from unittest.mock import MagicMock

from services.folder_service import FolderService


class TestGetRootFoldersWithCounts:
    def test_returns_folder_count_metadata(self, mocker):
        folder_one = MagicMock()
        folder_one.folder_id = 1
        folder_one.resources = [MagicMock(), MagicMock()]

        folder_two = MagicMock()
        folder_two.folder_id = 2
        folder_two.resources = []

        mocker.patch(
            "services.folder_service.FolderRepository.get_by_repository_id",
            return_value=[folder_one, folder_two],
        )

        subfolders_map = {
            1: [MagicMock()],
            2: [MagicMock(), MagicMock(), MagicMock()],
        }

        def fake_get_subfolders(_db, folder_id):
            return subfolders_map[folder_id]

        mocker.patch(
            "services.folder_service.FolderRepository.get_subfolders",
            side_effect=fake_get_subfolders,
        )

        result = FolderService.get_root_folders_with_counts(repository_id=99, db=MagicMock())

        assert len(result) == 2
        assert result[0]["folder"] is folder_one
        assert result[0]["subfolder_count"] == 1
        assert result[0]["resource_count"] == 2
        assert result[1]["folder"] is folder_two
        assert result[1]["subfolder_count"] == 3
        assert result[1]["resource_count"] == 0
