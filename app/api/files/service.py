import os
import uuid
from flask import request
from extensions import db
from model.agent import Agent
from api.files.utils import FileUtils
from api.shared.session_utils import SessionUtils
from utils.logger import get_logger
from utils.error_handlers import ValidationError, NotFoundError, safe_execute

logger = get_logger(__name__)


class FileService:
    @staticmethod
    def attach_file(agent_id: int, file):
        """Upload a file for use in chat conversations."""
        try:
            # Get agent
            agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
            if agent is None:
                raise NotFoundError(f"Agent with ID {agent_id} not found", "agent")
            
            # Validate file upload
            if not file or not file.filename:
                raise ValidationError('No file provided')
            
            # Process file upload
            attachment_path = FileUtils.process_file_upload(file)
            if not attachment_path:
                raise ValidationError('Failed to process file upload')
            
            # Generate file reference
            file_reference = str(uuid.uuid4())
            
            # Store file reference in session
            file_info = {
                'path': attachment_path,
                'filename': file.filename,
                'content_type': file.content_type,
                'agent_id': agent_id,
                'uploaded_at': '2024-04-04T12:00:00Z'  # In production, use actual timestamp
            }
            
            SessionUtils.add_attached_file(file_reference, file_info)
            
            logger.info(f"File attached for agent {agent_id}: {file.filename} -> {file_reference}")
            
            return {
                "status": "success",
                "file_reference": file_reference,
                "filename": file.filename,
                "content_type": file.content_type,
                "message": "File attached successfully"
            }
            
        except Exception as e:
            logger.error(f"Error attaching file: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def detach_file(agent_id: int, file_reference: str):
        """Remove an attached file from the session."""
        try:
            # Get agent
            agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
            if agent is None:
                raise NotFoundError(f"Agent with ID {agent_id} not found", "agent")
            
            # Check if file exists in session
            file_info = SessionUtils.get_attached_file(file_reference)
            if not file_info:
                raise NotFoundError(f"File reference {file_reference} not found", "file")
            
            # Clean up file from disk
            if os.path.exists(file_info['path']):
                try:
                    os.remove(file_info['path'])
                    logger.info(f"Removed file from disk: {file_info['path']}")
                except Exception as e:
                    logger.warning(f"Failed to remove file from disk: {e}")
            
            # Remove from session
            SessionUtils.remove_attached_file(file_reference)
            
            logger.info(f"File detached for agent {agent_id}: {file_reference}")
            
            return {
                "status": "success",
                "message": "File removed successfully"
            }
            
        except Exception as e:
            logger.error(f"Error detaching file: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def list_attached_files(agent_id: int):
        """List all files attached to the current session for this agent."""
        try:
            # Get agent
            agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
            if agent is None:
                raise NotFoundError(f"Agent with ID {agent_id} not found", "agent")
            
            # Get attached files from session
            attached_files = SessionUtils.get_attached_files()
            
            # Filter files for this agent
            agent_files = {
                ref: info for ref, info in attached_files.items() 
                if info.get('agent_id') == agent_id
            }
            
            # Clean up references to non-existent files
            valid_files = {}
            for ref, info in agent_files.items():
                if os.path.exists(info['path']):
                    valid_files[ref] = {
                        'filename': info['filename'],
                        'content_type': info['content_type'],
                        'uploaded_at': info['uploaded_at']
                    }
                else:
                    # Remove invalid reference
                    SessionUtils.remove_attached_file(ref)
            
            return {
                "status": "success",
                "files": valid_files,
                "count": len(valid_files)
            }
            
        except Exception as e:
            logger.error(f"Error listing attached files: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def get_referenced_files(agent_id: int, file_references: list):
        """Get file information for referenced files."""
        try:
            if not file_references:
                return []
            
            attached_files = SessionUtils.get_attached_files()
            referenced_files = []
            
            for file_ref in file_references:
                if file_ref in attached_files:
                    file_info = attached_files[file_ref]
                    # Verify the file is for this agent
                    if file_info.get('agent_id') == agent_id and os.path.exists(file_info['path']):
                        referenced_files.append(file_info)
                    else:
                        logger.warning(f"File reference {file_ref} not found or invalid for agent {agent_id}")
                else:
                    logger.warning(f"File reference {file_ref} not found in session")
            
            return referenced_files
            
        except Exception as e:
            logger.error(f"Error getting referenced files: {str(e)}", exc_info=True)
            return [] 