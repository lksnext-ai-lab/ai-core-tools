import os
import logging
from typing import List
from pdf2image import convert_from_path
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF file using pypdf.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        str: Extracted text from the PDF
        
    Raises:
        Exception: If there's an error reading the PDF
    """
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        raise


def convert_pdf_to_images(pdf_path: str, output_folder: str) -> List[str]:
    """
    Convert a PDF to images and save them in the specified folder.
    
    Args:
        pdf_path (str): Path to the PDF file
        output_folder (str): Folder where images will be saved
        
    Returns:
        List[str]: List of paths to the generated images
        
    Raises:
        Exception: If there's an error converting the PDF
    """
    try:
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            logger.info("Output folder created")
        
        logger.info("Converting PDF to images")
        images = convert_from_path(
            pdf_path,
            dpi=200,
            output_folder=output_folder,
            fmt='jpeg',
            paths_only=True  
        )
        
        if not images:
            logger.error("No images were generated from the PDF")
            return []
        
        logger.info(f"Generated {len(images)} images")
        return images
        
    except Exception as e:
        logger.error(f"Error converting PDF to images: {str(e)}")
        raise


def check_pdf_has_text(pdf_path: str, min_text_length: int = 50) -> bool:
    """
    Check if a PDF contains extractable text.
    
    Args:
        pdf_path (str): Path to the PDF file
        min_text_length (int): Minimum text length to consider the PDF as having text
        
    Returns:
        bool: True if the PDF contains extractable text, False otherwise
    """
    try:
        text = extract_text_from_pdf(pdf_path)
        if not text or len(text.strip()) < min_text_length:
            return False
            
        # Calculate ratio of printable characters
        printable_chars = sum(1 for c in text if c.isprintable() and not c.isspace())
        ratio = printable_chars / len(text)
        
        return ratio > 0.3
    except Exception as e:
        logger.error(f"Error checking PDF text: {str(e)}")
        return False 