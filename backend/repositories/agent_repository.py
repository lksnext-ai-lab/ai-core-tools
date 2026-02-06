from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from models.agent import Agent, AgentMCP, AgentTool, AgentSkill
from models.ocr_agent import OCRAgent
from models.ai_service import AIService
from models.silo import Silo
from models.output_parser import OutputParser
from models.mcp_config import MCPConfig
from models.skill import Skill
from repositories.ai_service_repository import AIServiceRepository
from repositories.silo_repository import SiloRepository
from repositories.output_parser_repository import OutputParserRepository
from repositories.mcp_config_repository import MCPConfigRepository
from repositories.skill_repository import SkillRepository


class AgentRepository:
    """Repository class for Agent database operations"""
    
    # ==================== BASIC AGENT OPERATIONS ====================
    
    @staticmethod
    def get_by_id(db: Session, agent_id: int) -> Optional[Agent]:
        """Get agent by ID from Agent table"""
        return db.query(Agent).filter(Agent.agent_id == agent_id).first()
    
    @staticmethod
    def get_ocr_agent_by_id(db: Session, agent_id: int) -> Optional[OCRAgent]:
        """Get OCR agent by ID from OCRAgent table"""
        return db.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
    
    @staticmethod
    def get_agent_by_id_and_type(db: Session, agent_id: int, agent_type: str = 'basic') -> Agent | OCRAgent:
        """Get agent by ID and type"""
        if agent_type == 'ocr' or agent_type == 'ocr_agent':
            return AgentRepository.get_ocr_agent_by_id(db, agent_id)
        elif agent_type == 'basic' or agent_type == 'agent':
            return AgentRepository.get_by_id(db, agent_id)
        else:
            agent = AgentRepository.get_by_id(db, agent_id)
            if not agent:
                agent = AgentRepository.get_ocr_agent_by_id(db, agent_id)
            return agent
    
    @staticmethod
    def get_by_app_id(db: Session, app_id: int) -> List[Agent]:
        """Get all agents for a specific app"""
        return db.query(Agent).filter(Agent.app_id == app_id).order_by(Agent.create_date.desc()).all()
    
    @staticmethod
    def get_tool_agents_by_app_id(db: Session, app_id: int, exclude_agent_id: Optional[int] = None) -> List[Agent]:
        """Get agents that are marked as tools for a specific app"""
        query = db.query(Agent).filter(
            Agent.app_id == app_id,
            Agent.is_tool == True
        )
        if exclude_agent_id:
            query = query.filter(Agent.agent_id != exclude_agent_id)
        
        return query.all()
    
    @staticmethod
    def create(db: Session, agent: Agent) -> Agent:
        """Create a new agent"""
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent
    
    @staticmethod
    def update(db: Session, agent: Agent) -> Agent:
        """Update an existing agent"""
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent
    
    @staticmethod
    def delete(db: Session, agent: Agent) -> bool:
        """Delete an agent"""
        try:
            db.delete(agent)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
    
    @staticmethod
    def delete_by_id(db: Session, agent_id: int) -> bool:
        """Delete an agent by its ID (checks both Agent and OCRAgent tables)"""
        try:
            # Check both Agent and OCRAgent tables
            agent = AgentRepository.get_by_id(db, agent_id)
            if not agent:
                agent = AgentRepository.get_ocr_agent_by_id(db, agent_id)
            
            if agent:
                # First remove all references to this agent as a tool
                AgentRepository.remove_tool_references(db, agent_id)
                # Then delete the agent
                db.delete(agent)
                db.commit()
                return True
            return False
        except Exception:
            db.rollback()
            return False
    
    # ==================== AGENT ASSOCIATIONS ====================
    
    @staticmethod
    def get_agent_tool_associations(db: Session, agent_id: int) -> List[AgentTool]:
        """Get all tool associations for an agent"""
        return db.query(AgentTool).filter(AgentTool.agent_id == agent_id).all()
    
    @staticmethod
    def get_agent_mcp_associations(db: Session, agent_id: int) -> List[AgentMCP]:
        """Get all MCP associations for an agent"""
        return db.query(AgentMCP).filter(AgentMCP.agent_id == agent_id).all()
    
    @staticmethod
    def delete_agent_tool_association(db: Session, association: AgentTool) -> None:
        """Delete an agent tool association"""
        db.delete(association)
    
    @staticmethod
    def delete_agent_mcp_association(db: Session, association: AgentMCP) -> None:
        """Delete an agent MCP association"""
        db.delete(association)

    @staticmethod
    def get_agent_skill_associations(db: Session, agent_id: int) -> List[AgentSkill]:
        """Get all skill associations for an agent"""
        return db.query(AgentSkill).filter(AgentSkill.agent_id == agent_id).all()

    @staticmethod
    def delete_agent_skill_association(db: Session, association: AgentSkill) -> None:
        """Delete an agent skill association"""
        db.delete(association)

    @staticmethod
    def create_agent_skill_association(db: Session, agent_id: int, skill_id: int, description: Optional[str] = None) -> AgentSkill:
        """Create a new agent skill association"""
        association = AgentSkill(
            agent_id=agent_id,
            skill_id=skill_id,
            description=description
        )
        db.add(association)
        return association

    @staticmethod
    def create_agent_tool_association(db: Session, agent_id: int, tool_id: int, description: Optional[str] = None) -> AgentTool:
        """Create a new agent tool association"""
        association = AgentTool(
            agent_id=agent_id,
            tool_id=tool_id,
            description=description
        )
        db.add(association)
        return association
    
    @staticmethod
    def create_agent_mcp_association(db: Session, agent_id: int, config_id: int, description: Optional[str] = None) -> AgentMCP:
        """Create a new agent MCP association"""
        association = AgentMCP(
            agent_id=agent_id,
            config_id=config_id,
            description=description
        )
        db.add(association)
        return association
    
    @staticmethod
    def remove_tool_references(db: Session, tool_id: int) -> None:
        """Remove all tool associations where this agent is used as a tool"""
        db.query(AgentTool).filter(AgentTool.tool_id == tool_id).delete()
        db.commit()
    
    @staticmethod
    def get_valid_tool_ids(db: Session, tool_ids: List[int]) -> List[int]:
        """Get valid tool IDs (agents that are marked as tools)"""
        tools_query = db.query(Agent.agent_id).filter(
            Agent.agent_id.in_(tool_ids),
            Agent.is_tool == True
        )
        return [id for (id,) in tools_query]
    
    # ==================== RELATED DATA QUERIES ====================
    
    @staticmethod
    def get_ai_services_by_app_id(db: Session, app_id: int) -> List[AIService]:
        """Get all AI services for a specific app"""
        return AIServiceRepository.get_by_app_id(db, app_id)
    
    @staticmethod
    def get_ai_services_dict_by_app_id(db: Session, app_id: int) -> Dict[int, Dict[str, str]]:
        """Get AI services as a dictionary for quick lookup"""
        ai_services = AgentRepository.get_ai_services_by_app_id(db, app_id)
        return {
            s.service_id: {"name": s.name, "model_name": s.description, "provider": s.provider} 
            for s in ai_services
        }
    
    @staticmethod
    def get_silos_by_app_id(db: Session, app_id: int) -> List[Silo]:
        """Get all silos for a specific app"""
        return SiloRepository.get_by_app_id(app_id, db)
    
    @staticmethod
    def get_output_parsers_by_app_id(db: Session, app_id: int) -> List[OutputParser]:
        """Get all output parsers for a specific app"""
        parser_repo = OutputParserRepository()
        return parser_repo.get_by_app_id(db, app_id)
    
    @staticmethod
    def get_mcp_configs_by_app_id(db: Session, app_id: int) -> List[MCPConfig]:
        """Get all MCP configs for a specific app"""
        return MCPConfigRepository.get_all_by_app_id(db, app_id)

    @staticmethod
    def get_skills_by_app_id(db: Session, app_id: int) -> List[Skill]:
        """Get all skills for a specific app"""
        return SkillRepository.get_all_by_app_id(db, app_id)

    @staticmethod
    def get_silo_by_id(db: Session, silo_id: int) -> Optional[Silo]:
        """Get silo by ID"""
        return SiloRepository.get_by_id(silo_id, db)
    
    @staticmethod
    def get_output_parser_by_id(db: Session, parser_id: int) -> Optional[OutputParser]:
        """Get output parser by ID"""
        parser_repo = OutputParserRepository()
        return parser_repo.get_by_id(db, parser_id)
    
    @staticmethod
    def get_silo_with_metadata_definition(db: Session, silo_id: int) -> Optional[Dict[str, Any]]:
        """Get silo information with metadata definition"""
        silo = AgentRepository.get_silo_by_id(db, silo_id)
        if not silo:
            return None
        
        silo_info = {
            "silo_id": silo.silo_id,
            "name": silo.name,
            "vector_db_type": silo.vector_db_type,
            "metadata_definition": None
        }
        
        # Get metadata definition if it exists
        if silo.metadata_definition_id:
            metadata_parser = AgentRepository.get_output_parser_by_id(db, silo.metadata_definition_id)
            if metadata_parser and metadata_parser.fields:
                silo_info["metadata_definition"] = {
                    "fields": metadata_parser.fields
                }
        
        return silo_info
    
    @staticmethod
    def get_output_parser_info(db: Session, parser_id: int) -> Optional[Dict[str, Any]]:
        """Get output parser information"""
        output_parser = AgentRepository.get_output_parser_by_id(db, parser_id)
        if not output_parser:
            return None
        
        return {
            "parser_id": output_parser.parser_id,
            "name": output_parser.name,
            "description": output_parser.description,
            "fields": output_parser.fields if output_parser.fields else []
        }
    
    # ==================== FORM DATA HELPERS ====================
    
    @staticmethod
    def get_form_data_for_agent(db: Session, app_id: int, agent_id: int) -> Dict[str, List]:
        """Get form data needed for agent editing (consolidating multiple queries)"""
        # Get AI services
        ai_services = AgentRepository.get_ai_services_by_app_id(db, app_id)
        ai_services_list = [{"service_id": s.service_id, "name": s.name} for s in ai_services]
        
        # Get silos
        silos = AgentRepository.get_silos_by_app_id(db, app_id)
        silos_list = [{"silo_id": s.silo_id, "name": s.name} for s in silos]
        
        # Get output parsers
        output_parsers = AgentRepository.get_output_parsers_by_app_id(db, app_id)
        output_parsers_list = [{"parser_id": p.parser_id, "name": p.name} for p in output_parsers]
        
        # Get tools (agents that are marked as tools)
        tools = AgentRepository.get_tool_agents_by_app_id(db, app_id, exclude_agent_id=agent_id)
        tools_list = [{"agent_id": t.agent_id, "name": t.name} for t in tools]
        
        # Get MCP configs
        mcp_configs = AgentRepository.get_mcp_configs_by_app_id(db, app_id)
        mcp_configs_list = [{"config_id": c.config_id, "name": c.name} for c in mcp_configs]

        # Get skills
        skills = AgentRepository.get_skills_by_app_id(db, app_id)
        skills_list = [{"skill_id": s.skill_id, "name": s.name, "description": s.description} for s in skills]

        return {
            'ai_services': ai_services_list,
            'silos': silos_list,
            'output_parsers': output_parsers_list,
            'tools': tools_list,
            'mcp_configs': mcp_configs_list,
            'skills': skills_list
        }
    
    @staticmethod
    def get_agent_associations_dict(db: Session, agent_id: int) -> Dict[str, List]:
        """Get agent's current associations as a dictionary"""
        if agent_id == 0:
            return {'tool_ids': [], 'mcp_ids': [], 'skill_ids': []}

        # Get tool associations
        tool_assocs = AgentRepository.get_agent_tool_associations(db, agent_id)
        agent_tool_ids = [assoc.tool_id for assoc in tool_assocs]

        # Get MCP associations
        mcp_assocs = AgentRepository.get_agent_mcp_associations(db, agent_id)
        agent_mcp_ids = [assoc.config_id for assoc in mcp_assocs]

        # Get skill associations
        skill_assocs = AgentRepository.get_agent_skill_associations(db, agent_id)
        agent_skill_ids = [assoc.skill_id for assoc in skill_assocs]

        return {'tool_ids': agent_tool_ids, 'mcp_ids': agent_mcp_ids, 'skill_ids': agent_skill_ids}
