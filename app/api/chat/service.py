import os
from flask import current_app, request
from extensions import db
from model.agent import Agent
from tools.agentTools import create_agent, prepare_agent_config, parse_agent_response, setup_tracer
from api.shared.session_utils import SessionUtils
from api.files.utils import FileUtils
from api.files.service import FileService
from tools.agentTools import MCPClientManager
from utils.logger import get_logger
from utils.error_handlers import safe_execute
from services.agent_cache_service import CheckpointerCacheService

logger = get_logger(__name__)


class ChatService:
    @staticmethod
    async def process_agent_request_with_attachments(agent, question, tracer, search_params, attachment_path=None, referenced_files=None):
        """
        Processes the agent request asynchronously with support for multiple file attachments.
        """
        try:
            logger.info(f"Processing agent request with attachments for agent {agent.agent_id}: {question[:50]}...")
            
            # Create agent instance
            agent_x = await create_agent(agent, search_params)
            
            # Prepare configuration
            config = prepare_agent_config(agent, tracer)
            
            # Prepare message content
            message_content = question
            
            # Process base64 attachment if present
            if attachment_path:
                attachment_content = FileUtils.process_attachment_for_agent(attachment_path, agent)
                message_content += attachment_content
                logger.info(f"Processed base64 attachment: {attachment_path}")
            
            # Process referenced files if present
            if referenced_files:
                for file_info in referenced_files:
                    attachment_content = FileUtils.process_attachment_for_agent(file_info['path'], agent)
                    message_content += attachment_content
                    logger.info(f"Processed referenced file: {file_info['filename']}")
            
            # Format the message according to the agent's prompt template
            from langchain_core.messages import HumanMessage
            formatted_message = agent.prompt_template.format(question=message_content)
            
            # Invoke agent
            result = await agent_x.ainvoke(
                {"messages": [HumanMessage(content=formatted_message)]}, 
                config
            )
            logger.info("Agent response received")
            
            # Extract response
            from langchain_core.messages import AIMessage
            final_message = next(
                (msg for msg in reversed(result['messages']) if isinstance(msg, AIMessage)), 
                None
            )
            response_text = final_message.content if final_message else str(result)
            
            # Parse response
            parsed_response = parse_agent_response(response_text, agent)
            
            # Clean up base64 attachment file if it was created
            if attachment_path and os.path.exists(attachment_path):
                try:
                    os.remove(attachment_path)
                    logger.info(f"Cleaned up base64 attachment file: {attachment_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up base64 attachment file {attachment_path}: {e}")
            
            # Prepare response data
            return {
                "input": question,
                "generated_text": parsed_response,
                "control": {
                    "temperature": 0.8,
                    "max_tokens": 100,
                    "top_p": 0.9,
                    "frequency_penalty": 0.5,
                    "presence_penalty": 0.5,
                    "stop_sequence": "\n\n"
                },
                "metadata": {
                    "model_name": agent.ai_service.name,
                    "timestamp": "2024-04-04T12:00:00Z",
                    "attachments_processed": (attachment_path is not None) or (referenced_files is not None and len(referenced_files) > 0),
                    "attachment_count": (1 if attachment_path else 0) + (len(referenced_files) if referenced_files else 0)
                }
            }
        
        except Exception as e:
            logger.error(f"Error processing agent request with attachments: {str(e)}", exc_info=True)
            # Clean up base64 attachment file on error
            if attachment_path and os.path.exists(attachment_path):
                try:
                    os.remove(attachment_path)
                    logger.info(f"Cleaned up base64 attachment file on error: {attachment_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up base64 attachment file on error {attachment_path}: {cleanup_error}")
            return {"error": str(e)}, 500
        finally:
            await MCPClientManager().close()

    @staticmethod
    def reset_conversation(agent_id: int):
        """Resets the conversation state for the current session and clears agent cache."""
        try:
            # Clear the message list from session
            SessionUtils.clear_messages()
            
            # Clear all attached files for this agent
            try:
                attached_files = SessionUtils.get_attached_files()
                agent_files = {
                    ref: info for ref, info in attached_files.items() 
                    if info.get('agent_id') == agent_id
                }
                
                # Remove files from disk and session
                for file_ref, file_info in agent_files.items():
                    # Remove from disk
                    if os.path.exists(file_info['path']):
                        try:
                            os.remove(file_info['path'])
                            logger.info(f"Removed file from disk during reset: {file_info['path']}")
                        except Exception as e:
                            logger.warning(f"Failed to remove file from disk during reset {file_info['path']}: {e}")
                    
                    # Remove from session
                    SessionUtils.remove_attached_file(file_ref)
                
                logger.info(f"Cleared {len(agent_files)} attached files for agent {agent_id}")
                
            except Exception as e:
                logger.warning(f"Error clearing attached files during reset: {e}")
            
            # Clear the agent from cache
            CheckpointerCacheService.invalidate_checkpointer(agent_id)
            
            logger.info(f"Reset conversation, cleared cache and files for agent {agent_id}")
            return {"status": "success", "message": "Conversation reset successfully"}
            
        except Exception as e:
            logger.error(f"Error resetting conversation: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def update_request_count(agent):
        """Update request count for the agent."""
        if not hasattr(request, 'api_usage_already_counted'):
            agent.request_count = (agent.request_count or 0) + 1
            result, error = safe_execute(db.session.commit, log_errors=True)
            if error:
                logger.warning(f"Failed to update request count: {error}")

    @staticmethod
    def get_agent(agent_id: int):
        """Get agent from database."""
        return db.session.query(Agent).filter(Agent.agent_id == agent_id).first() 