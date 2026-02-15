"""Configuration for Query & Answer module."""

# Intent Classification
INTENT_CLASSIFIER_CONFIG = {
    "confidence_threshold": 0.5,
    "unknown_confidence": 0.0,
}

# Retrieval
RETRIEVER_CONFIG = {
    "top_k_default": 10,
    "fts5_weight": 0.2,
    "vector_weight": 0.4,
    "graph_weight": 0.2,
    "recency_weight": 0.2,
    "recency_decay": 0.1,  # 10% per day
}

# Reranking
RERANKER_CONFIG = {
    "min_quality_score": 0.3,
    "min_relevance_score": 0.5,
    "diversity_penalty": 0.05,
    "cross_encoder_weight": 0.6,
    "retrieval_score_weight": 0.3,
    "quality_score_weight": 0.1,
}

# RAG Generation
RAG_CONFIG = {
    "max_context_tokens": 2048,
    "max_citations": 5,
    "response_model": "default",  # Specify LLM model
    "file_list_max_items": 10,
}

# Evidence Verification
VERIFICATION_CONFIG = {
    "min_pass_score": 0.7,
    "min_retry_score": 0.5,
    "claim_support_weight": 0.4,
    "factuality_weight": 0.3,
    "consistency_weight": 0.15,
    "completeness_weight": 0.1,
    "safety_weight": 0.05,
}

# Core Agent
CORE_AGENT_CONFIG = {
    "max_retries": 3,
    "retry_with_increased_results": True,
    "retry_increase_per_attempt": 5,  # Increase top_k by this amount
    "batch_processing_enabled": True,
    "logging_level": "INFO",
}

# Pipeline defaults
DEFAULT_TOP_K = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_INTENT_THRESHOLD = 0.5

# Response templates
RESPONSE_TEMPLATES = {
    "no_results": "I couldn't find any relevant information for your query. Could you please rephrase or provide more context?",
    "multiple_files": "Found {count} matching files. Please select one for more details.",
    "low_confidence": "I found some information, but with lower confidence. Please verify the following results.",
    "error": "An error occurred while processing your query. Please try again.",
}

# Keywords for intent classification
INTENT_KEYWORDS = {
    "file": [
        "find file", "get file", "show file", "document",
        "pdf", "download", "retrieve", "path",
        "where", "locate", "search for", "look for"
    ],
    "response": [
        "what is", "explain", "how", "why", "tell me",
        "describe", "summarize", "analyze", "answer"
    ]
}

# Supported document types for file search
SUPPORTED_FILE_TYPES = {
    ".pdf", ".txt", ".docx", ".xlsx", ".py",
    ".json", ".csv", ".md", ".pptx"
}
