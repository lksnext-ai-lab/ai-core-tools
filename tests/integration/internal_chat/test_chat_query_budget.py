"""Query budget of the App Chat (app-flexible-chat step_016, NFR-5).

Counts the SQL statements the app sends (SQLAlchemy ``before_cursor_execute``) for the listing/options endpoints and a
whole ``POST /messages`` turn, with a small and a large amount of App data. Two guarantees:

* no N+1: the count with 30 of everything equals the count with 3 of everything;
* an absolute ceiling (measured value + 3), so a new query in the hot path is noticed.

Engines listened to, and counted separately (the process has several, a listener on one misses the others):

* ``test``: the ``test_engine`` fixture, under the request session (``get_db`` is overridden to the test session);
* ``app``: ``db.database.engine``, a DIFFERENT Engine object (same URL, own pool) used by every product code path that
  opens ``SessionLocal()`` itself (e.g. the temp-silo lookup in ``tools/agentTools``);
* ``async``: ``db.database.async_engine.sync_engine`` (async sessions; the pgvector store and A2A use it).

Excluded, on purpose:

* the LangGraph checkpointer: its own psycopg pool, not SQLAlchemy, invisible to these listeners;
* the metrics write (``agent_metrics_recorder.persist_metrics_payload``, one ``SessionLocal()`` session on the app
  engine, after the turn): the ``fakes`` fixture replaces it to capture the payload (the real one cannot see the
  test transaction), so it is NOT in the numbers; a real turn adds its statements on top of the figures here;
* SAVEPOINT / RELEASE statements, which come from the test harness (``join_transaction_mode="create_savepoint"``).

Every measurement is preceded by a warm-up call (see ``measure``).
"""
import re
from collections import Counter

import pytest
from sqlalchemy import event

from db.database import async_engine, engine as app_engine
from models.ai_service import AIService
from models.mcp_config import MCPConfig
from models.silo import Silo
from models.skill import Skill
from tests.factories import AIServiceFactory, configure_factories
from tests.integration.internal_chat._chat_support import base, selection, turn_form

SMALL, LARGE = 3, 30

# Ceilings: measured total over all engines + 3 (see the report of step_016 for the measured values).
OPTIONS_CEILING = 17  # measured 14
CONVERSATIONS_CEILING = 8  # measured 5
TURN_CEILING = 61  # measured 58 (test engine; app and async engines 0)

_HARNESS = re.compile(r"^\s*(SAVEPOINT|RELEASE SAVEPOINT|ROLLBACK TO SAVEPOINT)\b", re.I)


class SkillRefreshGrowth(AssertionError):
    """The turn issues one extra statement per SELECTED skill (finding of step_016)."""


class McpGrowth(AssertionError):
    """The turn issues extra statements per SELECTED MCP config."""


class Counting:
    def __init__(self, engines: dict):
        self.engines = engines
        self.statements: dict[str, list[str]] = {name: [] for name in engines}
        self._hooks = {}

    def __enter__(self):
        for name, eng in self.engines.items():
            def hook(conn, cursor, statement, parameters, context, executemany, _name=name):
                if not _HARNESS.match(statement):
                    self.statements[_name].append(statement)

            self._hooks[name] = hook
            event.listen(eng, "before_cursor_execute", hook)
        return self

    def __exit__(self, *exc):
        for name, eng in self.engines.items():
            event.remove(eng, "before_cursor_execute", self._hooks[name])

    @property
    def count(self) -> int:
        return sum(len(v) for v in self.statements.values())

    def per_engine(self) -> str:
        return " ".join(f"{n}={len(v)}" for n, v in self.statements.items())

    def pattern(self) -> str:
        """The statements that repeat, with their literal parameters collapsed (the N+1 suspects)."""
        shapes = Counter(re.sub(r"\s+", " ", s)[:160] for v in self.statements.values() for s in v)
        return "\n".join(f"{n}x {s}" for s, n in shapes.most_common(6) if n > 1)


