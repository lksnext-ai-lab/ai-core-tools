import os
import uuid
import pathlib
from flask import request, jsonify
from extensions import db
from agents.ocrAgent import OCRAgent, process_pdf
from utils.logger import get_logger
from utils.error_handlers import ValidationError, NotFoundError, safe_execute
from pydantic import BaseModel

logger = get_logger(__name__)


class OCRRequest(BaseModel):
    agent_id: int

    @classmethod
    def __get_validators__(cls):
        yield from super().__get_validators__()
        yield cls.validate_agent_id

    @staticmethod
    def validate_agent_id(value):
        if value <= 0:
            raise ValueError("agent_id must be a positive integer")
        return value


class OCRService:
    @staticmethod
    def process_ocr(agent_id: int, pdf_file):
        """Process OCR for a PDF file."""
        try:
            # Validate agent_id from form data
            raw_agent_id = request.form.get('agent_id')
            if not raw_agent_id:
                raise ValidationError('Missing agent_id parameter')
            
            try:
                validated_data = OCRRequest(agent_id=int(raw_agent_id))
                agent_id = validated_data.agent_id
            except (ValueError, TypeError):
                raise ValidationError('Invalid agent_id format')
            
            # Get OCR agent
            agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
            if agent is None:
                raise NotFoundError(f"OCR Agent with ID {agent_id} not found", "ocr_agent")
            
            # Update request count if not already counted by the usage limit decorator
            if not hasattr(request, 'api_usage_already_counted'):
                agent.request_count = (agent.request_count or 0) + 1
                result, error = safe_execute(db.session.commit, log_errors=True)
                if error:
                    logger.warning(f"Failed to update request count: {error}")
            
            # Validate PDF file upload
            if not pdf_file or not pdf_file.filename:
                raise ValidationError('Missing or empty PDF file')
            
            # Validate file extension
            original_filename = pdf_file.filename
            file_ext = pathlib.Path(original_filename).suffix.lower()
            if file_ext != '.pdf':
                raise ValidationError('Only PDF files are allowed')
            
            # Generate secure filename
            secure_filename = f"{uuid.uuid4()}{file_ext}"
            
            # Get paths from environment variables with defaults
            downloads_dir = os.getenv('DOWNLOADS_PATH', 'data/temp/downloads/')
            images_dir = os.getenv('IMAGES_PATH', 'data/temp/images/')
            
            # Ensure directories exist
            os.makedirs(downloads_dir, exist_ok=True)
            os.makedirs(images_dir, exist_ok=True)
            
            # Setup file paths
            temp_path = os.path.join(downloads_dir, secure_filename)
            images_path = os.path.join(images_dir, secure_filename[:-4])  # remove .pdf
            
            logger.info(f"Processing OCR for file: {secure_filename} with agent {agent_id}")
            
            # Clean up old files if they exist
            if os.path.exists(temp_path):
                safe_execute(os.remove, temp_path, log_errors=False)
            
            # Save PDF file
            pdf_file.save(temp_path)
            
            try:
                logger.info("Starting OCR processing with agent")
                result = process_pdf(int(agent_id), temp_path, images_path)
                logger.info("OCR process completed successfully")
                return jsonify(result)
            except Exception as e:
                logger.error(f"Error during OCR processing: {str(e)}", exc_info=True)
                # Clean up files on error
                safe_execute(os.remove, temp_path, log_errors=False)
                raise
                
        except Exception as e:
            logger.error(f"Error in OCR processing: {str(e)}", exc_info=True)
            raise 