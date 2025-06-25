from flask import session
from utils.logger import get_logger

logger = get_logger(__name__)

MSG_LIST = "MSG_LIST"


class SessionUtils:
    @staticmethod
    def get_attached_files():
        """Get attached files from session."""
        return session.get('attached_files', {})
    
    @staticmethod
    def add_attached_file(file_reference: str, file_info: dict):
        """Add a file reference to session."""
        if 'attached_files' not in session:
            session['attached_files'] = {}
        
        session['attached_files'][file_reference] = file_info
        session.modified = True
        logger.info(f"Added file to session: {file_reference}")
    
    @staticmethod
    def remove_attached_file(file_reference: str):
        """Remove a file reference from session."""
        if 'attached_files' in session and file_reference in session['attached_files']:
            del session['attached_files'][file_reference]
            session.modified = True
            logger.info(f"Removed file from session: {file_reference}")
    
    @staticmethod
    def get_attached_file(file_reference: str):
        """Get a specific file reference from session."""
        attached_files = session.get('attached_files', {})
        return attached_files.get(file_reference)
    
    @staticmethod
    def add_message_to_session(message: str):
        """Add a message to the session message list."""
        if MSG_LIST not in session:
            session[MSG_LIST] = []
        session[MSG_LIST].append(message)
        session.modified = True
    
    @staticmethod
    def clear_messages():
        """Clear all messages from session."""
        if MSG_LIST in session:
            session[MSG_LIST] = []
            session.modified = True
    
    @staticmethod
    def get_messages():
        """Get all messages from session."""
        return session.get(MSG_LIST, []) 