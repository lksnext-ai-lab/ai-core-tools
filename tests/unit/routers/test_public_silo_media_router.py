"""Public silo API: video/audio indexing and media endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Response

from routers.public.v1 import silos as silos_module
from routers.public.v1.schemas import SiloYouTubeIndexRequestSchema
from utils.error_handlers import ValidationError

SILO = SimpleNamespace(silo_id=7, app_id=1)


def _media(**overrides):
    values = dict(media_id=5, silo_id=7, repository_id=None, name="demo", source_type="upload",
                  source_url=None, status="pending", error_message=None, duration=None, language=None,
                  processing_mode=None, custom_metadata=None, create_date=None, processed_at=None)
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def auth(mocker):
    mocker.patch.object(silos_module, "validate_api_key_for_app", return_value=None)
    return mocker.patch.object(silos_module, "validate_silo_ownership", return_value=SILO)


@pytest.fixture
def media_service(mocker):
    return mocker.patch.object(silos_module, "MediaService")


def _upload(filename, content_type=None, content=b"data"):
    file = MagicMock()
    file.filename = filename
    file.content_type = content_type
    file.read = AsyncMock(return_value=content)
    return file


def _db_returning(*, first=None, items=()):
    db = MagicMock()
    query = db.query.return_value.filter.return_value
    query.first.return_value = first
    query.order_by.return_value.all.return_value = list(items)
    return db


async def _index_file(file, response=None, metadata=None):
    return await silos_module.index_file_document(
        app_id=1, silo_id=7, file=file, api_key="key", db=MagicMock(),
        response=response or Response(), background_tasks=MagicMock(), metadata=metadata,
    )


class TestIndexFileMedia:
    @pytest.mark.asyncio
    async def test_media_is_queued_with_202(self, auth, media_service):
        media_service.is_media_filename.return_value = True
        media_service.create_silo_media_from_file = AsyncMock(return_value=_media())
        response = Response()

        result = await _index_file(_upload("clip.mp4"), response, metadata='{"doc_id": "42"}')

        assert response.status_code == 202
        assert result.media_id == 5
        assert result.num_documents == 0
        call = media_service.create_silo_media_from_file.call_args
        assert call.args[1] is SILO
        assert call.kwargs["metadata"] == {"doc_id": "42"}

    @pytest.mark.asyncio
    async def test_non_object_metadata_is_dropped(self, auth, media_service):
        media_service.is_media_filename.return_value = True
        media_service.create_silo_media_from_file = AsyncMock(return_value=_media())

        await _index_file(_upload("clip.mp4"), metadata="[1, 2]")

        assert media_service.create_silo_media_from_file.call_args.kwargs["metadata"] is None

    @pytest.mark.asyncio
    async def test_silo_without_media_services_is_400(self, auth, media_service):
        media_service.is_media_filename.return_value = True
        media_service.create_silo_media_from_file = AsyncMock(side_effect=ValueError("no transcription"))

        with pytest.raises(HTTPException) as exc:
            await _index_file(_upload("clip.mp4"))

        assert exc.value.status_code == 400
        assert exc.value.detail == "no transcription"


class TestIndexFileDocument:
    @pytest.mark.asyncio
    async def test_document_is_indexed_synchronously(self, auth, media_service, mocker):
        media_service.is_media_filename.return_value = False
        silo_service = mocker.patch.object(silos_module, "SiloService")
        silo_service.extract_documents_from_file.return_value = [
            SimpleNamespace(page_content="hola", metadata={"page": 1}),
        ]

        result = await _index_file(_upload("notes.txt"))

        assert result.num_documents == 1
        assert result.media_id is None
        indexed = silo_service.index_multiple_content.call_args.args[1]
        assert indexed == [{"content": "hola", "metadata": {"page": 1}}]


class TestDocumentExtension:
    @pytest.mark.parametrize("filename, content_type, expected", [
        ("Report.PDF", None, ".pdf"),
        ("upload", "application/msword", ".doc"),
        ("upload", "application/octet-stream", ".txt"),
        (None, None, ".txt"),
    ])
    def test_extension(self, filename, content_type, expected):
        assert silos_module._document_extension(_upload(filename, content_type)) == expected


class TestIndexYouTube:
    @pytest.mark.asyncio
    async def test_youtube_is_queued(self, auth, media_service):
        media_service.create_silo_media_from_youtube = AsyncMock(return_value=_media(source_type="youtube"))
        body = SiloYouTubeIndexRequestSchema(url="https://youtu.be/abc", metadata={"k": "v"})

        result = await silos_module.index_youtube_video(
            app_id=1, silo_id=7, body=body, api_key="key", db=MagicMock(), background_tasks=MagicMock(),
        )

        assert result.media_id == 5
        assert media_service.create_silo_media_from_youtube.call_args.kwargs["metadata"] == {"k": "v"}

    @pytest.mark.asyncio
    async def test_invalid_url_is_400(self, auth, media_service):
        media_service.create_silo_media_from_youtube = AsyncMock(side_effect=ValueError("Invalid YouTube URL"))
        body = SiloYouTubeIndexRequestSchema(url="https://example.com")

        with pytest.raises(HTTPException) as exc:
            await silos_module.index_youtube_video(
                app_id=1, silo_id=7, body=body, api_key="key", db=MagicMock(), background_tasks=MagicMock(),
            )

        assert exc.value.status_code == 400


class TestMediaEndpoints:
    @pytest.mark.asyncio
    async def test_list(self, auth):
        db = _db_returning(items=[_media(), _media(media_id=6)])

        result = await silos_module.list_silo_media(app_id=1, silo_id=7, api_key="key", db=db)

        assert [m.media_id for m in result.media] == [5, 6]

    @pytest.mark.asyncio
    async def test_get(self, auth):
        db = _db_returning(first=_media(status="transcribing"))

        result = await silos_module.get_silo_media(app_id=1, silo_id=7, media_id=5, api_key="key", db=db)

        assert result.status == "transcribing"

    @pytest.mark.asyncio
    async def test_get_missing_is_404(self, auth):
        with pytest.raises(HTTPException) as exc:
            await silos_module.get_silo_media(app_id=1, silo_id=7, media_id=5, api_key="key",
                                              db=_db_returning(first=None))

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete(self, auth, media_service):
        media = _media()
        media_service.delete_media_item.return_value = True

        result = await silos_module.delete_silo_media(app_id=1, silo_id=7, media_id=5, api_key="key",
                                                      db=_db_returning(first=media))

        assert result.message == "Media deleted"
        assert media_service.delete_media_item.call_args.args[0] is media

    @pytest.mark.asyncio
    async def test_delete_repository_media_is_409(self, auth, media_service):
        with pytest.raises(HTTPException) as exc:
            await silos_module.delete_silo_media(app_id=1, silo_id=7, media_id=5, api_key="key",
                                                 db=_db_returning(first=_media(repository_id=3)))

        assert exc.value.status_code == 409
        media_service.delete_media_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_failure_is_500(self, auth, media_service):
        media_service.delete_media_item.return_value = False

        with pytest.raises(HTTPException) as exc:
            await silos_module.delete_silo_media(app_id=1, silo_id=7, media_id=5, api_key="key",
                                                 db=_db_returning(first=_media()))

        assert exc.value.status_code == 500


class TestCreateSiloValidation:
    @pytest.mark.asyncio
    async def test_invalid_media_service_is_422(self, mocker):
        mocker.patch.object(silos_module, "validate_api_key_for_app", return_value=None)
        silo_service = mocker.patch.object(silos_module, "SiloService")
        silo_service.create_or_update_silo_router.side_effect = ValidationError("not found")

        with pytest.raises(HTTPException) as exc:
            await silos_module.create_silo(app_id=1, silo_data=MagicMock(), api_key="key", db=MagicMock())

        assert exc.value.status_code == 422
