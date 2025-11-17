from typing import Optional, Union
from sqlalchemy.orm import Session, joinedload, selectinload
from models.agent import Agent, AgentTool
from models.ocr_agent import OCRAgent
from models.silo import Silo
from models.output_parser import OutputParser
from repositories.agent_repository import AgentRepository
from repositories.output_parser_repository import OutputParserRepository
from utils.logger import get_logger

logger = get_logger(__name__)


class AgentExecutionRepository:
    """Repository class for Agent Execution database operations"""
    
    @staticmethod
    def get_agent_with_relationships(db: Session, agent_id: int) -> Optional[Agent]:
        """
        Get agent with all necessary relationships for execution.
        
        Uses eager loading to prevent:
        - N+1 query problems (multiple DB hits for related data)
        - DetachedInstanceError (when accessing relations after session closes)
        - Lazy loading issues in async contexts
        
        This is critical when agents use other agents as tools, as the tool agents
        also need their relationships (ai_service, silo, tool_associations) loaded.
        """
        agent = db.query(Agent).options(
            # Main agent relationships
            joinedload(Agent.silo).joinedload(Silo.embedding_service),
            joinedload(Agent.mcp_associations),
            joinedload(Agent.ai_service),
            joinedload(Agent.output_parser),
            joinedload(Agent.app),
            # Tool agents and their relationships (critical for IACTTool)
            selectinload(Agent.tool_associations).joinedload(AgentTool.tool).joinedload(Agent.ai_service),
            selectinload(Agent.tool_associations).joinedload(AgentTool.tool).joinedload(Agent.silo),
            selectinload(Agent.tool_associations).joinedload(AgentTool.tool).joinedload(Agent.tool_associations)
        ).filter(Agent.agent_id == agent_id).first()
        
        return agent
    
    @staticmethod
    def get_ocr_agent_with_relationships(db: Session, agent_id: int) -> Optional[OCRAgent]:
        """Get OCR agent with all necessary relationships for execution"""
        return db.query(OCRAgent).options(
            joinedload(OCRAgent.ai_service),
            joinedload(OCRAgent.vision_service_rel),
            joinedload(OCRAgent.output_parser)
        ).filter(OCRAgent.agent_id == agent_id).first()
    
    @staticmethod
    def get_output_parser_by_id(db: Session, parser_id: int) -> Optional[OutputParser]:
        """Get output parser by ID - delegates to OutputParserRepository"""
        parser_repo = OutputParserRepository()
        return parser_repo.get_by_id(db, parser_id)
    
    @staticmethod
    def update_agent_request_count(db: Session, agent_id: int) -> bool:
        """Update agent request count"""
        try:
            db_agent = AgentRepository.get_by_id(db, agent_id)
            if db_agent:
                db_agent.request_count = (db_agent.request_count or 0) + 1
                db.commit()
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to update request count for agent {agent_id}: {e}")
            db.rollback()
            return False
    
    @staticmethod
    def get_agent_by_id_and_type(db: Session, agent_id: int, agent_type: str = 'basic') -> Union[Agent, OCRAgent]:
        """Get agent by ID and type - delegates to AgentRepository"""
        return AgentRepository.get_agent_by_id_and_type(db, agent_id, agent_type)