def grow(db, world, total: int) -> None:
    """Top the App up to ``total`` AI services, silos, skills and MCP configs (plus what the world already has)."""
    configure_factories(db)
    app_id = world["app_id"]
    for model, name in ((AIService, "ai"), (Silo, "silo"), (Skill, "skill"), (MCPConfig, "mcp")):
        have = db.query(model).filter(model.app_id == app_id).count()
        for i in range(max(0, total - have)):
            if model is AIService:
                AIServiceFactory(app_id=app_id, app=None, name=f"extra-ai-{have + i}", description="gpt-x")
            elif model is Silo:
                db.add(Silo(name=f"extra-silo-{have + i}", app_id=app_id, embedding_service_id=world["emb"]))
            elif model is Skill:
                db.add(Skill(name=f"extra-skill-{have + i}", content="x", app_id=app_id))
            else:
                db.add(MCPConfig(name=f"extra-mcp-{have + i}", app_id=app_id,
                                 config={f"srv{have + i}": {"url": "http://x", "transport": "streamable_http"}}))
    db.commit()


def make_conversations(client, world, total: int) -> None:
    have = client.get(base(world["app_id"]) + "/conversations?limit=1", headers=world["alice"]).json()["total"]
    for _ in range(max(0, total - have)):
        r = client.post(base(world["app_id"]) + "/conversations", headers=world["alice"],
                        json={"selection": {"ai_service_id": world["ai_a"]}})
        assert r.status_code == 200, r.text


def measure(test_engine, call) -> Counting:
    # Warm-up, ALWAYS before a measurement: the first turn of a conversation lazily creates the App's hidden internal
    # chat agent (and its first call fills one-time caches / lazy imports); that one-off cost is not per-request cost
    # and would make the first (small) measurement larger than the second one.
    call()
    engines = {"test": test_engine, "app": app_engine, "async": async_engine.sync_engine}
    assert len({id(e) for e in engines.values()}) == 3, "the three engines must be distinct objects"
    with Counting(engines) as counter:
        response = call()
    assert response.status_code == 200, response.text
    return counter


# Statements on the ``app`` / ``async`` engines are not issued by the request itself (it runs on the ``test`` engine);
# the few that can land inside a counting window come from background workers the app starts with each test client
# (orphan-repository sweep, sandbox reaper, late metrics write). They are bounded noise, not per-item cost.
BACKGROUND_TOLERANCE = 2
BACKGROUND_CEILING = 4


def _engine_counts(counter: Counting) -> dict:
    return {name: len(v) for name, v in counter.statements.items()}


def assert_budget(small: Counting, large: Counting, ceiling: int, label: str, growth_exc=AssertionError) -> None:
    """The ``test`` engine (the only one the request uses) has the SAME count at both sizes (``growth_exc`` is raised
    only when the growth is exactly one statement per extra selected item, the shape of a known finding) and stays
    under the ceiling. The ``app`` and ``async`` engines may differ by background noise only: at most
    ``BACKGROUND_TOLERANCE`` more in the large run and never more than ``BACKGROUND_CEILING``. All per-engine counts,
    and the stray statements, are in every failure message."""
    s, l = _engine_counts(small), _engine_counts(large)
    strays = {n: [re.sub(r"\s+", " ", x)[:200] for x in v]
              for n, v in {**{f"{k}(small)": small.statements[k] for k in ("app", "async")},
                           **{f"{k}(large)": large.statements[k] for k in ("app", "async")}}.items() if v}
    detail = f"small {small.per_engine()}, large {large.per_engine()}; background statements: {strays or 'none'}"
    if l["test"] != s["test"]:
        grown = l["test"] - s["test"]
        exc = growth_exc if grown == LARGE - SMALL else AssertionError
        raise exc(
            f"{label}: {s['test']} request statements with {SMALL} items but {l['test']} with {LARGE}; +{grown} "
            f"({detail})\nrepeated in the large run:\n{large.pattern()}"
        )
    for name in ("app", "async"):
        assert l[name] <= s[name] + BACKGROUND_TOLERANCE and l[name] <= BACKGROUND_CEILING, f"{label}: {name} engine grew ({detail})"
    assert large.count <= ceiling + BACKGROUND_CEILING, f"{label}: {large.count} statements, ceiling {ceiling} ({detail})\n{large.pattern()}"
    assert l["test"] <= ceiling, f"{label}: {l['test']} request statements, ceiling {ceiling} ({detail})\n{large.pattern()}"


