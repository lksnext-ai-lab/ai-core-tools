import os
import uuid
import tempfile
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import UploadFile, HTTPException

from tools.PDFTools import extract_text_from_pdf, convert_pdf_to_images, check_pdf_has_text
from utils.logger import get_logger

logger = get_logger(__name__)


class FileReference:
    """Represents a file reference for agent consumption"""
    
    def __init__(self, file_id: str, filename: str, file_type: str, content: str):
        self.file_id = file_id
        self.filename = filename
        self.file_type = file_type
        self.content = content
        self.uploaded_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "content": self.content,
            "uploaded_at": self.uploaded_at.isoformat()
        }


class FileManagementService:
    """Unified file management - used by both public and internal APIs"""
    
    def __init__(self):
        # Persistent file storage on disk
        # Structure: {session_key: {file_id: FileReference}}
        self._files: Dict[str, Dict[str, FileReference]] = {}
        
        # Get TMP_BASE_FOLDER from config
        from utils.config import get_app_config
        app_config = get_app_config()
        self._tmp_base_folder = app_config['TMP_BASE_FOLDER']
        self._persistent_dir = os.path.join(self._tmp_base_folder, "persistent")
        self._temp_dir = os.path.join(self._tmp_base_folder, "uploads")
        
        # Ensure directories exist
        os.makedirs(self._persistent_dir, exist_ok=True)
        os.makedirs(self._temp_dir, exist_ok=True)
        os.makedirs(os.path.join(self._tmp_base_folder, "downloads"), exist_ok=True)
        os.makedirs(os.path.join(self._tmp_base_folder, "images"), exist_ok=True)
        
        # Load existing files from disk
        self._load_persistent_files()
    
    async def upload_file(
        self, 
        file: UploadFile, 
        agent_id: int,
        user_context: Dict = None
    ) -> FileReference:
        """
        Upload file for agent consumption
        
        Args:
            file: Uploaded file
            agent_id: ID of the agent
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            FileReference object
        """
        try:
            # Validate file
            if not file.filename:
                raise HTTPException(status_code=400, detail="No filename provided")
            
            # Generate unique file ID
            file_id = str(uuid.uuid4())
            
            # Determine file type
            file_type = self._get_file_type(file.filename)
            
            # Process file based on type
            content, temp_path = await self._process_file_content(file, file_type)
            
            # Create file reference
            file_ref = FileReference(file_id, file.filename, file_type, content)
            
            # Create session key for this agent and user
            session_key = self._get_session_key(agent_id, user_context)
            
            # Initialize session if not exists
            if session_key not in self._files:
                self._files[session_key] = {}
            
            # Store file reference in session
            self._files[session_key][file_id] = file_ref
            
            # Save file to disk for persistence (including original file)
            await self._save_file_to_disk(session_key, file_id, file_ref, temp_path)
            
            # Clean up temporary file after saving to persistent storage
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            
            logger.info(f"Uploaded file {file.filename} for agent {agent_id}, session {session_key}")
            return file_ref
            
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
    
    async def process_file_for_agent(
        self, 
        file_path: str, 
        agent: Any
    ) -> str:
        """
        Process file for agent consumption - reuse existing PDF tools
        
        Args:
            file_path: Path to the file
            agent: Agent object
            
        Returns:
            Processed content string
        """
        try:
            # Determine file type from path
            file_type = self._get_file_type_from_path(file_path)
            
            if file_type == "pdf":
                # Use existing PDF tools
                return extract_text_from_pdf(file_path)
            elif file_type in ["txt", "md", "json"]:
                # Read text files directly
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                # For other file types, return basic info
                return f"File: {os.path.basename(file_path)} (type: {file_type})"
                
        except Exception as e:
            logger.error(f"Error processing file for agent: {str(e)}")
            return f"Error processing file: {str(e)}"
    
    async def get_file_reference(self, file_id: str) -> Optional[FileReference]:
        """
        Get file reference by ID
        
        Args:
            file_id: File ID
            
        Returns:
            FileReference or None if not found
        """
        return self._files.get(file_id)
    
    async def list_attached_files(
        self, 
        agent_id: int, 
        user_context: Dict = None
    ) -> List[Dict[str, Any]]:
        """
        List attached files for a user session
        
        Args:
            agent_id: ID of the agent
            user_context: User context
            
        Returns:
            List of file references
        """
        try:
            # Get session key for this agent and user
            session_key = self._get_session_key(agent_id, user_context)
            
            # Return files for this session
            if session_key in self._files:
                return [file_ref.to_dict() for file_ref in self._files[session_key].values()]
            else:
                return []
            
        except Exception as e:
            logger.error(f"Error listing attached files: {str(e)}")
            return []
    
    async def remove_file(
        self, 
        file_id: str, 
        agent_id: int,
        user_context: Dict = None
    ) -> bool:
        """
        Remove attached file
        
        Args:
            file_id: File ID to remove
            agent_id: ID of the agent
            user_context: User context
            
        Returns:
            True if removed successfully
        """
        try:
            # Get session key for this agent and user
            session_key = self._get_session_key(agent_id, user_context)
            
            if session_key in self._files and file_id in self._files[session_key]:
                del self._files[session_key][file_id]
                
                # Also remove from disk
                await self._remove_file_from_disk(session_key, file_id)
                
                logger.info(f"Removed file {file_id} from session {session_key}")
                return True
            else:
                logger.warning(f"File {file_id} not found for removal in session {session_key}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing file: {str(e)}")
            return False
    
    def _get_file_type(self, filename: str) -> str:
        """Get file type from filename"""
        if not filename:
            return "unknown"
        
        ext = os.path.splitext(filename)[1].lower()
        
        # PDF files
        if ext == '.pdf':
            return "pdf"
        
        # Text files
        elif ext in ['.txt', '.md', '.json', '.csv']:
            return "text"
        
        # Image files
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            return "image"
        
        # Document files
        elif ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
            return "document"
        
        else:
            return "unknown"
    
    def _get_file_type_from_path(self, file_path: str) -> str:
        """Get file type from file path"""
        return self._get_file_type(os.path.basename(file_path))
    
    async def _process_file_content(self, file: UploadFile, file_type: str) -> tuple[str, str]:
        """
        Process file content based on file type
        
        Args:
            file: Uploaded file
            file_type: Type of file
            
        Returns:
            Tuple of (processed_content, temp_file_path)
        """
        try:
            # Save file temporarily
            temp_path = await self._save_uploaded_file(file)
            
            try:
                if file_type == "pdf":
                    # Use existing PDF tools
                    content = extract_text_from_pdf(temp_path)
                    return content, temp_path
                
                elif file_type == "text":
                    # Read text files
                    with open(temp_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return content, temp_path
                
                elif file_type == "image":
                    # For images, return basic info (in production, use OCR)
                    content = f"Image file: {file.filename} (OCR processing not implemented)"
                    return content, temp_path
                
                elif file_type == "document":
                    # For documents, return basic info (in production, use document processing)
                    content = f"Document file: {file.filename} (Document processing not implemented)"
                    return content, temp_path
                
                else:
                    # For unknown types, return basic info
                    content = f"File: {file.filename} (type: {file_type})"
                    return content, temp_path
                    
            except Exception as e:
                logger.error(f"Error processing file content: {str(e)}")
                return f"Error processing file: {str(e)}", temp_path
                    
        except Exception as e:
            logger.error(f"Error processing file content: {str(e)}")
            return f"Error processing file: {str(e)}", None
    
    async def _save_uploaded_file(self, file: UploadFile) -> str:
        """Save uploaded file to temporary location"""
        # Create temporary file in TMP_BASE_FOLDER/uploads
        suffix = os.path.splitext(file.filename)[1] if file.filename else ""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=self._temp_dir)
        
        try:
            # Write file content
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            
            return temp_file.name
        finally:
            temp_file.close()
    
    def _get_session_key(self, agent_id: int, user_context: Dict = None) -> str:
        """Generate session key for agent and user combination"""
        if user_context:
            user_id = user_context.get('user_id', 'anonymous')
            app_id = user_context.get('app_id', 'default')
            return f"agent_{agent_id}_user_{user_id}_app_{app_id}"
        else:
            return f"agent_{agent_id}_anonymous"

    async def _save_file_to_disk(self, session_key: str, file_id: str, file_ref: FileReference, original_file_path: str = None):
        """Save file reference to disk for persistence"""
        try:
            session_dir = os.path.join(self._persistent_dir, session_key)
            os.makedirs(session_dir, exist_ok=True)
            
            # Save file metadata
            metadata_file = os.path.join(session_dir, f"{file_id}.json")
            with open(metadata_file, 'w') as f:
                import json
                json.dump(file_ref.to_dict(), f, indent=2)
            
            # Save file content (extracted text)
            content_file = os.path.join(session_dir, f"{file_id}.content")
            with open(content_file, 'w', encoding='utf-8') as f:
                f.write(file_ref.content)
            
            # Save original file if provided
            if original_file_path and os.path.exists(original_file_path):
                original_filename = os.path.basename(original_file_path)
                original_extension = os.path.splitext(original_filename)[1]
                original_file = os.path.join(session_dir, f"{file_id}{original_extension}")
                
                import shutil
                shutil.copy2(original_file_path, original_file)
                logger.info(f"Saved original file {original_filename} to {original_file}")
                
            logger.info(f"Saved file {file_id} to disk: {session_dir}")
            
        except Exception as e:
            logger.error(f"Error saving file to disk: {str(e)}")

    def _load_persistent_files(self):
        """Load existing files from disk on startup"""
        try:
            if not os.path.exists(self._persistent_dir):
                return
                
            for session_key in os.listdir(self._persistent_dir):
                session_path = os.path.join(self._persistent_dir, session_key)
                if not os.path.isdir(session_path):
                    continue
                    
                self._files[session_key] = {}
                
                # Load files for this session
                for filename in os.listdir(session_path):
                    if filename.endswith('.json'):
                        file_id = filename[:-5]  # Remove .json extension
                        metadata_file = os.path.join(session_path, filename)
                        content_file = os.path.join(session_path, f"{file_id}.content")
                        
                        if os.path.exists(content_file):
                            try:
                                with open(metadata_file, 'r') as f:
                                    import json
                                    metadata = json.load(f)
                                
                                with open(content_file, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                
                                # Recreate FileReference
                                file_ref = FileReference(
                                    metadata['file_id'],
                                    metadata['filename'],
                                    metadata['file_type'],
                                    content
                                )
                                
                                self._files[session_key][file_id] = file_ref
                                logger.info(f"Loaded persistent file {file_id} for session {session_key}")
                                
                            except Exception as e:
                                logger.error(f"Error loading file {file_id}: {str(e)}")
                                
            logger.info(f"Loaded {sum(len(files) for files in self._files.values())} persistent files from disk")
            
        except Exception as e:
            logger.error(f"Error loading persistent files: {str(e)}")

    async def _remove_file_from_disk(self, session_key: str, file_id: str):
        """Remove file from disk"""
        try:
            session_dir = os.path.join(self._persistent_dir, session_key)
            metadata_file = os.path.join(session_dir, f"{file_id}.json")
            content_file = os.path.join(session_dir, f"{file_id}.content")
            
            # Remove metadata and content files
            if os.path.exists(metadata_file):
                os.remove(metadata_file)
            if os.path.exists(content_file):
                os.remove(content_file)
            
            # Remove original file (look for any file with the file_id as prefix)
            for filename in os.listdir(session_dir):
                if filename.startswith(file_id) and not filename.endswith(('.json', '.content')):
                    original_file = os.path.join(session_dir, filename)
                    if os.path.exists(original_file):
                        os.remove(original_file)
                        logger.info(f"Removed original file {filename}")
                
            logger.info(f"Removed file {file_id} from disk")
            
        except Exception as e:
            logger.error(f"Error removing file from disk: {str(e)}")

    def get_file_stats(self) -> Dict[str, Any]:
        """Get file management statistics"""
        try:
            file_types = {}
            total_size = 0
            total_files = 0
            
            for session_files in self._files.values():
                for file_ref in session_files.values():
                    file_type = file_ref.file_type
                    file_types[file_type] = file_types.get(file_type, 0) + 1
                    total_size += len(file_ref.content)
                    total_files += 1
            
            return {
                "total_files": total_files,
                "total_sessions": len(self._files),
                "file_types": file_types,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting file stats: {str(e)}")
            return {} 