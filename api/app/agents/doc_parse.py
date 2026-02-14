"""DocParseAgent — stub that echoes text input as parsed content."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from tika import parser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DocumentParser:
    """
    Parses various document formats (PDF, DOCX, images, etc.) using Apache Tika.
    """
    
    # Supported file extensions
    SUPPORTED_FORMATS = {
        ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
        ".txt", ".rtf", ".odt", ".csv", ".jpg", ".jpeg", ".png", ".gif"
    }
    
    def __init__(self):
        """Initialize the document parser."""
        logger.info("Initialized DocumentParser")
    
    def _validate_file(self, file_path: str) -> Path:
        """
        Validate that the file exists and is supported.
        
        Args:
            file_path: Path to the document
            
        Returns:
            Path object if valid
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is not supported
        """
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            logger.error(f"Document file not found: {file_path}")
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        if not file_path_obj.is_file():
            logger.error(f"Path is not a file: {file_path}")
            raise ValueError(f"Path is not a file: {file_path}")
        
        file_extension = file_path_obj.suffix.lower()
        if file_extension not in self.SUPPORTED_FORMATS:
            logger.warning(f"Unsupported file format: {file_extension}. Will attempt to parse anyway.")
        
        return file_path_obj
    
    def parse(self, file_path: str) -> Dict[str, Any]:
        """
        Parse a document and extract text and metadata.
        
        Args:
            file_path: Path to the document
            
        Returns:
            Dictionary containing:
                - status: Processing status
                - content: Extracted text from the document
                - metadata: Document metadata (author, title, creation date, etc.)
                - origin: Processing source identifier
                
        Raises:
            FileNotFoundError: If the document doesn't exist
            Exception: If parsing fails
        """
        try:
            # Validate file
            file_path_obj = self._validate_file(file_path)
            logger.info(f"Starting parsing for: {file_path}")
            
            # Parse document
            parsed_result = parser.from_file(str(file_path_obj))
            
            # Extract content and metadata
            content = parsed_result.get("content") or ""
            metadata = parsed_result.get("metadata") or {}
            
            # Clean up content
            content = content.strip() if content else ""
            
            result = {
                "status": "success",
                "content": content,
                "metadata": metadata,
                "file_path": str(file_path_obj),
                "file_name": file_path_obj.name,
                "origin": "document_parser"
            }
            
            logger.info(f"Successfully parsed document. Content length: {len(content)} chars, Metadata keys: {len(metadata)}")
            return result
            
        except FileNotFoundError as e:
            logger.error(f"File error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Document parsing failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "origin": "document_parser"
            }
    
    def parse_batch(self, file_paths: list) -> list:
        """
        Parse multiple documents in batch.
        
        Args:
            file_paths: List of paths to documents
            
        Returns:
            List of results from parse() for each document
        """
        results = []
        for file_path in file_paths:
            try:
                result = self.parse(file_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch parsing error for {file_path}: {str(e)}")
                results.append({
                    "status": "error",
                    "error": str(e),
                    "file_path": file_path,
                    "origin": "document_parser"
                })
        return results


# Module-level function for backward compatibility
def parse_document(file_path: str) -> Dict[str, Any]:
    """
    Convenience function to parse a document.
    
    Args:
        file_path: Path to the document
        
    Returns:
        Dictionary containing parsed content and metadata
    """
    parser_instance = DocumentParser()
    return parser_instance.parse(file_path)


if __name__ == "__main__":
    try:
        parser_instance = DocumentParser()
        result = parser_instance.parse(
            r"C:\Users\ilyes\Documents\github\ai_minds\Data Ingestion\Document Parsing\example.pdf"
        )
        
        if result["status"] == "success":
            print("TEXT:")
            print(result["content"][:1000])
            
            print("\nMETADATA:")
            print(result["metadata"])
        else:
            print(f"Parsing failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")



registry.register(
    name="doc_parse",
    version="0.1.0",
    description="Parse a document and extract structured content (stub).",
    input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    output_schema={"type": "object", "properties": {"content_text": {"type": "string"}, "mime": {"type": "string"}}},
    agent_factory=DocParseAgent,
)