class TestOptionsBudget:
    def test_options_does_not_grow_with_the_app_data(self, client, world, test_engine):
        def call():
            return client.get(base(world["app_id"]) + "/options", headers=world["viewer"])

        grow(_session(client), world, SMALL)
        small = measure(test_engine, call)
        grow(_session(client), world, LARGE)
        large = measure(test_engine, call)
        print(f"\nBUDGET options small={small.count} ({small.per_engine()}) large={large.count} ({large.per_engine()})")
        assert_budget(small, large, ceiling=OPTIONS_CEILING, label="GET /options")


class TestConversationsBudget:
    def test_listing_does_not_grow_with_the_number_of_conversations(self, client, world, test_engine):
        def call():
            return client.get(base(world["app_id"]) + "/conversations?limit=100", headers=world["alice"])

        make_conversations(client, world, SMALL)
        small = measure(test_engine, call)
        make_conversations(client, world, LARGE)
        large = measure(test_engine, call)
        print(f"\nBUDGET conversations small={small.count} ({small.per_engine()}) large={large.count} ({large.per_engine()})")
        assert_budget(small, large, ceiling=CONVERSATIONS_CEILING, label="GET /conversations")


class TestTurnBudget:
    """A whole non-streaming turn (resolve selection, prepare, run the fake LLM, persist) on a fresh conversation."""

    @staticmethod
    def _turn(client, world, test_engine, n, skills_n=2, mcps_n=2):
        grow(_session(client), world, n)
        db = _session(client)
        silos = [s.silo_id for s in db.query(Silo).filter(Silo.app_id == world["app_id"]).order_by(Silo.silo_id)]
        skills = [s.skill_id for s in db.query(Skill).filter(Skill.app_id == world["app_id"]).order_by(Skill.skill_id)]
        mcps = [m.config_id for m in db.query(MCPConfig).filter(MCPConfig.app_id == world["app_id"])
                .order_by(MCPConfig.config_id)]
        sel = selection(world["ai_a"], silo=silos[0], skills=skills[:skills_n], mcps=mcps[:mcps_n])
        db.commit()

        def call():
            return client.post(base(world["app_id"]) + "/messages", headers=world["alice"],
                               data=turn_form("hello", sel))

        return measure(test_engine, call)

    def _compare(self, client, world, test_engine, label, exc, **scale):
        small = self._turn(client, world, test_engine, SMALL, **{k: SMALL if v else 2 for k, v in scale.items()})
        large = self._turn(client, world, test_engine, LARGE, **{k: LARGE if v else 2 for k, v in scale.items()})
        print(f"\nBUDGET turn[{label}] small={small.count} ({small.per_engine()}) large={large.count} ({large.per_engine()})")
        assert_budget(small, large, ceiling=TURN_CEILING, label=f"POST /messages [{label}]", growth_exc=exc)

    def test_turn_does_not_grow_with_the_app_data(self, client, world, fakes, test_engine):
        """The App has 3 vs 30 of everything; the selection stays 1 silo, 2 skills, 2 MCP configs."""
        self._compare(client, world, test_engine, "fixed-selection", AssertionError)

    @pytest.mark.xfail(strict=True, raises=SkillRefreshGrowth, reason=(
        "Product finding (step_016): one SELECT per SELECTED skill (+1 each). The Skill rows loaded by the resolver in "
        "one query are expired by a commit before create_agent -> tools/agentTools._resolve_skills_for_prompt -> "
        "skill_tools.resolve_skills reads skill.is_enabled / name, and each attribute read refreshes one row. Bounded "
        "by MAX_SELECTION_ITEMS (50); independent of the number of skills of the App."))
    def test_turn_does_not_grow_with_the_number_of_selected_skills(self, client, world, fakes, test_engine):
        self._compare(client, world, test_engine, "skills-scale", SkillRefreshGrowth, skills_n=True)

    def test_turn_does_not_grow_with_the_number_of_selected_mcp_configs(self, client, world, fakes, test_engine):
        self._compare(client, world, test_engine, "mcps-scale", McpGrowth, mcps_n=True)


def _session(client):
    from db.database import get_db

    return next(client.app.dependency_overrides[get_db]())
