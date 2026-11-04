"""parse_agent_response returns JSON-serialisable data for structured (output parser) responses."""

import json
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import List, Optional

from pydantic import BaseModel

from tools.agentTools import parse_agent_response


class _Line(BaseModel):
    precio: Decimal
    fecha_desde: Optional[date] = None


class _Tarifa(BaseModel):
    nombre_proveedor: str
    fecha_tarifa: Optional[date] = None
    generado: Optional[datetime] = None
    articulos: List[_Line]


def test_structured_response_with_dates_is_json_serialisable():
    agent = SimpleNamespace(output_parser_id=203)
    response = _Tarifa(
        nombre_proveedor="SIBO",
        fecha_tarifa=date(2026, 6, 29),
        generado=datetime(2026, 10, 19, 16, 17, 51),
        articulos=[_Line(precio=Decimal("1.25"), fecha_desde=date(2026, 7, 1))],
    )

    parsed = parse_agent_response(response, agent)

    json.dumps(parsed)  # must not raise
    assert parsed["fecha_tarifa"] == "2026-06-29"
    assert parsed["articulos"][0]["fecha_desde"] == "2026-07-01"


def test_without_output_parser_text_is_returned_unchanged():
    agent = SimpleNamespace(output_parser_id=None)
    assert parse_agent_response("hola", agent) == "hola"
