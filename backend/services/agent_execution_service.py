import os
import asyncio
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from models.agent import Agent
from models.ocr_agent import OCRAgent
from tools.PDFTools import extract_text_from_pdf, convert_pdf_to_images, check_pdf_has_text
from tools.ocrAgentTools import (
    convert_image_to_base64,
    extract_text_from_image,
    format_data_with_text_llm,
    format_data_from_vision,
    get_data_from_extracted_text,
    get_document_data_from_pages
)
from tools.aiServiceTools import get_llm
from tools.outputParserTools import create_model_from_json_schema
from services.agent_service import AgentService
from services.session_management_service import SessionManagementService
from repositories.agent_execution_repository import AgentExecutionRepository
from utils.logger import get_logger

logger = get_logger(__name__)


class AgentExecutionService:
    """Unified service for agent execution - used by both public and internal APIs"""
    
    # Shared thread pool for blocking operations (LLM calls, file I/O, etc.)
    # This prevents blocking the event loop
    _executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="agent_exec")
    
    def __init__(self, db: Session = None):
        self.agent_service = AgentService()
        self.session_service = SessionManagementService()
        self.agent_execution_repo = AgentExecutionRepository()
        self.db = db
    
    async def execute_agent_chat(
        self, 
        agent_id: int, 
        message: str, 
        files: List[UploadFile] = None,
        search_params: Dict = None,
        user_context: Dict = None,
        conversation_id: str = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Execute agent chat - used by both playground and public API
        
        Args:
            agent_id: ID of the agent to execute
            message: User message
            files: Optional file attachments
            search_params: Optional search parameters for silo-based agents
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            Dict containing agent response and metadata
        """
        try:
            # Get agent
            agent = self.agent_service.get_agent(db, agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            # Validate user has access to this agent
            await self._validate_agent_access(agent, user_context)
            
            # Process files if provided
            processed_files = []
            if files:
                processed_files = await self._process_files_for_agent(files, agent)
            
            # Get user session for memory-enabled agents
            session = None
            if agent.has_memory:
                session = await self.session_service.get_user_session(agent_id, user_context, conversation_id)
            
            # Execute agent using LangChain IN A THREAD POOL (blocking LLM calls)
            # This prevents blocking the event loop and allows other requests to be processed
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self._executor,
                self._execute_langchain_agent,
                agent, message, processed_files, search_params, session, db
            )
            
            # Parse response based on agent's output parser
            from tools.agentTools import parse_agent_response
            parsed_response = parse_agent_response(response, agent)
            
            # Update request count
            self._update_request_count(agent, db)
            
            # Add to session history if memory enabled
            if session:
                await self.session_service.add_message_to_session(
                    session.id, message, parsed_response
                )
            
            return {
                "response": parsed_response,
                "agent_id": agent_id,
                "metadata": {
                    "agent_name": agent.name,
                    "agent_type": agent.type,
                    "files_processed": len(processed_files),
                    "has_memory": agent.has_memory
                }
            }
            
        except Exception as e:
            logger.error(f"Error executing agent chat: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")
    
    async def execute_agent_ocr(
        self, 
        agent_id: int, 
        pdf_file: UploadFile,
        user_context: Dict = None,
        for_api: bool = False,  # True for public API, False for playground
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Execute OCR processing - used by both playground and public API
        
        Args:
            agent_id: ID of the OCR agent
            pdf_file: PDF file to process
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            Dict containing OCR processing results
        """
        try:
            # Get OCR agent
            agent = self.agent_service.get_agent(db, agent_id, agent_type='ocr_agent')
            if not agent or not isinstance(agent, OCRAgent):
                raise HTTPException(status_code=404, detail="OCR Agent not found")
            
            # Validate user has access to this agent
            await self._validate_agent_access(agent, user_context)
            
            # Validate PDF file
            if not pdf_file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail="Only PDF files are allowed")
            
            # Save PDF to temporary location
            temp_pdf_path = await self._save_uploaded_file(pdf_file)
            
            try:
                # Process PDF using existing tools
                result = await self._process_pdf_with_ocr(agent, temp_pdf_path, db)
                
                # Update request count
                self._update_request_count(agent, db)
                
                if for_api:
                    # Public API: Return just the structured content (output parser result)
                    return result.get("content", result)
                else:
                    # Playground: Return full result with metadata for UI
                    content = result.get("content", "")
                    if isinstance(content, dict):
                        import json
                        extracted_text = json.dumps(content, indent=2, ensure_ascii=False)
                    else:
                        extracted_text = str(content)
                    
                    return {
                        "result": result,
                        "agent_id": agent_id,
                        "extracted_text": extracted_text,
                        "metadata": {
                            "agent_name": agent.name,
                            "pdf_filename": pdf_file.filename,
                            "pages_processed": len(result.get("pages", [])),
                            "confidence": result.get("confidence", 0.0)
                        }
                    }
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)
                    
        except Exception as e:
            logger.error(f"Error executing OCR agent: {str(e)}")
            raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")
    
    async def reset_agent_conversation(
        self, 
        agent_id: int,
        user_context: Dict = None,
        db: Session = None
    ) -> bool:
        """
        Reset conversation - used by both playground and public API
        
        Args:
            agent_id: ID of the agent
            user_context: User context (api_key, user_id, etc.)
            
        Returns:
            True if reset successful
        """
        try:
            # Get agent
            agent = self.agent_service.get_agent(db, agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            # Validate user has access to this agent
            await self._validate_agent_access(agent, user_context)
            
            # Reset session if memory enabled
            if agent.has_memory:
                await self.session_service.reset_user_session(agent_id, user_context)
            
            return True
            
        except Exception as e:
            logger.error(f"Error resetting agent conversation: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")
    
    async def _validate_agent_access(self, agent: Agent, user_context: Dict):
        """Validate user has access to the agent"""
        # TODO: Implement proper access validation
        # For now, just log the validation
        logger.info(f"Validating access for agent {agent.agent_id} with context {user_context}")
        pass
    
    async def _process_files_for_agent(self, files: List[UploadFile], agent: Agent) -> List[Dict]:
        """Process files for agent consumption using existing PDF tools"""
        processed_files = []
        
        for file in files:
            try:
                # Save file temporarily
                temp_path = await self._save_uploaded_file(file)
                
                # Process based on file type IN THREAD POOL (blocking I/O)
                loop = asyncio.get_event_loop()
                file_data = await loop.run_in_executor(
                    self._executor,
                    self._process_single_file,
                    temp_path, file.filename
                )
                
                if file_data:
                    processed_files.append(file_data)
                
                # Clean up
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {str(e)}")
                continue
        
        return processed_files
    
    def _process_single_file(self, temp_path: str, filename: str) -> Dict:
        """Synchronous file processing - called in thread pool"""
        try:
            if filename.lower().endswith('.pdf'):
                # Use existing PDF tools (blocking I/O)
                text_content = extract_text_from_pdf(temp_path)
                return {
                    "filename": filename,
                    "content": text_content,
                    "type": "pdf"
                }
            else:
                # Handle other file types (blocking I/O)
                with open(temp_path, 'r') as f:
                    content = f.read()
                return {
                    "filename": filename,
                    "content": content,
                    "type": "text"
                }
        except Exception as e:
            logger.error(f"Error in _process_single_file: {str(e)}")
            return None
    
    async def _process_pdf_with_ocr(self, agent: OCRAgent, pdf_path: str, db: Session) -> Dict[str, Any]:
        """Process PDF using OCR workflow respecting output parser/data structure"""
        # Run all OCR processing in thread pool (blocking operations: PDF parsing, LLM calls, etc.)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            self._process_pdf_with_ocr_sync,
            agent, pdf_path, db
        )
        return result
    
    def _process_pdf_with_ocr_sync(self, agent: OCRAgent, pdf_path: str, db: Session) -> Dict[str, Any]:
        """Synchronous OCR processing - called in thread pool"""
        try:
            # Re-load agent with all relationships
            agent = self.agent_execution_repo.get_ocr_agent_with_relationships(db, agent.agent_id)
            
            if not agent:
                raise Exception(f"Agent {agent.agent_id} not found")
            
            # Get output parser if configured - this is CRITICAL for structured output
            pydantic_class = None
            if agent.output_parser_id:
                try:
                    # Get the output parser definition using repository
                    output_parser = self.agent_execution_repo.get_output_parser_by_id(db, agent.output_parser_id)
                    
                    if output_parser and output_parser.fields:
                        logger.info(f"Found output parser: {output_parser.name} with fields: {output_parser.fields}")
                        # Create pydantic model from schema like in original
                        pydantic_class = create_model_from_json_schema(
                            output_parser.fields,
                            output_parser.name
                        )
                        logger.info(f"Output parser model created successfully: {output_parser.name} -> {pydantic_class}")
                    else:
                        logger.warning(f"Output parser {agent.output_parser_id} not found or has no fields")
                    
                except Exception as e:
                    logger.warning(f"Failed to load output parser: {str(e)}")
            
            # Check if PDF has text
            has_text = check_pdf_has_text(pdf_path)
            
            if has_text:
                # Extract text directly
                text_content = extract_text_from_pdf(pdf_path)
                logger.info(f"Extracted text from PDF: {len(text_content)} characters")
                
                # Process with text model and output parser if available
                if agent.text_system_prompt and agent.service_id and pydantic_class:
                    try:
                        text_model = get_llm(agent, is_vision=False)
                        if text_model:
                            logger.info(f"Processing text with LLM and output parser")
                            # Use the output parser to structure the data
                            structured_data = get_data_from_extracted_text(
                                text_content,
                                text_model,
                                pydantic_class,
                                agent.text_system_prompt,
                                text_content,
                                os.path.basename(pdf_path)
                            )
                            
                            logger.info(f"Structured data result: {structured_data}")
                            
                            return {
                                "method": "text_extraction_with_llm",
                                "content": structured_data,
                                "extracted_text": text_content,
                                "confidence": 0.9
                            }
                    except Exception as e:
                        logger.error(f"Error processing with LLM and output parser: {str(e)}", exc_info=True)
                
                # If no text model or output parser, return raw text
                logger.info("No text model or output parser configured, returning raw text")
                return {
                    "method": "text_extraction",
                    "content": text_content,
                    "extracted_text": text_content,
                    "confidence": 0.9
                }
            else:
                # Convert to images and process with vision
                images_dir = os.getenv("IMAGES_PATH", "data/temp/images/")
                os.makedirs(images_dir, exist_ok=True)
                
                image_paths = convert_pdf_to_images(pdf_path, images_dir)
                logger.info(f"Converted PDF to {len(image_paths)} images")
                
                # Process images with vision model
                vision_results = []
                for i, image_path in enumerate(image_paths):
                    try:
                        base64_image = convert_image_to_base64(image_path)
                        
                        # Get vision model
                        vision_model = get_llm(agent, is_vision=True)
                        if not vision_model:
                            raise Exception("Vision model not found")
                        
                        # Extract text from image
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
                        
                        # Clean up image file
                        try:
                            os.remove(image_path)
                        except:
                            pass
                            
                    except Exception as e:
                        logger.warning(f"Error processing image {i+1}: {str(e)}")
                        continue
                
                # Process with text model if available and we have vision results
                if agent.text_system_prompt and agent.service_id and vision_results:
                    try:
                        text_model = get_llm(agent, is_vision=False)
                        if text_model:
                            # Format data with text model using output parser
                            formatted_result = format_data_with_text_llm(
                                vision_results, 
                                text_model, 
                                pydantic_class, 
                                agent.text_system_prompt, 
                                "", 
                                os.path.basename(pdf_path)
                            )
                            
                            # Get final structured document data
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
                
                # Return vision results directly
                return {
                    "method": "vision_only",
                    "content": vision_results,
                    "extracted_text": vision_results,
                    "confidence": 0.7
                }
                
        except Exception as e:
            logger.error(f"Error processing PDF with OCR: {str(e)}")
            raise
    
    def _execute_langchain_agent(
        self, 
        agent: Agent, 
        message: str, 
        processed_files: List[Dict], 
        search_params: Dict = None,
        session = None,
        db: Session = None
    ) -> str:
        """Execute agent using LangChain with existing tools"""
        try:
            from tools.aiServiceTools import invoke, invoke_with_rag, invoke_conversational_retrieval_chain
            
            # Re-query the agent with relationships loaded using repository
            fresh_agent = self.agent_execution_repo.get_agent_with_relationships(db, agent.agent_id)
            
            if not fresh_agent:
                raise Exception("Agent not found in database")
            
            # Check if agent has memory (conversational)
            if fresh_agent.has_memory and session:
                # Use conversational retrieval chain
                return invoke_conversational_retrieval_chain(fresh_agent, message, session)
            
            # Check if agent has RAG capabilities (silo)
            elif fresh_agent.silo:
                # Use RAG-enabled invocation with search parameters
                return invoke_with_rag(fresh_agent, message, search_params)
            
            # Default invocation
            else:
                return invoke(fresh_agent, message)
                
        except Exception as e:
            logger.error(f"Error executing LangChain agent: {str(e)}")
            raise Exception(f"Agent execution failed: {str(e)}")
    
    async def _save_uploaded_file(self, file: UploadFile) -> str:
        """Save uploaded file to temporary location"""
        import tempfile
        
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
    
    def _update_request_count(self, agent: Agent, db: Session):
        """Update agent request count"""
        self.agent_execution_repo.update_agent_request_count(db, agent.agent_id) 