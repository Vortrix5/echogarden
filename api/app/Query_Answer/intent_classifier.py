"""
Intent Classifier - Determines user intent (file search vs response generation).

Classifies whether the user wants:
1. FILE - A specific document/resource
2. RESPONSE - An answer/explanation

Uses pattern matching, keywords, and LLM-based classification.
"""

import logging
from typing import Literal, Dict, Any
from enum import Enum
import re

logger = logging.getLogger(__name__)


class Intent(Enum):
    """User intent types."""
    FILE = "file"          # User wants a file/document
    RESPONSE = "response"  # User wants an answer/explanation
    UNKNOWN = "unknown"    # Cannot determine intent


class IntentClassifier:
    """
    Classifies user queries to determine intent.
    """
    
    # Keywords that indicate file search
    FILE_KEYWORDS = {
        "find file", "get file", "show file", "document", 
        "pdf", "download", "retrieve file", "file path",
        "where is", "locate", "search for file", "look for",
        "send file", "file name", "which file", "what file"
    }
    
    # Keywords that indicate response generation
    RESPONSE_KEYWORDS = {
        "what is", "explain", "how", "why", "tell me", "describe",
        "summarize", "what are", "can you", "could you", "would you",
        "analyze", "interpret", "meaning", "definition", "question",
        "answer", "help", "advise", "suggest", "recommend"
    }
    
    def __init__(self):
        """Initialize the intent classifier."""
        logger.info("Initialized IntentClassifier")
    
    def classify(self, query: str) -> Dict[str, Any]:
        """
        Classify the user's intent from their query.
        
        Args:
            query: User's query string
            
        Returns:
            Dictionary containing:
                - intent: Intent enum (FILE, RESPONSE, UNKNOWN)
                - confidence: Confidence score (0.0 - 1.0)
                - reason: Explanation of the classification
        """
        query_lower = query.lower().strip()
        
        if not query_lower:
            return {
                "intent": Intent.UNKNOWN,
                "confidence": 0.0,
                "reason": "Empty query"
            }
        
        # Pattern-based classification
        file_score = self._calculate_file_score(query_lower)
        response_score = self._calculate_response_score(query_lower)
        
        # Determine intent based on scores
        if file_score > response_score and file_score > 0.3:
            intent = Intent.FILE
            confidence = min(file_score, 1.0)
            reason = "File-related keywords detected"
        elif response_score > file_score and response_score > 0.3:
            intent = Intent.RESPONSE
            confidence = min(response_score, 1.0)
            reason = "Question/explanation keywords detected"
        else:
            intent = Intent.UNKNOWN
            confidence = 0.0
            reason = "Unable to determine intent"
        
        logger.info(f"Classified query as {intent.value} (confidence: {confidence:.2f})")
        
        return {
            "intent": intent,
            "confidence": confidence,
            "reason": reason,
            "query": query_lower
        }
    
    def _calculate_file_score(self, query: str) -> float:
        """Calculate file-related intent score."""
        score = 0.0
        
        # Check for file keywords
        matching_keywords = sum(
            1 for keyword in self.FILE_KEYWORDS 
            if keyword in query
        )
        score += matching_keywords * 0.2
        
        # Check for file extensions
        extensions = [".pdf", ".txt", ".docx", ".xlsx", ".py", ".json", ".csv"]
        file_extensions = sum(1 for ext in extensions if ext in query)
        score += file_extensions * 0.3
        
        # Check for file-related patterns
        if re.search(r'(file|document)\s+(named|called|path)', query):
            score += 0.3
        if re.search(r'(find|search|locate).*file', query):
            score += 0.4
        
        return score
    
    def _calculate_response_score(self, query: str) -> float:
        """Calculate response/question intent score."""
        score = 0.0
        
        # Check for question words
        question_words = ["what", "how", "why", "who", "when", "where"]
        if any(query.startswith(q) for q in question_words):
            score += 0.4
        
        # Check for question mark
        if query.endswith("?"):
            score += 0.3
        
        # Check for response keywords
        matching_keywords = sum(
            1 for keyword in self.RESPONSE_KEYWORDS 
            if keyword in query
        )
        score += matching_keywords * 0.15
        
        # Check for imperative verbs that might indicate questions
        if re.search(r'(explain|tell|describe|summarize|analyze)\s+', query):
            score += 0.3
        
        return score
    
    def get_intent_type(self, query: str) -> Literal["file", "response", "unknown"]:
        """
        Get just the intent type as a string (convenience method).
        
        Args:
            query: User's query string
            
        Returns:
            Intent type as string: "file", "response", or "unknown"
        """
        result = self.classify(query)
        return result["intent"].value


# Convenience function
def classify_intent(query: str) -> Dict[str, Any]:
    """
    Convenience function to classify a query.
    
    Args:
        query: User's query string
        
    Returns:
        Classification result with intent, confidence, and reason
    """
    classifier = IntentClassifier()
    return classifier.classify(query)
