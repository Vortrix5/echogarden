"""
Reranker - Reranks retrieval results using cross-encoder models.

Improves ranking by:
1. Computing query-document relevance scores
2. Diversity checking
3. Semantic similarity refinement
4. Removing low-quality results
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class RerankedResult:
    """Represents a reranked document."""
    content_id: str
    content: str
    original_score: float
    reranked_score: float
    ranking_reason: str
    quality_check: Dict[str, Any]


class Reranker:
    """
    Reranks retrieval results using cross-encoder scoring.
    """
    
    # Quality thresholds
    MIN_QUALITY_SCORE = 0.3
    MIN_RELEVANCE_SCORE = 0.5
    
    # Diversity penalty (to avoid very similar results)
    DIVERSITY_PENALTY = 0.05
    
    def __init__(self, cross_encoder_model=None):
        """
        Initialize the reranker.
        
        Args:
            cross_encoder_model: Pre-trained cross-encoder model
        """
        self.cross_encoder_model = cross_encoder_model
        logger.info("Initialized Reranker")
    
    def rerank(self, 
              query: str, 
              results: List[Any]) -> List[RerankedResult]:
        """
        Rerank retrieval results.
        
        Args:
            query: Original query
            results: List of retrieval results
            
        Returns:
            List of reranked results
        """
        logger.info(f"Reranking {len(results)} results for query: {query}")
        
        reranked = []
        seen_content_hashes = set()
        diversity_penalty_applied = 0
        
        for i, result in enumerate(results):
            # 1. Calculate cross-encoder score
            cross_encoder_score = self._calculate_cross_encoder_score(query, result)
            
            # 2. Check quality
            quality_check = self._check_quality(result)
            
            # 3. Apply diversity penalty if content is too similar
            diversity_penalty = self._calculate_diversity_penalty(
                result.content, 
                seen_content_hashes
            )
            
            # 4. Calculate final reranked score
            final_score = (cross_encoder_score * 0.6 + 
                          result.combined_score * 0.3 + 
                          quality_check["score"] * 0.1 - 
                          diversity_penalty)
            
            # 5. Rank reason
            if final_score < self.MIN_RELEVANCE_SCORE:
                reason = "Below minimum relevance threshold"
            elif not quality_check["is_valid"]:
                reason = f"Quality check failed: {quality_check['issues']}"
            else:
                reason = "Passed quality and relevance checks"
            
            reranked_result = RerankedResult(
                content_id=result.content_id,
                content=result.content,
                original_score=result.combined_score,
                reranked_score=final_score,
                ranking_reason=reason,
                quality_check=quality_check
            )
            
            reranked.append(reranked_result)
            seen_content_hashes.add(hash(result.content[:100]))
        
        # Sort by reranked score
        reranked_sorted = sorted(reranked, key=lambda x: x.reranked_score, reverse=True)
        
        if reranked_sorted:
            logger.info(f"Reranked results. Top score: {reranked_sorted[0].reranked_score:.3f}")
        else:
            logger.warning("No results after reranking")
        
        return reranked_sorted
    
    def _calculate_cross_encoder_score(self, query: str, result: Any) -> float:
        """
        Calculate cross-encoder relevance score.
        
        Cross-encoder models compute a score for the (query, document) pair.
        
        Args:
            query: Search query
            result: Retrieval result
            
        Returns:
            Relevance score (0.0 - 1.0)
        """
        # Mock implementation
        # In production, use actual cross-encoder model:
        # >>> from sentence_transformers import CrossEncoder
        # >>> model = CrossEncoder('cross-encoder/ms-marco-MiniLMv2-L12-H384')
        # >>> scores = model.predict([[query, result.content]])
        
        try:
            # Simple mock: score based on query-content overlap
            query_words = set(query.lower().split())
            content_words = set(result.content.lower().split())
            
            overlap = len(query_words & content_words)
            total_words = len(query_words | content_words)
            
            if total_words == 0:
                return 0.0
            
            base_score = overlap / total_words
            
            # Boost if content is longer (more informative)
            content_length_boost = min(0.2, len(result.content) / 1000)
            
            final_score = min(1.0, base_score + content_length_boost)
            
            return final_score
            
        except Exception as e:
            logger.error(f"Cross-encoder scoring error: {str(e)}")
            return 0.5
    
    def _check_quality(self, result: Any) -> Dict[str, Any]:
        """
        Check quality of a retrieval result.
        
        Validates:
        - Content length (not too short)
        - No spam/low-quality patterns
        - Proper formatting
        - Metadata validity
        """
        issues = []
        score = 1.0
        
        # Check content length
        if len(result.content) < 50:
            issues.append("Content too short (<50 chars)")
            score -= 0.3
        
        # Check for spam patterns
        if self._is_spam_content(result.content):
            issues.append("Spam patterns detected")
            score -= 0.5
        
        # Check metadata
        if not result.metadata:
            issues.append("Missing metadata")
            score -= 0.1
        
        # Check source validity
        valid_sources = {"fts5", "vector", "graph"}
        if result.source not in valid_sources and not all(
            s in valid_sources for s in result.source.split(", ")
        ):
            issues.append("Invalid source")
            score -= 0.2
        
        return {
            "is_valid": len(issues) == 0 or score > self.MIN_QUALITY_SCORE,
            "score": max(0.0, score),
            "issues": issues
        }
    
    def _is_spam_content(self, content: str) -> bool:
        """Detect spam/low-quality content patterns."""
        spam_patterns = [
            "click here",
            "spam",
            "xxx",
            "unsubscribe",
            "||||",  # Multiple pipes suggesting formatting issues
        ]
        
        content_lower = content.lower()
        return any(pattern in content_lower for pattern in spam_patterns)
    
    def _calculate_diversity_penalty(self, content: str, seen_hashes: set) -> float:
        """
        Apply diversity penalty for duplicate/similar content.
        
        Prevents the same content from appearing multiple times.
        """
        content_hash = hash(content[:100])
        
        if content_hash in seen_hashes:
            return self.DIVERSITY_PENALTY
        
        return 0.0
    
    def filter_results(self, 
                      reranked: List[RerankedResult], 
                      min_score: float = None) -> List[RerankedResult]:
        """
        Filter reranked results by minimum score.
        
        Args:
            reranked: List of reranked results
            min_score: Minimum reranked score (default: MIN_RELEVANCE_SCORE)
            
        Returns:
            Filtered results above threshold
        """
        threshold = min_score or self.MIN_RELEVANCE_SCORE
        filtered = [r for r in reranked if r.reranked_score >= threshold]
        
        logger.info(f"Filtered {len(reranked)} results to {len(filtered)} above threshold {threshold}")
        
        return filtered


# Convenience function
def rerank_results(query: str, results: List[Any]) -> List[RerankedResult]:
    """
    Convenience function to rerank results.
    
    Args:
        query: Search query
        results: Retrieval results
        
    Returns:
        Reranked results
    """
    reranker = Reranker()
    return reranker.rerank(query, results)
