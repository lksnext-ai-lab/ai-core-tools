import os
import base64
import uuid
import pathlib
from typing import Optional
from utils.logger import get_logger
from utils.error_handlers import ValidationError
from tools.PDFTools import extract_text_from_pdf

logger = get_logger(__name__)


class FileUtils:
    @staticmethod
    def process_base64_attachment(attachment: str, filename: str, mime_type: str) -> Optional[str]:
        """
        Process base64 encoded attachment and save to temporary file.
        Returns the path to the temporary file.
        """
        try:
            # Remove data URL prefix if present
            if attachment.startswith('data:'):
                # Extract base64 data after the comma
                attachment = attachment.split(',', 1)[1]
            
            # Decode base64 data
            file_data = base64.b64decode(attachment)
            
            # Create temporary file
            temp_dir = os.getenv('DOWNLOADS_PATH', 'data/temp/downloads/')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate secure filename
            secure_filename = f"{uuid.uuid4()}_{filename}"
            temp_path = os.path.join(temp_dir, secure_filename)
            
            # Write file data
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            logger.info(f"Saved base64 attachment to: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error processing base64 attachment: {str(e)}")
            raise ValidationError(f"Invalid attachment format: {str(e)}")

    @staticmethod
    def process_file_upload(file) -> Optional[str]:
        """
        Process uploaded file and save to temporary location.
        Returns the path to the temporary file.
        """
        try:
            if not file or not file.filename:
                return None
            
            # Validate file extension
            original_filename = file.filename
            file_ext = pathlib.Path(original_filename).suffix.lower()
            allowed_extensions = ['.pdf', '.txt', '.doc', '.docx', '.png', '.jpg', '.jpeg']
            
            if file_ext not in allowed_extensions:
                raise ValidationError(f'File type {file_ext} not allowed. Allowed types: {", ".join(allowed_extensions)}')
            
            # Create temporary file
            temp_dir = os.getenv('DOWNLOADS_PATH', 'data/temp/downloads/')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate secure filename
            secure_filename = f"{uuid.uuid4()}{file_ext}"
            temp_path = os.path.join(temp_dir, secure_filename)
            
            # Save file
            file.save(temp_path)
            
            logger.info(f"Saved uploaded file to: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error processing file upload: {str(e)}")
            raise ValidationError(f"Error processing file: {str(e)}")

    @staticmethod
    def process_attachment_for_agent(attachment_path: str, agent) -> str:
        """
        Process attachment file and return appropriate content for the agent.
        Handles different file types (PDF, images, text files) based on agent capabilities.
        """
        try:
            if not attachment_path or not os.path.exists(attachment_path):
                return ""
            
            file_ext = pathlib.Path(attachment_path).suffix.lower()
            
            # Handle PDF files
            if file_ext == '.pdf':
                return FileUtils._process_pdf_attachment(attachment_path)
            
            # Handle image files
            elif file_ext in ['.png', '.jpg', '.jpeg']:
                return FileUtils._process_image_attachment(attachment_path, agent)
            
            # Handle text files
            elif file_ext in ['.txt', '.md']:
                return FileUtils._process_text_attachment(attachment_path)
            
            # Handle document files (basic text extraction)
            elif file_ext in ['.doc', '.docx']:
                return FileUtils._process_document_attachment(attachment_path)
            
            else:
                logger.warning(f"Unsupported file type: {file_ext}")
                return f"\n\n[Unsupported file type: {file_ext}]"
                
        except Exception as e:
            logger.error(f"Error processing attachment {attachment_path}: {str(e)}")
            return f"\n\n[Error processing attachment: {str(e)}]"

    @staticmethod
    def _process_pdf_attachment(pdf_path: str) -> str:
        """Process PDF attachment by extracting text."""
        try:
            # Extract text from PDF
            text = extract_text_from_pdf(pdf_path)
            
            if text and len(text.strip()) > 0:
                # Limit text length to avoid overwhelming the agent
                max_length = 2000
                if len(text) > max_length:
                    text = text[:max_length] + "..."
                return f"\n\n[PDF Content: {text}]"
            else:
                return f"\n\n[PDF file attached: {os.path.basename(pdf_path)} - No text content found]"
            
        except Exception as e:
            logger.error(f"Error processing PDF {pdf_path}: {str(e)}")
            return f"\n\n[PDF file attached: {os.path.basename(pdf_path)}]"

    @staticmethod
    def _process_image_attachment(image_path: str, agent) -> str:
        """Process image attachment for vision models."""
        try:
            # Check if agent has vision capabilities
            if hasattr(agent, 'vision_service_rel') and agent.vision_service_rel:
                # Convert image to base64 for vision models
                with open(image_path, 'rb') as img_file:
                    img_data = base64.b64encode(img_file.read()).decode('utf-8')
                
                # For vision models, we'll include the base64 data
                # The agent processing will need to handle this appropriately
                return f"\n\n[Image data: data:image/jpeg;base64,{img_data[:100]}...]"
            
            # Fallback: just mention the image
            return f"\n\n[Image file attached: {os.path.basename(image_path)}]"
            
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {str(e)}")
            return f"\n\n[Image file attached: {os.path.basename(image_path)}]"

    @staticmethod
    def _process_text_attachment(text_path: str) -> str:
        """Process text file attachment."""
        try:
            with open(text_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Limit content length to avoid overwhelming the agent
            max_length = 2000
            if len(content) > max_length:
                content = content[:max_length] + "..."
            
            return f"\n\n[Text file content: {content}]"
            
        except Exception as e:
            logger.error(f"Error processing text file {text_path}: {str(e)}")
            return f"\n\n[Text file attached: {os.path.basename(text_path)}]"

    @staticmethod
    def _process_document_attachment(doc_path: str) -> str:
        """Process document file attachment (basic implementation)."""
        try:
            # For now, just mention the document
            # In a full implementation, you might use libraries like python-docx
            return f"\n\n[Document file attached: {os.path.basename(doc_path)}]"
            
        except Exception as e:
            logger.error(f"Error processing document {doc_path}: {str(e)}")
            return f"\n\n[Document file attached: {os.path.basename(doc_path)}]" 