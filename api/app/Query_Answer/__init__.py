"""Query & Answer Module - Production Ready"""

from .intent_classifier import IntentClassifier, Intent, classify_intent
from .retriever import Retriever, RetrievalResult, retrieve_documents
from .reranker import Reranker, RerankedResult, rerank_results
from .rag_generator import RAGGenerator, RAGOutput, generate_rag_output
from .evidence_verifier import EvidenceVerifier, VerificationStatus, VerificationResult, verify_output
from .core_agent import CoreAgent, QueryResult

__version__ = "1.0.0"
__all__ = [
    "IntentClassifier",
    "Intent",
    "classify_intent",
    "Retriever",
    "RetrievalResult",
    "retrieve_documents",
    "Reranker",
    "RerankedResult",
    "rerank_results",
    "RAGGenerator",
    "RAGOutput",
    "generate_rag_output",
    "EvidenceVerifier",
    "VerificationStatus",
    "VerificationResult",
    "verify_output",
    "CoreAgent",
    "QueryResult",
]
