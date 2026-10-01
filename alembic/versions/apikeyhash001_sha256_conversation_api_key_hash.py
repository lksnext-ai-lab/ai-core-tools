"""Conversation.api_key_hash: MD5 -> SHA-256.

Conversations created through the public API are tied to the caller by a hash
of its API key. That hash was MD5; it is now SHA-256 (utils.security.hash_api_key).
APIKey stores the raw key, so existing rows are rewritten by recomputing both
digests per key. Conversations whose API key no longer exists keep their MD5
value; no key can reach them anyway.
"""

import hashlib

from alembic import op
import sqlalchemy as sa

revision = "apikeyhash001"
down_revision = "periodic005"
branch_labels = None
depends_on = None

api_key = sa.table("APIKey", sa.column("key", sa.String))
conversation = sa.table("Conversation", sa.column("api_key_hash", sa.String))


def _md5(key: str) -> str:
    # Only used to find the legacy values being migrated away from.
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()


def _sha256(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _rewrite(old_hash, new_hash):
    bind = op.get_bind()
    for (key,) in bind.execute(sa.select(api_key.c.key)):
        bind.execute(
            conversation.update()
            .where(conversation.c.api_key_hash == old_hash(key))
            .values(api_key_hash=new_hash(key))
        )


def upgrade():
    _rewrite(_md5, _sha256)


def downgrade():
    _rewrite(_sha256, _md5)
