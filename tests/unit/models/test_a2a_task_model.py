from models.a2a_task import A2ATask


def test_api_key_fk_uses_set_null_on_delete():
    foreign_keys = list(A2ATask.__table__.c.api_key_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "SET NULL"
