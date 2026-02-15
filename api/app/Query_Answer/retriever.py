"""
Retriever - Hybrid retrieval system combining multiple sources and ranking strategies.

Components:
1. FTS5 (Full-Text Search) - Fast text matching
2. Vector DB (Qdrant) - Semantic similarity
3. Recency Weighting - Favor recent documents
4. Graph DB - Relationship-based retrieval

All results are merged, deduplicated, and ranked by relevance.
"""

import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Represents a single retrieved document."""
    content_id: str
    content: str
    source: str  # "fts5", "vector", "graph"
    relevance_score: float
    recency_score: float
    metadata: Dict[str, Any]
    timestamp: str
    combined_score: float = 0.0


class Retriever:
    """
    Hybrid retriever combining FTS5, Vector DB, Recency, and Graph DB.
    """
    
    # Weights for different retrieval sources
    SOURCE_WEIGHTS = {
        "fts5": 0.2,      # Exact matches
        "vector": 0.4,    # Semantic similarity (highest priority)
        "graph": 0.2,     # Relationship-based
        "recency": 0.2    # Time-based relevance
    }
    
    # Recency decay factor (how much older docs lose relevance)
    RECENCY_DECAY = 0.1  # 10% relevance loss per day
    
    def __init__(self, 
                 fts5_index=None,
                 vector_db=None,
                 graph_db=None,
                 recency_weight: float = 0.2):
        """
        Initialize the hybrid retriever.
        
        Args:
            fts5_index: Full-text search index (SQLite FTS5)
            vector_db: Vector database (Qdrant)
            graph_db: Graph database (Neo4j, etc.)
            recency_weight: Weight for recency scoring
        """
        self.fts5_index = fts5_index
        self.vector_db = vector_db
        self.graph_db = graph_db
        self.recency_weight = recency_weight
        logger.info("Initialized Retriever with hybrid sources")
    
    def retrieve(self, 
                query: str, 
                top_k: int = 10,
                filters: Optional[Dict[str, Any]] = None) -> List[RetrievalResult]:
        """
        Retrieve documents from all sources and combine results.
        
        Args:
            query: Search query
            top_k: Number of top results to return
            filters: Optional filters (content type, date range, etc.)
            
        Returns:
            List of ranked retrieval results
        """
        logger.info(f"Retrieving for query: {query} (top_k={top_k})")
        
        all_results = {}  # Use dict for deduplication by content_id
        
        # 1. FTS5 Retrieval (Full-Text Search)
        if self.fts5_index:
            fts5_results = self._retrieve_fts5(query, filters)
            for result in fts5_results:
                if result.content_id not in all_results:
                    all_results[result.content_id] = result
                else:
                    # Merge scores
                    existing = all_results[result.content_id]
                    existing.relevance_score = max(existing.relevance_score, result.relevance_score)
                    existing.source += f", fts5"
        
        # 2. Vector DB Retrieval (Semantic Search)
        if self.vector_db:
            vector_results = self._retrieve_vector(query, filters)
            for result in vector_results:
                if result.content_id not in all_results:
                    all_results[result.content_id] = result
                else:
                    existing = all_results[result.content_id]
                    existing.relevance_score = max(existing.relevance_score, result.relevance_score)
                    existing.source += f", vector"
        
        # 3. Graph DB Retrieval (Relationships)
        if self.graph_db:
            graph_results = self._retrieve_graph(query, filters)
            for result in graph_results:
                if result.content_id not in all_results:
                    all_results[result.content_id] = result
                else:
                    existing = all_results[result.content_id]
                    existing.relevance_score = max(existing.relevance_score, result.relevance_score)
                    existing.source += f", graph"
        
        # 4. Apply recency weighting to all results
        for result in all_results.values():
            result.recency_score = self._calculate_recency_score(result.timestamp)
        
        # 5. Calculate combined scores and rank
        ranked_results = self._rank_results(all_results)
        
        # 6. Return top-k results
        final_results = ranked_results[:top_k]
        logger.info(f"Retrieved {len(final_results)} results from {len(all_results)} unique documents")
        
        return final_results
    
    def _retrieve_fts5(self, 
                      query: str, 
                      filters: Optional[Dict[str, Any]] = None) -> List[RetrievalResult]:
        """
        Retrieve using Full-Text Search (FTS5).
        
        Handles:
        - Exact phrase matching
        - Partial word matching
        - Boolean operators
        """
        results = []
        
        if not self.fts5_index:
            return results
        
        try:
            # Mock FTS5 implementation
            # In production, this would query SQLite FTS5 index
            mock_data = [
                {
                    "id": "doc_1",
                    "content": "Machine learning is a subset of AI",
                    "score": 0.95,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"type": "article", "author": "Alice"}
                },
                {
                    "id": "doc_2", 
                    "content": "Deep learning uses neural networks",
                    "score": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"type": "article", "author": "Bob"}
                }
            ]
            
            for item in mock_data:
                result = RetrievalResult(
                    content_id=item["id"],
                    content=item["content"],
                    source="fts5",
                    relevance_score=item["score"],
                    recency_score=0.0,
                    metadata=item.get("metadata", {}),
                    timestamp=item["timestamp"]
                )
                results.append(result)
                
        except Exception as e:
            logger.error(f"FTS5 retrieval error: {str(e)}")
        
        return results
    
    def _retrieve_vector(self, 
                        query: str, 
                        filters: Optional[Dict[str, Any]] = None) -> List[RetrievalResult]:
        """
        Retrieve using Vector DB (Qdrant).
        
        Performs semantic similarity search using embeddings.
        """
        results = []
        
        if not self.vector_db:
            return results
        
        try:
            # Mock vector DB implementation
            # In production, this would query Qdrant with embeddings
            mock_data = [
                {
                    "id": "doc_3",
                    "content": "Neural networks process information",
                    "score": 0.92,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"type": "documentation", "version": "2.0"}
                },
                {
                    "id": "doc_4",
                    "content": "AI algorithms optimize decision making",
                    "score": 0.88,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"type": "research", "journal": "Nature"}
                }
            ]
            
            for item in mock_data:
                result = RetrievalResult(
                    content_id=item["id"],
                    content=item["content"],
                    source="vector",
                    relevance_score=item["score"],
                    recency_score=0.0,
                    metadata=item.get("metadata", {}),
                    timestamp=item["timestamp"]
                )
                results.append(result)
                
        except Exception as e:
            logger.error(f"Vector DB retrieval error: {str(e)}")
        
        return results
    
    def _retrieve_graph(self, 
                       query: str, 
                       filters: Optional[Dict[str, Any]] = None) -> List[RetrievalResult]:
        """
        Retrieve using Graph DB.
        
        Retrieves documents based on relationships and connections.
        """
        results = []
        
        if not self.graph_db:
            return results
        
        try:
            # Mock graph DB implementation
            # In production, this would query Neo4j or similar
            mock_data = [
                {
                    "id": "doc_5",
                    "content": "Knowledge graphs connect entities",
                    "score": 0.87,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"type": "graph", "connections": 5}
                }
            ]
            
            for item in mock_data:
                result = RetrievalResult(
                    content_id=item["id"],
                    content=item["content"],
                    source="graph",
                    relevance_score=item["score"],
                    recency_score=0.0,
                    metadata=item.get("metadata", {}),
                    timestamp=item["timestamp"]
                )
                results.append(result)
                
        except Exception as e:
            logger.error(f"Graph DB retrieval error: {str(e)}")
        
        return results
    
    def _calculate_recency_score(self, timestamp_str: str) -> float:
        """
        Calculate recency score (newer = higher score).
        
        Args:
            timestamp_str: ISO format timestamp
            
        Returns:
            Recency score (0.0 - 1.0)
        """
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            now = datetime.now()
            days_old = (now - timestamp).days
            
            # Decay score based on age
            recency_score = max(0.0, 1.0 - (days_old * self.RECENCY_DECAY))
            return recency_score
        except Exception as e:
            logger.warning(f"Could not calculate recency: {str(e)}")
            return 0.5  # Default middle score
    
    def _rank_results(self, results_dict: Dict[str, RetrievalResult]) -> List[RetrievalResult]:
        """
        Combine and rank all results by combined score.
        
        Combined score = weighted average of relevance and recency
        """
        for result in results_dict.values():
            # Combined score: 70% relevance, 30% recency
            result.combined_score = (result.relevance_score * 0.7) + (result.recency_score * 0.3)
        
        # Sort by combined score descending
        ranked = sorted(
            results_dict.values(), 
            key=lambda x: x.combined_score, 
            reverse=True
        )
        
        return ranked
    
    def retrieve_for_file(self, 
                         query: str, 
                         top_k: int = 5) -> List[RetrievalResult]:
        """Specialized retrieval for file search."""
        return self.retrieve(query, top_k=top_k, filters={"intent": "file"})
    
    def retrieve_for_response(self, 
                             query: str, 
                             top_k: int = 10) -> List[RetrievalResult]:
        """Specialized retrieval for response generation."""
        return self.retrieve(query, top_k=top_k, filters={"intent": "response"})


# Convenience function
def retrieve_documents(query: str, top_k: int = 10) -> List[RetrievalResult]:
    """
    Convenience function to retrieve documents.
    
    Args:
        query: Search query
        top_k: Number of results
        
    Returns:
        List of retrieval results
    """
    retriever = Retriever()
    return retriever.retrieve(query, top_k=top_k)
