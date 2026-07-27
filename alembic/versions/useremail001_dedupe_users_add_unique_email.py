"""Merge duplicate User rows (same email) and add a unique constraint on User.email.

Fixes the OIDC first-login race in ``UserService.get_or_create_user`` (check-then-insert
with no DB-level uniqueness) that could create 2-3 ``User`` rows sharing the same email.
The application-level race fix lives in a separate change; this migration only repairs
existing data and closes the schema gap that let it happen.

Data-merge strategy (irreversible - see downgrade note below):

For every email with more than one ``User`` row, we pick a canonical row using an
activity score - ``count(owned App) + count(APIKey) + count(AppCollaborator)
+ count(usage_records) + count(MarketplaceUsage)`` - tie-broken by the lowest
``user_id`` (oldest row). All "loser" rows for that email are then folded into the
canonical row before being deleted:

- ``App.owner_id``, ``APIKey.user_id`` (NO ACTION FKs) - reassigned to canonical.
- ``AppCollaborator.user_id`` (NO ACTION FK) - reassigned to canonical unless canonical
  already has a collaborator row for the same ``app_id``, in which case the loser's row
  is dropped instead (avoids a duplicate collaborator entry).
- ``AppCollaborator.invited_by`` (SET NULL FK, not in the original FK table but found via
  grep for ``ForeignKey('User.user_id')`` across backend/models/) - reassigned to
  canonical to preserve "who invited" attribution instead of relying on SET NULL.
- ``subscriptions.user_id`` / ``user_credentials.user_id`` (CASCADE, 1:1 unique) -
  reassigned only if canonical doesn't already have one; otherwise the loser's row is
  left in place and is removed by the CASCADE when the loser ``User`` row is deleted
  (logged via RAISE NOTICE - rare edge case).
- ``usage_records`` (CASCADE, unique on ``(user_id, billing_period_start)``) and
  ``MarketplaceUsage`` (CASCADE, unique on ``(user_id, year, month)``) - overlapping
  periods are summed (``call_count``) into canonical's row and the loser's row dropped;
  non-overlapping periods are reassigned.
- ``AgentMarketplaceRating`` (CASCADE, unique on ``(profile_id, user_id)``) - if both
  duplicates rated the same profile, the more recently ``updated_at`` rating wins and
  the other is dropped; otherwise reassigned.
- ``Conversation.user_id`` and ``crawl_job.triggered_by_user_id`` (SET NULL, nullable) -
  reassigned explicitly rather than relying on SET NULL, so chat history / crawl
  attribution isn't orphaned.
- ``refresh_tokens.user_id`` (CASCADE, no uniqueness) - left untouched; stale sessions on
  the loser row are simply cascade-deleted with it.

Revision ID: useremail001
Revises: 20260717_conversation_starters
Create Date: 2026-07-24
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'useremail001'
down_revision = '20260717_conversation_starters'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Data fix: merge duplicate User rows sharing the same email -----------------
    # NOTE: this data merge is NOT reversible (rows are combined/deleted). See the
    # downgrade() docstring below.
    op.execute("""
    DO $$
    DECLARE
        dup_email   RECORD;
        canonical_id INTEGER;
        loser       RECORD;
    BEGIN
        FOR dup_email IN
            SELECT email
            FROM "User"
            WHERE email IS NOT NULL
            GROUP BY email
            HAVING COUNT(*) > 1
        LOOP
            -- Canonical = highest activity score, tie-broken by lowest (oldest) user_id.
            SELECT u.user_id INTO canonical_id
            FROM "User" u
            WHERE u.email = dup_email.email
            ORDER BY
                (
                    (SELECT COUNT(*) FROM "App" a WHERE a.owner_id = u.user_id) +
                    (SELECT COUNT(*) FROM "APIKey" k WHERE k.user_id = u.user_id) +
                    (SELECT COUNT(*) FROM "AppCollaborator" c WHERE c.user_id = u.user_id) +
                    (SELECT COUNT(*) FROM usage_records ur WHERE ur.user_id = u.user_id) +
                    (SELECT COUNT(*) FROM "MarketplaceUsage" mu WHERE mu.user_id = u.user_id)
                ) DESC,
                u.user_id ASC
            LIMIT 1;

            FOR loser IN
                SELECT user_id FROM "User" WHERE email = dup_email.email AND user_id <> canonical_id
            LOOP
                -- App.owner_id (NO ACTION FK) -- reassign
                UPDATE "App" SET owner_id = canonical_id WHERE owner_id = loser.user_id;

                -- APIKey.user_id (NO ACTION FK) -- reassign
                UPDATE "APIKey" SET user_id = canonical_id WHERE user_id = loser.user_id;

                -- AppCollaborator.user_id (NO ACTION FK) -- reassign unless canonical
                -- already collaborates on the same app, then drop the loser's duplicate row.
                UPDATE "AppCollaborator" ac
                SET user_id = canonical_id
                WHERE ac.user_id = loser.user_id
                  AND NOT EXISTS (
                      SELECT 1 FROM "AppCollaborator" ac2
                      WHERE ac2.app_id = ac.app_id AND ac2.user_id = canonical_id
                  );

                DELETE FROM "AppCollaborator" WHERE user_id = loser.user_id;

                -- AppCollaborator.invited_by (SET NULL FK) -- reassign attribution explicitly
                UPDATE "AppCollaborator" SET invited_by = canonical_id WHERE invited_by = loser.user_id;

                -- subscriptions (CASCADE, 1:1 unique) -- reassign only if canonical has none
                IF NOT EXISTS (SELECT 1 FROM subscriptions WHERE user_id = canonical_id) THEN
                    UPDATE subscriptions SET user_id = canonical_id WHERE user_id = loser.user_id;
                ELSIF EXISTS (SELECT 1 FROM subscriptions WHERE user_id = loser.user_id) THEN
                    RAISE NOTICE 'user email-merge: subscription row for loser user_id % (email %) left in place to cascade-delete; canonical user_id % already has one.', loser.user_id, dup_email.email, canonical_id;
                END IF;

                -- user_credentials (CASCADE, 1:1 unique) -- reassign only if canonical has none
                IF NOT EXISTS (SELECT 1 FROM user_credentials WHERE user_id = canonical_id) THEN
                    UPDATE user_credentials SET user_id = canonical_id WHERE user_id = loser.user_id;
                ELSIF EXISTS (SELECT 1 FROM user_credentials WHERE user_id = loser.user_id) THEN
                    RAISE NOTICE 'user email-merge: user_credentials row for loser user_id % (email %) left in place to cascade-delete; canonical user_id % already has one.', loser.user_id, dup_email.email, canonical_id;
                END IF;

                -- usage_records (CASCADE, unique on user_id+billing_period_start) --
                -- sum overlapping periods into canonical, then drop loser's dupes, then reassign the rest.
                UPDATE usage_records ur_c
                SET call_count = ur_c.call_count + ur_l.call_count,
                    updated_at = GREATEST(ur_c.updated_at, ur_l.updated_at)
                FROM usage_records ur_l
                WHERE ur_c.user_id = canonical_id
                  AND ur_l.user_id = loser.user_id
                  AND ur_c.billing_period_start = ur_l.billing_period_start;

                DELETE FROM usage_records ur_l
                WHERE ur_l.user_id = loser.user_id
                  AND EXISTS (
                      SELECT 1 FROM usage_records ur_c
                      WHERE ur_c.user_id = canonical_id
                        AND ur_c.billing_period_start = ur_l.billing_period_start
                  );

                UPDATE usage_records SET user_id = canonical_id WHERE user_id = loser.user_id;

                -- MarketplaceUsage (CASCADE, unique on user_id+year+month) -- same aggregate-or-reassign logic
                UPDATE "MarketplaceUsage" mu_c
                SET call_count = mu_c.call_count + mu_l.call_count,
                    updated_at = GREATEST(mu_c.updated_at, mu_l.updated_at)
                FROM "MarketplaceUsage" mu_l
                WHERE mu_c.user_id = canonical_id
                  AND mu_l.user_id = loser.user_id
                  AND mu_c.year = mu_l.year
                  AND mu_c.month = mu_l.month;

                DELETE FROM "MarketplaceUsage" mu_l
                WHERE mu_l.user_id = loser.user_id
                  AND EXISTS (
                      SELECT 1 FROM "MarketplaceUsage" mu_c
                      WHERE mu_c.user_id = canonical_id
                        AND mu_c.year = mu_l.year
                        AND mu_c.month = mu_l.month
                  );

                UPDATE "MarketplaceUsage" SET user_id = canonical_id WHERE user_id = loser.user_id;

                -- AgentMarketplaceRating (CASCADE, unique on profile_id+user_id) -- keep the
                -- most-recently-updated rating on conflict, then reassign the rest.
                UPDATE "AgentMarketplaceRating" r_c
                SET rating = r_l.rating,
                    updated_at = r_l.updated_at
                FROM "AgentMarketplaceRating" r_l
                WHERE r_c.user_id = canonical_id
                  AND r_l.user_id = loser.user_id
                  AND r_c.profile_id = r_l.profile_id
                  AND r_l.updated_at > r_c.updated_at;

                DELETE FROM "AgentMarketplaceRating" r_l
                WHERE r_l.user_id = loser.user_id
                  AND EXISTS (
                      SELECT 1 FROM "AgentMarketplaceRating" r_c
                      WHERE r_c.user_id = canonical_id
                        AND r_c.profile_id = r_l.profile_id
                  );

                UPDATE "AgentMarketplaceRating" SET user_id = canonical_id WHERE user_id = loser.user_id;

                -- Conversation.user_id (SET NULL, nullable) -- reassign explicitly, don't orphan chat history
                UPDATE "Conversation" SET user_id = canonical_id WHERE user_id = loser.user_id;

                -- crawl_job.triggered_by_user_id (SET NULL, nullable) -- reassign explicitly
                UPDATE crawl_job SET triggered_by_user_id = canonical_id WHERE triggered_by_user_id = loser.user_id;

                -- refresh_tokens.user_id (CASCADE, no uniqueness) -- intentionally left alone;
                -- stale sessions on the loser row cascade-delete with it below.
            END LOOP;

            -- All loser rows for this email are now safe to delete.
            DELETE FROM "User" WHERE email = dup_email.email AND user_id <> canonical_id;
        END LOOP;
    END $$;
    """)

    # --- Schema fix: prevent this from ever happening again --------------------------
    op.create_unique_constraint('uq_user_email', 'User', ['email'])


def downgrade() -> None:
    # The row merge performed in upgrade() is NOT reversible -- duplicate rows were
    # combined (usage/rating data summed, FKs repointed) and the loser rows deleted.
    # There is no data to restore. Downgrade only removes the schema constraint so a
    # subsequent upgrade path (or manual recovery) isn't blocked by it.
    op.drop_constraint('uq_user_email', 'User', type_='unique')
