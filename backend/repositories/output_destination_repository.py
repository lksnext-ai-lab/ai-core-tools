"""Data access for output destinations."""

from models.output_delivery import OutputDestination
from sqlalchemy.orm import Session


class OutputDestinationRepository:
    """Stateless repository for OutputDestination (create/save commit; the rest never does)."""

    @staticmethod
    def get_by_id_and_app_id(db: Session, destination_id: int, app_id: int) -> OutputDestination | None:
        """Return the destination only when it belongs to the given app."""
        return db.query(OutputDestination).filter(
            OutputDestination.id == destination_id, OutputDestination.app_id == app_id,
        ).one_or_none()

    @staticmethod
    def list_enabled_by_app(db: Session, app_id: int) -> list[OutputDestination]:
        """Enabled destinations of an app ordered by name."""
        return db.query(OutputDestination).filter_by(app_id=app_id, enabled=True).order_by(OutputDestination.name).all()

    @staticmethod
    def create(db: Session, destination: OutputDestination) -> OutputDestination:
        """Insert, commit and refresh. May raise IntegrityError (the caller rolls back)."""
        db.add(destination)
        db.commit()
        db.refresh(destination)
        return destination

    @staticmethod
    def save(db: Session, destination: OutputDestination) -> OutputDestination:
        """Commit pending changes and refresh. May raise IntegrityError (the caller rolls back)."""
        db.commit()
        db.refresh(destination)
        return destination

    @staticmethod
    def delete(db: Session, destination: OutputDestination) -> None:
        """Mark the destination for deletion. Does not commit."""
        db.delete(destination)

    @staticmethod
    def deactivate_with_bindings(db: Session, destination: OutputDestination) -> None:
        """Disable the destination and every one of its bindings. Does not commit."""
        destination.enabled = False
        for binding in destination.bindings:
            binding.enabled = False
