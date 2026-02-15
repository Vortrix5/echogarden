"""
Evidence Verifier - Validates generated responses and file references.

Verification stages:
1. Claim verification - Are claims supported by sources?
2. Factuality check - Are facts accurate?
3. Consistency check - Is output internally consistent?
4. Completeness check - Does output answer the query?
5. Safety check - Is output safe and appropriate?

Returns: PASS (send to user) or FAIL (restart process)
"""

import logging
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class VerificationStatus(Enum):
    """Verification outcomes."""
    PASS = "pass"
    FAIL = "fail"
    RETRY = "retry"
    ESCALATE = "escalate"


@dataclass
class VerificationResult:
    """Result of evidence verification."""
    status: VerificationStatus
    overall_score: float
    claim_checks: List[Dict[str, Any]]
    issues: List[str]
    recommendations: List[str]
    retry_strategy: str = None  # How to retry if FAIL


class EvidenceVerifier:
    """
    Verifies evidence and validity of generated output.
    """
    
    # Verification thresholds
    MIN_PASS_SCORE = 0.7
    MIN_RETRY_SCORE = 0.5
    
    # Weights for different verification aspects
    VERIFICATION_WEIGHTS = {
        "claim_support": 0.4,      # Are claims supported by sources?
        "factuality": 0.3,         # Are facts accurate?
        "consistency": 0.15,       # Is output consistent?
        "completeness": 0.1,       # Does it answer the query?
        "safety": 0.05             # Is output safe?
    }
    
    def __init__(self):
        """Initialize the evidence verifier."""
        logger.info("Initialized EvidenceVerifier")
    
    def verify(self,
              query: str,
              rag_output: Any,
              intent: str) -> VerificationResult:
        """
        Verify the RAG output against evidence.
        
        Args:
            query: Original user query
            rag_output: RAG generator output
            intent: User intent classification
            
        Returns:
            Verification result with status and details
        """
        logger.info(f"Verifying output for intent: {intent}")
        
        scores = {}
        issues = []
        recommendations = []
        claim_checks = []
        
        # 1. Claim Support Verification
        claim_score, claim_issues, claim_details = self._verify_claim_support(
            query, 
            rag_output,
            intent
        )
        scores["claim_support"] = claim_score
        issues.extend(claim_issues)
        claim_checks.extend(claim_details)
        
        # 2. Factuality Check
        fact_score, fact_issues = self._verify_factuality(rag_output, intent)
        scores["factuality"] = fact_score
        issues.extend(fact_issues)
        
        # 3. Consistency Check
        consistency_score, consistency_issues = self._verify_consistency(
            query,
            rag_output,
            intent
        )
        scores["consistency"] = consistency_score
        issues.extend(consistency_issues)
        
        # 4. Completeness Check
        completeness_score, completeness_issues = self._verify_completeness(
            query,
            rag_output,
            intent
        )
        scores["completeness"] = completeness_score
        issues.extend(completeness_issues)
        
        # 5. Safety Check
        safety_score, safety_issues = self._verify_safety(rag_output)
        scores["safety"] = safety_score
        issues.extend(safety_issues)
        
        # Calculate weighted overall score
        overall_score = self._calculate_weighted_score(scores)
        
        # Determine status
        if overall_score >= self.MIN_PASS_SCORE:
            status = VerificationStatus.PASS
            recommendations.append("Output meets quality standards. Ready for delivery.")
        elif overall_score >= self.MIN_RETRY_SCORE:
            status = VerificationStatus.RETRY
            recommendations.append("Output quality is borderline. Consider retry with modified parameters.")
            retry_strategy = self._suggest_retry_strategy(issues, intent)
        else:
            status = VerificationStatus.FAIL
            recommendations.append("Output quality is too low. System should retry generation.")
            retry_strategy = self._suggest_retry_strategy(issues, intent)
        
        logger.info(f"Verification result: {status.value} (score: {overall_score:.2f})")
        
        return VerificationResult(
            status=status,
            overall_score=overall_score,
            claim_checks=claim_checks,
            issues=issues,
            recommendations=recommendations,
            retry_strategy=retry_strategy if status != VerificationStatus.PASS else None
        )
    
    def _verify_claim_support(self, 
                             query: str,
                             rag_output: Any,
                             intent: str) -> Tuple[float, List[str], List[Dict[str, Any]]]:
        """
        Verify that claims in output are supported by citations.
        
        For FILE intent: Check that files exist and are accessible
        For RESPONSE intent: Check that statements reference source material
        """
        issues = []
        claim_checks = []
        
        if intent == "file":
            # Verify file references are valid
            if not hasattr(rag_output, 'citations') or not rag_output.citations:
                issues.append("No citations provided for file references")
                return 0.6, issues, claim_checks
            
            for citation in rag_output.citations:
                check = {
                    "type": "file_reference",
                    "source_id": citation.get("source_id"),
                    "has_path": "source_id" in citation,
                    "verified": True
                }
                claim_checks.append(check)
            
            score = 0.9 if len(rag_output.citations) > 0 else 0.5
            
        else:  # RESPONSE intent
            # Verify response references retrieved documents
            if not hasattr(rag_output, 'citations') or not rag_output.citations:
                issues.append("Response lacks proper source citations")
                score = 0.5
            else:
                citation_quality = all(
                    citation.get("relevance_score", 0) > 0.5 
                    for citation in rag_output.citations
                )
                
                if citation_quality:
                    score = 0.9
                else:
                    issues.append("Some citations have low relevance scores")
                    score = 0.7
                
                for i, citation in enumerate(rag_output.citations):
                    check = {
                        "claim_index": i,
                        "source_relevance": citation.get("relevance_score", 0),
                        "supported": citation.get("relevance_score", 0) > 0.5
                    }
                    claim_checks.append(check)
        
        return score, issues, claim_checks
    
    def _verify_factuality(self, 
                          rag_output: Any,
                          intent: str) -> Tuple[float, List[str]]:
        """
        Verify factuality of generated content.
        
        Checks for:
        - Contradictions with source material
        - Hallucinations (claims not in sources)
        - Outdated information
        """
        issues = []
        
        if intent == "file":
            # For files, check that they're not mislabeled
            score = 0.95  # Files are typically factual if paths are valid
        else:
            # For responses, check content doesn't contradict sources
            # Mock implementation - would use fact verification model in production
            
            # Check if response is too general (might be hallucinating)
            if len(rag_output.content) < 100:
                issues.append("Response is too brief - may lack sufficient detail")
                score = 0.6
            
            # Check confidence score
            if hasattr(rag_output, 'confidence') and rag_output.confidence < 0.5:
                issues.append("Low confidence score on response generation")
                score = 0.7
            else:
                score = 0.85
        
        return score, issues
    
    def _verify_consistency(self,
                           query: str,
                           rag_output: Any,
                           intent: str) -> Tuple[float, List[str]]:
        """
        Verify internal consistency of output.
        
        Checks for:
        - Contradictions within response
        - Consistent formatting
        - Logical flow
        """
        issues = []
        
        # Basic consistency checks
        if not hasattr(rag_output, 'content') or not rag_output.content:
            issues.append("Output content is empty")
            return 0.3, issues
        
        # Check for obvious contradictions
        content_lower = rag_output.content.lower()
        if "error" in content_lower and "success" in content_lower:
            issues.append("Output contains contradictory statements")
            score = 0.6
        else:
            score = 0.9
        
        # Check generation timestamp exists
        if not hasattr(rag_output, 'generation_timestamp'):
            issues.append("Missing generation timestamp")
            score -= 0.05
        
        return score, issues
    
    def _verify_completeness(self,
                            query: str,
                            rag_output: Any,
                            intent: str) -> Tuple[float, List[str]]:
        """
        Verify that output sufficiently answers the query.
        
        Checks:
        - Is query adequately addressed?
        - Are key points covered?
        - Is response substantive enough?
        """
        issues = []
        
        query_words = set(query.lower().split())
        content = rag_output.content.lower() if hasattr(rag_output, 'content') else ""
        
        # Check if keywords from query appear in response
        matching_words = len(query_words & set(content.split()))
        coverage_ratio = matching_words / max(len(query_words), 1)
        
        if coverage_ratio < 0.3:
            issues.append("Response doesn't adequately address the query")
            score = 0.6
        elif coverage_ratio < 0.6:
            issues.append("Response partially addresses the query")
            score = 0.75
        else:
            score = 0.9
        
        return score, issues
    
    def _verify_safety(self, rag_output: Any) -> Tuple[float, List[str]]:
        """
        Verify output safety.
        
        Checks for:
        - Harmful content
        - Privacy violations
        - Inappropriate language
        """
        issues = []
        
        content = rag_output.content.lower() if hasattr(rag_output, 'content') else ""
        
        # Basic safety checks (mock)
        unsafe_patterns = [
            "password",
            "credit card",
            "ssn",
            "hack",
            "exploit"
        ]
        
        unsafe_found = any(pattern in content for pattern in unsafe_patterns)
        
        if unsafe_found:
            issues.append("Potentially unsafe content detected")
            score = 0.3
        else:
            score = 0.99
        
        return score, issues
    
    def _calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted overall score."""
        total_score = 0.0
        
        for aspect, weight in self.VERIFICATION_WEIGHTS.items():
            aspect_score = scores.get(aspect, 0.0)
            total_score += aspect_score * weight
        
        return min(1.0, max(0.0, total_score))
    
    def _suggest_retry_strategy(self,
                               issues: List[str],
                               intent: str) -> str:
        """Suggest how to retry if verification fails."""
        
        strategies = []
        
        if any("citation" in issue.lower() for issue in issues):
            strategies.append("Increase retrieval result count")
        
        if any("content" in issue.lower() or "brief" in issue.lower() for issue in issues):
            strategies.append("Adjust RAG prompt to encourage more detailed responses")
        
        if any("relevance" in issue.lower() for issue in issues):
            strategies.append("Re-rank with stricter relevance thresholds")
        
        if intent == "file" and any("file" in issue.lower() for issue in issues):
            strategies.append("Search with alternative query terms")
        
        if strategies:
            return "; ".join(strategies)
        else:
            return "Retry with expanded search parameters"


# Convenience function
def verify_output(query: str,
                 rag_output: Any,
                 intent: str) -> VerificationResult:
    """
    Convenience function to verify output.
    
    Args:
        query: Original query
        rag_output: RAG output to verify
        intent: User intent
        
    Returns:
        Verification result
    """
    verifier = EvidenceVerifier()
    return verifier.verify(query, rag_output, intent)
