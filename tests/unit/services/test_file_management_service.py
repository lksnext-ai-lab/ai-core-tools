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
