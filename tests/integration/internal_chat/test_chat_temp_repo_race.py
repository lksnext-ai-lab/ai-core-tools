"""Two simultaneous first uploads to one conversation create ONE temp repository (and silo), not two.

Real concurrency: committed data and one session per thread (the ``cworld`` harness of the concurrency tests); both
threads are held after their first "does it exist?" lookup until the other has done it too, so without the advisory
lock both would create it.
"""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from models.agent import Agent
from models.repository import PLAYGROUND_MEDIA_REPO_TYPE, Repository
from services.playground_media_service import PlaygroundMediaService
from tests.integration.internal_chat.test_chat_isolation_concurrency import cworld  # noqa: F401


def test_two_concurrent_first_uploads_create_one_temp_repository(test_engine, cworld, monkeypatch):  # noqa: F811
    with Session(test_engine) as setup:
        agent = Agent(name=f"race-{cworld.tag}", description="d", system_prompt="p", has_memory=True,
                      app_id=cworld.app_id, service_id=cworld.ai["x"])
        setup.add(agent)
        setup.commit()
        agent_id = agent.agent_id
    session_id = f"conv_{agent_id}_{uuid.uuid4()}"

    real_lookup = PlaygroundMediaService.get_temp_repository
    barrier = threading.Barrier(2, timeout=5)
    seen_first = threading.local()

    def lookup(app_id, agent_id_, session_id_, db):
        found = real_lookup(app_id, agent_id_, session_id_, db)
        if not getattr(seen_first, "done", False):
            seen_first.done = True
            try:
                barrier.wait()  # both threads have looked, and both found nothing
            except threading.BrokenBarrierError:
                pass
        return found

    monkeypatch.setattr(PlaygroundMediaService, "get_temp_repository", staticmethod(lookup))

    def upload():
        with Session(test_engine) as session:
            repo = PlaygroundMediaService.get_or_create_temp_repository(
                cworld.app_id, agent_id, session_id, session, embedding_service_id=cworld.emb
            )
            return repo.repository_id, repo.silo_id

    with ThreadPoolExecutor(2) as pool:
        results = [f.result(timeout=60) for f in [pool.submit(upload), pool.submit(upload)]]

    with Session(test_engine) as check:
        rows = check.query(Repository).filter(
            Repository.app_id == cworld.app_id, Repository.type == PLAYGROUND_MEDIA_REPO_TYPE,
            Repository.name.like(f"%{session_id}")).all()
        assert len(rows) == 1, [r.repository_id for r in rows]
    assert results[0] == results[1] == (rows[0].repository_id, rows[0].silo_id)
