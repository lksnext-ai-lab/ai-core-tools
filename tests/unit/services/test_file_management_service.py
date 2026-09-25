import pytest

from services.file_management_service import FileReference


def test_document_placeholder_is_ready_but_not_extractable():
    file_ref = FileReference(
        file_id="file-1",
        filename="brief.docx",
        file_type="document",
        content="Document file: brief.docx (Document processing not implemented)",
        file_size_bytes=128,
    )

    assert file_ref.processing_status == "ready"
    assert file_ref.has_extractable_content is False
    assert file_ref.content_preview is None


def test_processing_errors_are_not_ready():
    file_ref = FileReference(
        file_id="file-1",
        filename="broken.pdf",
        file_type="pdf",
        content="Error processing file: invalid PDF",
        file_size_bytes=128,
    )

    assert file_ref.processing_status == "error"


def _minimal_docx(text: str) -> bytes:
    """Build a minimal .docx in memory (docx2txt only reads word/document.xml)."""
    import io
    import zipfile

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_docx_text_is_extracted(tmp_path):
    """Regression: .docx attachments reached the agent as a placeholder, not their text."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from services.file_management_service import FileManagementService

    upload = MagicMock()
    upload.filename = "informe.docx"
    upload.read = AsyncMock(return_value=_minimal_docx("Resumen trimestral de ventas"))

    with patch("utils.config.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}):
        fms = FileManagementService()
    file_type = fms._get_file_type(upload.filename)
    content, _, _ = await fms._process_file_content(upload, file_type)

    assert file_type == "document"
    assert "Resumen trimestral de ventas" in content
