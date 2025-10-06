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
            "uploaded_at": self.uploaded_at.isoformat()
        }


class FileManagementService:
    """Unified file management - used by both public and internal APIs"""
    
    def __init__(self):
        # In-memory file storage (in production, use cloud storage)
        self._files: Dict[str, FileReference] = {}
        self._temp_dir = os.getenv("TEMP_DIR", "data/temp/uploads/")
        
        # Ensure temp directory exists
        os.makedirs(self._temp_dir, exist_ok=True)
    
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
            content = await self._process_file_content(file, file_type)
            
            # Create file reference
            file_ref = FileReference(file_id, file.filename, file_type, content)
            
            # Store file reference
            self._files[file_id] = file_ref
            
            logger.info(f"Uploaded file {file.filename} for agent {agent_id}")
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
            # In a real implementation, you'd filter by user context
            # For now, return all files (this should be improved)
            return [file_ref.to_dict() for file_ref in self._files.values()]
            
        except Exception as e:
            logger.error(f"Error listing attached files: {str(e)}")
            return []
    
    async def remove_file(
        self, 
        file_id: str, 
        user_context: Dict = None
    ) -> bool:
        """
        Remove attached file
        
        Args:
            file_id: File ID to remove
            user_context: User context
            
        Returns:
            True if removed successfully
        """
        try:
            if file_id in self._files:
                del self._files[file_id]
                logger.info(f"Removed file {file_id}")
                return True
            else:
                logger.warning(f"File {file_id} not found for removal")
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
    
    async def _process_file_content(self, file: UploadFile, file_type: str) -> str:
        """
        Process file content based on file type
        
        Args:
            file: Uploaded file
            file_type: Type of file
            
        Returns:
            Processed content string
        """
        try:
            # Save file temporarily
            temp_path = await self._save_uploaded_file(file)
            
            try:
                if file_type == "pdf":
                    # Use existing PDF tools
                    return extract_text_from_pdf(temp_path)
                
                elif file_type == "text":
                    # Read text files
                    with open(temp_path, 'r', encoding='utf-8') as f:
                        return f.read()
                
                elif file_type == "image":
                    # For images, return basic info (in production, use OCR)
                    return f"Image file: {file.filename} (OCR processing not implemented)"
                
                elif file_type == "document":
                    # For documents, return basic info (in production, use document processing)
                    return f"Document file: {file.filename} (Document processing not implemented)"
                
                else:
                    # For unknown types, return basic info
                    return f"File: {file.filename} (type: {file_type})"
                    
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            logger.error(f"Error processing file content: {str(e)}")
            return f"Error processing file: {str(e)}"
    
    async def _save_uploaded_file(self, file: UploadFile) -> str:
        """Save uploaded file to temporary location"""
        # Create temporary file
        suffix = os.path.splitext(file.filename)[1] if file.filename else ""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        
        try:
            # Write file content
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            
            return temp_file.name
        finally:
            temp_file.close()
    
    def get_file_stats(self) -> Dict[str, Any]:
        """Get file management statistics"""
        try:
            file_types = {}
            total_size = 0
            
            for file_ref in self._files.values():
                file_type = file_ref.file_type
                file_types[file_type] = file_types.get(file_type, 0) + 1
                total_size += len(file_ref.content)
            
            return {
                "total_files": len(self._files),
                "file_types": file_types,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting file stats: {str(e)}")
            return {} 