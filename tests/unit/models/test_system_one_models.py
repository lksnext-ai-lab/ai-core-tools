from sqlalchemy import inspect

from models import Agent, AgentSystemOneAnswer, SystemOneAgent, SystemOneService


def test_system_one_agent_is_polymorphic_subtype_of_agent():
    assert SystemOneAgent.__mapper__.polymorphic_identity == "system_one_agent"
    assert SystemOneAgent.__mapper__.inherits is Agent.__mapper__
    assert SystemOneAgent().type == "system_one_agent"


def test_service_fk_is_not_null_and_restrict():
    col = SystemOneAgent.__table__.c.system_one_service_id
    assert col.nullable is False
    (fk,) = col.foreign_keys
    assert fk.ondelete == "RESTRICT"
    assert fk.column.table.name == "SystemOneService"


def test_summarization_fk_is_set_null_and_app_id_required():
    (fk,) = SystemOneAgent.__table__.c.summarization_service_id.foreign_keys
    assert fk.ondelete == "SET NULL"
    assert SystemOneService.__table__.c.app_id.nullable is False
    assert SystemOneAgent.__table__.c.max_state_chars.nullable is False


def test_answer_rows_cascade_with_event():
    (fk,) = AgentSystemOneAnswer.__table__.c.event_id.foreign_keys
    assert fk.ondelete == "CASCADE"
    assert "app_id" in {c.name for c in inspect(SystemOneService).columns}
