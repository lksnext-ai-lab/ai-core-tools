"""Text extraction for office documents attached to a chat.

PDFs have their own module (``PDFTools``). This one covers the ``document``
family (.docx, .doc, .xls, .ppt…), which until now returned the placeholder
string "Document processing not implemented" *as the file's content* — the
agent received that sentence instead of the document, so attaching a Word file
silently did nothing.

.docx is read with the same loader the silo indexing pipeline already uses
(``Docx2txtLoader``), so a document attached to a chat and the same document
indexed into a repository yield the same text.
"""

import os

from utils.logger import get_logger

logger = get_logger(__name__)

# Formats we can turn into text. Anything else keeps an explicit "not read"
# notice rather than pretending it was read.
_DOCX_EXTENSIONS = {".docx"}


def extract_text_from_document(file_path: str, filename: str) -> str:
    """Extract plain text from an office document.

    Args:
        file_path: Path to the file on disk.
        filename: Original name, used to pick the extractor and for messages.

    Returns:
        The document's text, or a human-readable notice when the format has no
        extractor (legacy .doc, spreadsheets, slides) or the file cannot be
        read. The caller treats the return value as the file's content, so a
        notice must state plainly that the document was not read.
    """
    extension = os.path.splitext(filename or "")[1].lower()

    if extension not in _DOCX_EXTENSIONS:
        logger.info(
            "No text extractor for '%s' (%s); attachment not read",
            filename,
            extension or "no extension",
        )
        return (
            f"Document file: {filename} "
            f"(text extraction is not supported for {extension or 'this format'})"
        )

    try:
        from langchain_community.document_loaders import Docx2txtLoader

        documents = Docx2txtLoader(file_path).load()
        text = "\n\n".join(doc.page_content for doc in documents).strip()

        if not text:
            logger.warning(
                "No text extracted from '%s' (empty or image-only document)", filename
            )
            return (
                f"Document file: {filename} "
                f"(no extractable text: it may be empty or contain only images)"
            )

        return text
    except Exception as exc:
        logger.error(
            "Failed to extract text from '%s': %s", filename, exc, exc_info=True
        )
        return f"Error processing document {filename}: {exc}"
