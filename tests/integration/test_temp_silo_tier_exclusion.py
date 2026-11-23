"""[DECISION] The hidden temp silos of conversations never count against the tier silo quota and are never frozen."""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from tests.integration.test_downgrade_freeze import pro_user, saas_env, tier_config  # noqa: F401  (fixtures)


def _to_free(db, pro_user):
    from models.subscription import SubscriptionTier

    pro_user["sub"].tier = SubscriptionTier.FREE
    db.flush()


def _silos(db, app, real: int, temp: int, temp_newer: bool = True):
    from models.repository import PLAYGROUND_MEDIA_REPO_TYPE, Repository
    from models.silo import Silo

    base = datetime(2025, 1, 1)
    made = {"real": [], "temp": []}
    for i in range(real + temp):
        is_temp = i >= real if temp_newer else i < temp
        silo = Silo(name=f"s{i}", app_id=app.app_id, is_frozen=False)
        silo.create_date = base + timedelta(days=i)
        db.add(silo)
        db.flush()
        if is_temp:
            db.add(Repository(name=f"_playground_1_conv_1_{i}", type=PLAYGROUND_MEDIA_REPO_TYPE, app_id=app.app_id,
                              silo_id=silo.silo_id))
        made["temp" if is_temp else "real"].append(silo.silo_id)
    db.flush()
    return made


def test_temp_silos_do_not_block_creating_a_real_silo_at_the_limit(db, pro_user, saas_env):  # noqa: F811
    from services.tier_enforcement_service import TierEnforcementService

    app = pro_user["app"]
    _to_free(db, pro_user)  # free: 2 silos
    _silos(db, app, real=1, temp=5)
    TierEnforcementService.check_resource_limit(db, app.app_id, "silos")  # 1 real + 5 temp: still below 2


def test_the_real_silos_still_count(db, pro_user, saas_env):  # noqa: F811
    from services.freeze_service import FreezeService
    from services.tier_enforcement_service import TierEnforcementService

    app = pro_user["app"]
    _to_free(db, pro_user)
    _silos(db, app, real=2, temp=3)
    with pytest.raises(HTTPException) as exc:
        TierEnforcementService.check_resource_limit(db, app.app_id, "silos")
    assert exc.value.status_code == 403


def test_a_downgrade_keeps_the_real_silos_and_never_freezes_temp_ones(db, pro_user, saas_env):  # noqa: F811
    from models.silo import Silo
    from services.freeze_service import FreezeService

    app, user = pro_user["app"], pro_user["user"]
    made = _silos(db, app, real=3, temp=3, temp_newer=True)  # the temp ones are NEWER than every real one
    FreezeService.apply_freeze(db, user.user_id, "free")  # free: 2 silos
    db.flush()
    db.expire_all()
    state = {s.silo_id: s.is_frozen for s in db.query(Silo).filter(Silo.app_id == app.app_id)}
    assert [state[i] for i in made["temp"]] == [False, False, False]  # never frozen
    # the two newest REAL silos keep their slots, the oldest real one is frozen (temp ones took no slot)
    assert [state[i] for i in made["real"]] == [True, False, False]


def test_a_temp_silo_can_still_be_created_when_the_real_quota_is_full(db, pro_user, saas_env):  # noqa: F811
    from models.repository import Repository
    from services.freeze_service import FreezeService
    from services.repository_service import RepositoryService
    from tests.factories import EmbeddingServiceFactory, configure_factories

    app = pro_user["app"]
    _to_free(db, pro_user)
    _silos(db, app, real=2, temp=0)
    configure_factories(db)
    emb = EmbeddingServiceFactory(app=app)
    db.flush()
    repo = Repository(name="_playground_1_conv_1_new", type="playground_media", status="active", app_id=app.app_id)
    created = RepositoryService.create_repository(repo, embedding_service_id=emb.service_id, db=db)
    assert created.silo_id is not None
