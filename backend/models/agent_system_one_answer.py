import uuid
from sqlalchemy import Column, Float, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from db.database import Base


class AgentSystemOneAnswer(Base):
    """One System One answer (one question) of one agent execution."""
    __tablename__ = 'agent_system_one_answer'

    answer_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey('agent_execution_event.event_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    question_key = Column(String(40), nullable=False)
    question_type = Column(String(10), nullable=False)
    decision = Column(Text, nullable=True)           # bool / option / level serialized; NULL = undetermined
    probability = Column(Float, nullable=True)
    expected_score = Column(Float, nullable=True)    # score questions only
    confidence = Column(Float, nullable=True)        # choice / score only
    probabilities = Column(JSON, nullable=True)
    state_reduction = Column(String(12), nullable=False)
