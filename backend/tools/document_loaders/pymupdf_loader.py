"""``pymupdf`` PDF loader: plain PyMuPDF page text split by size. Fast (~0.01 s/page).

This is the PDF indexing Mattin AI had before the structure-aware loaders:
``PyMuPDFLoader`` (one Document per page, PDF metadata such as ``source`` and
``total_pages``) followed by a ``RecursiveCharacterTextSplitter``. Chunks do not
cross pages and carry no section information.
"""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_pymupdf_chunks(file_path: str, chunk_size: int, chunk_overlap: int) -> list[Document]:
    from langchain_community.document_loaders import PyMuPDFLoader

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_documents(PyMuPDFLoader(file_path).load())
