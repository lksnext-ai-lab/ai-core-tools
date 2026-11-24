"""SiloService.apply_indexing_settings: how create/update requests change a silo's indexing settings."""
from types import SimpleNamespace

import pytest
from services.silo_service import SiloService
from utils.error_handlers import ValidationError


def _silo(**overrides):
    values = {"chunk_size": 1000, "chunk_overlap": 200, "pdf_loader": "pymupdf", "pdf_loader_options": {}}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_nothing_changes_when_no_indexing_field_is_sent():
    silo = _silo(chunk_size=10, pdf_loader="removed-loader")  # invalid stored values must not block

    SiloService.apply_indexing_settings(silo, {"name": "renamed"})

    assert (silo.chunk_size, silo.pdf_loader) == (10, "removed-loader")


def test_new_silo_gets_defaults_for_omitted_fields():
    silo = _silo(chunk_size=None, chunk_overlap=None, pdf_loader=None, pdf_loader_options=None)

    SiloService.apply_indexing_settings(silo, {"pdf_loader": "pymupdf4llm"})

    assert (silo.chunk_size, silo.chunk_overlap, silo.pdf_loader) == (2000, 400, "pymupdf4llm")
    assert silo.pdf_loader_options == {"section_prefix": True, "remove_headers_footers": True}


def test_omitted_or_null_fields_keep_the_stored_value():
    silo = _silo()

    SiloService.apply_indexing_settings(silo, {"chunk_size": 3000, "chunk_overlap": None})

    assert (silo.chunk_size, silo.chunk_overlap, silo.pdf_loader) == (3000, 200, "pymupdf")


def test_changing_loader_without_options_resets_them_to_the_new_loader_defaults():
    silo = _silo(pdf_loader="pymupdf4llm", pdf_loader_options={"section_prefix": False, "remove_headers_footers": True})

    SiloService.apply_indexing_settings(silo, {"pdf_loader": "pymupdf"})

    assert silo.pdf_loader_options == {}


def test_options_for_the_current_loader_are_merged_with_defaults():
    silo = _silo(pdf_loader="pymupdf4llm", pdf_loader_options={"section_prefix": True, "remove_headers_footers": True})

    SiloService.apply_indexing_settings(silo, {"pdf_loader_options": {"remove_headers_footers": False}})

    assert silo.pdf_loader_options == {"section_prefix": True, "remove_headers_footers": False}


@pytest.mark.parametrize(
    "data",
    [
        {"chunk_size": 100},
        {"chunk_overlap": 600},  # more than half of the stored 1000
        {"chunk_size": "big"},
        {"pdf_loader": "unknown"},
        {"pdf_loader_options": {"section_prefix": True}},  # pymupdf has no options
    ],
)
def test_invalid_settings_raise_validation_error_and_leave_the_silo_untouched(data):
    silo = _silo()

    with pytest.raises(ValidationError):
        SiloService.apply_indexing_settings(silo, data)

    assert silo == _silo()
