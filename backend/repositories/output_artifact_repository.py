"""Data access for output artifacts. Never commits."""

from collections.abc import Collection
from datetime import datetime

from models.output_delivery import OutputArtifact, OutputDelivery
from repositories.output_delivery_repository import _body_needed_clause
from sqlalchemy.orm import Session


class OutputArtifactRepository:
    """Stateless repository for OutputArtifact."""

    @staticmethod
    def file_ids_for_run(db: Session, run_id: int) -> set[str]:
        """File ids already captured as artifacts for a run."""
        return {row.file_id for row in db.query(OutputArtifact).filter_by(run_id=run_id).all()}

    @staticmethod
    def all_object_keys(db: Session) -> set[str]:
        """Non-empty spool object keys referenced by any artifact."""
        return {key for (key,) in db.query(OutputArtifact.object_key).all() if key}

    @staticmethod
    def delete_unneeded(db: Session, now: datetime, statuses: Collection[str]) -> None:
        """Bulk-delete artifacts whose run has no delivery that can still send."""
        still_needed = db.query(OutputDelivery.id).filter(
            OutputDelivery.run_id == OutputArtifact.run_id, _body_needed_clause(now, statuses),
        ).exists()
        db.query(OutputArtifact).filter(~still_needed).delete(synchronize_session=False)

    @staticmethod
    def add(db: Session, artifact: OutputArtifact) -> None:
        """Add an artifact to the session."""
        db.add(artifact)
