import os
from typing import Dict, Any
from sqlalchemy.orm import Session

from models.ocr_agent import OCRAgent
from tools.PDFTools import extract_text_from_pdf, convert_pdf_to_images, check_pdf_has_text
from tools.ocrAgentTools import (
    convert_image_to_base64,
    extract_text_from_image,
    format_data_with_text_llm,
    get_data_from_extracted_text,
    get_document_data_from_pages
)
from tools.aiServiceTools import get_llm
from tools.outputParserTools import create_model_from_json_schema
from utils.logger import get_logger
from utils.config import get_app_config

logger = get_logger(__name__)

class OCRService:
    """Service for handling OCR agent processing logic"""

    def process_pdf(self, agent: OCRAgent, pdf_path: str, db: Session) -> Dict[str, Any]:
        """
        Process PDF using OCR workflow respecting output parser/data structure.
        This is a synchronous method intended to be run in a thread pool.
        """
        try:
            # Ensure we have the agent with relationships (assuming the caller provided a fresh agent or we reload)
            # For simplicity in this service, we assume a fresh agent is passed or we use the provided one.
            # If we need to ensure relationships, we might need to reload from DB.

            # Get output parser if configured
            pydantic_class = None
            if agent.output_parser_id:
                try:
                    # Using a direct query or repository here would be better, 
                    # but let's see how it was done in AgentExecutionService.
                    # We'll need to pass the repository or use SessionLocal.
                    from repositories.agent_execution_repository import AgentExecutionRepository
                    repo = AgentExecutionRepository()
                    output_parser = repo.get_output_parser_by_id(db, agent.output_parser_id)

                    if output_parser and output_parser.fields:
                        pydantic_class = create_model_from_json_schema(
                            output_parser.fields,
                            output_parser.name
                        )
                except Exception as e:
                    logger.warning(f"Failed to load output parser: {str(e)}")

            # Check if PDF has text
            has_text = check_pdf_has_text(pdf_path)

            if has_text:
                text_content = extract_text_from_pdf(pdf_path)

                if agent.text_system_prompt and agent.service_id and pydantic_class:
                    try:
                        text_model = get_llm(agent, is_vision=False)
                        if text_model:
                            structured_data = get_data_from_extracted_text(
                                text_content,
                                text_model,
                                pydantic_class,
                                agent.text_system_prompt,
                                text_content,
                                os.path.basename(pdf_path)
                            )
                            return {
                                "method": "text_extraction_with_llm",
                                "content": structured_data,
                                "extracted_text": text_content,
                                "confidence": 0.9
                            }
                    except Exception as e:
                        logger.error(f"Error processing with LLM and output parser: {str(e)}", exc_info=True)

                return {
                    "method": "text_extraction",
                    "content": text_content,
                    "extracted_text": text_content,
                    "confidence": 0.9
                }
            else:
                app_config = get_app_config()
                images_dir = app_config['IMAGES_PATH']
                os.makedirs(images_dir, exist_ok=True)

                image_paths = convert_pdf_to_images(pdf_path, images_dir)

                vision_results = []
                for i, image_path in enumerate(image_paths):
                    try:
                        base64_image = convert_image_to_base64(image_path)
                        vision_model = get_llm(agent, is_vision=True)
                        if not vision_model:
                            raise ValueError("Vision model not found")

                        vision_result = extract_text_from_image(
                            base64_image, 
                            agent.vision_system_prompt, 
                            vision_model, 
                            f"Page {i+1}"
                        )
                        vision_results.append({
                            "page": i + 1,
                            "extracted_text": vision_result
                        })

                        try:
                            os.remove(image_path)
                        except OSError:
                            pass
                    except Exception as e:
                        logger.warning(f"Error processing image {i+1}: {str(e)}")
                        continue

                if agent.text_system_prompt and agent.service_id and vision_results:
                    try:
                        text_model = get_llm(agent, is_vision=False)
                        if text_model:
                            formatted_result = format_data_with_text_llm(
                                vision_results, 
                                text_model, 
                                pydantic_class, 
                                agent.text_system_prompt, 
                                "", 
                                os.path.basename(pdf_path)
                            )
                            final_result = get_document_data_from_pages(
                                agent.text_system_prompt,
                                formatted_result,
                                pydantic_class,
                                text_model,
                                "",
                                os.path.basename(pdf_path)
                            )
                            return {
                                "method": "vision_and_text",
                                "content": final_result,
                                "extracted_text": vision_results,
                                "confidence": 0.8
                            }
                    except Exception as e:
                        logger.warning(f"Error processing with text model: {str(e)}")

                return {
                    "method": "vision_only",
                    "content": vision_results,
                    "extracted_text": vision_results,
                    "confidence": 0.7
                }
        except Exception as e:
            logger.error(f"Error in OCRService.process_pdf: {str(e)}")
            raise