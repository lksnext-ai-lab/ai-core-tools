from types import SimpleNamespace


def test_approval_rate_limit_is_checked_before_claiming(monkeypatch):
    import routers.public.v1.approvals as approvals_router

    approval = SimpleNamespace(agent_id=7)
    calls = []
    monkeypatch.setattr(
        approvals_router.approvals,
        "get_for_requester",
        lambda *args: approval,
    )
    monkeypatch.setattr(
        approvals_router.approvals,
        "prepare_decisions",
        lambda *args: calls.append("validate"),
    )
    monkeypatch.setattr(
        approvals_router,
        "_apply_approval_agent_rate_limit",
        lambda *args: calls.append("limit"),
    )
    monkeypatch.setattr(
        approvals_router.approvals,
        "prepare_resume",
        lambda *args: calls.append("claim") or "resume",
    )

    result = approvals_router._prepare_rate_limited_approval_resume(
        db=object(),
        app_id=1,
        approval_id="approval-id",
        body=SimpleNamespace(decisions=[]),
        requester=object(),
        response_headers={},
    )

    assert result == "resume"
    assert calls == ["validate", "limit", "claim"]
