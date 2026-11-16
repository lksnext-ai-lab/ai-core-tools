from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models.oidc_identity_link import OIDCIdentityLink


class OIDCIdentityLinkRepository:
    """Repository for explicit, administrator-approved identity links."""

    @staticmethod
    def get_for_scim_external_id(
        db: Session, connection_id: int, external_id: str
    ) -> Optional[OIDCIdentityLink]:
        """Find the approved OIDC mapping for a connection-scoped SCIM ID."""
        statement = (
            select(OIDCIdentityLink)
            .options(joinedload(OIDCIdentityLink.user))
            .where(
                OIDCIdentityLink.connection_id == connection_id,
                OIDCIdentityLink.external_id == external_id,
            )
        )
        return db.execute(statement).scalar_one_or_none()

    @staticmethod
    def add(db: Session, link: OIDCIdentityLink) -> OIDCIdentityLink:
        """Persist an approved mapping."""
        db.add(link)
        db.commit()
        db.refresh(link)
        return link
