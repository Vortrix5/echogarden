"""
Core Agent - Orchestrates the Query & Answer pipeline.

Pipeline flow:
1. Intent Classification - Determine if user wants FILE or RESPONSE
2. Retrieval - Hybrid retrieval from FTS5, Vector DB, Recency, Graph DB
3. Reranking - Cross-encoder reranking with quality checks
4. RAG Generation - Generate response or file references
5. Evidence Verification - Verify output with claim checking
6. Output - Return to user or retry process

If verification fails, automatically retry with adjusted parameters.
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

from .intent_classifier import IntentClassifier, Intent
from .retriever import Retriever, RetrievalResult
from .reranker import Reranker, RerankedResult
from .rag_generator import RAGGenerator, RAGOutput
from .evidence_verifier import EvidenceVerifier, VerificationStatus, VerificationResult

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Final result from the Query & Answer system."""
    query: str
    intent: str
    status: str  # "success", "failed", "partial"
    output: str  # User-facing output
    citations: List[Dict[str, Any]]
    confidence: float
    verification_passed: bool
    retry_count: int
    processing_steps: List[Dict[str, Any]]
    timestamp: str


class CoreAgent:
    """
    Main orchestrator for Query & Answer pipeline.
    
    Coordinates all components and manages retry logic.
    """
    
    # Configuration
    MAX_RETRIES = 3
    RETRY_WITH_INCREASED_RESULTS = True
    
    def __init__(self,
                 fts5_index=None,
                 vector_db=None,
                 graph_db=None,
                 llm_model=None):
        """
        Initialize the core agent.
        
        Args:
            fts5_index: Full-text search index
            vector_db: Vector database (Qdrant)
            graph_db: Graph database
            llm_model: LLM for response generation
        """
        self.intent_classifier = IntentClassifier()
        self.retriever = Retriever(
            fts5_index=fts5_index,
            vector_db=vector_db,
            graph_db=graph_db
        )
        self.reranker = Reranker()
        self.rag_generator = RAGGenerator(llm_model=llm_model)
        self.evidence_verifier = EvidenceVerifier()
        
        logger.info("Initialized CoreAgent")
    
    def process_query(self, query: str) -> QueryResult:
        """
        Process a user query through the entire pipeline.
        
        Args:
            query: User's query string
            
        Returns:
            QueryResult with output and metadata
        """
        logger.info(f"Processing query: {query}")
        
        processing_steps = []
        retry_count = 0
        verification_passed = False
        final_output = None
        citations = []
        confidence = 0.0
        
        # Step 1: Intent Classification
        step_info = {"step": "intent_classification", "timestamp": datetime.now().isoformat()}
        logger.info("Step 1: Intent Classification")
        
        intent_result = self.intent_classifier.classify(query)
        intent = intent_result["intent"].value
        intent_confidence = intent_result["confidence"]
        
        step_info["result"] = intent
        step_info["confidence"] = intent_confidence
        processing_steps.append(step_info)
        
        # Retry loop for verification failures
        retry_count = 0
        while retry_count < self.MAX_RETRIES and not verification_passed:
            
            try:
                # Step 2: Retrieval
                step_info = {"step": "retrieval", "timestamp": datetime.now().isoformat()}
                logger.info("Step 2: Retrieval")
                
                top_k = 10 + (retry_count * 5)  # Increase results on retry
                
                if intent == "file":
                    retrieval_results = self.retriever.retrieve_for_file(query, top_k=top_k)
                else:
                    retrieval_results = self.retriever.retrieve_for_response(query, top_k=top_k)
                
                step_info["result_count"] = len(retrieval_results)
                step_info["top_score"] = retrieval_results[0].combined_score if retrieval_results else 0
                processing_steps.append(step_info)
                
                # Step 3: Reranking
                step_info = {"step": "reranking", "timestamp": datetime.now().isoformat()}
                logger.info("Step 3: Reranking")
                
                reranked_results = self.reranker.rerank(query, retrieval_results)
                filtered_results = self.reranker.filter_results(reranked_results)
                
                step_info["initial_count"] = len(reranked_results)
                step_info["after_filter"] = len(filtered_results)
                processing_steps.append(step_info)
                
                if not filtered_results:
                    logger.warning("No results passed reranking filter")
                    retry_count += 1
                    continue
                
                # Step 4: RAG Generation
                step_info = {"step": "rag_generation", "timestamp": datetime.now().isoformat()}
                logger.info("Step 4: RAG Generation")
                
                # Convert RerankedResult back to format for RAG
                rag_input = [self._convert_to_rag_input(r) for r in filtered_results]
                rag_output = self.rag_generator.generate(
                    query=query,
                    intent=intent,
                    reranked_results=rag_input
                )
                
                step_info["output_type"] = rag_output.output_type
                step_info["confidence"] = rag_output.confidence
                processing_steps.append(step_info)
                
                # Step 5: Evidence Verification
                step_info = {"step": "evidence_verification", "timestamp": datetime.now().isoformat()}
                logger.info("Step 5: Evidence Verification")
                
                verification_result = self.evidence_verifier.verify(
                    query=query,
                    rag_output=rag_output,
                    intent=intent
                )
                
                step_info["status"] = verification_result.status.value
                step_info["score"] = verification_result.overall_score
                step_info["issues"] = verification_result.issues
                processing_steps.append(step_info)
                
                # Check verification status
                if verification_result.status == VerificationStatus.PASS:
                    logger.info("✓ Verification PASSED")
                    verification_passed = True
                    final_output = rag_output.content
                    citations = rag_output.citations
                    confidence = rag_output.confidence
                    
                elif verification_result.status == VerificationStatus.RETRY:
                    logger.info("⟳ Verification suggests RETRY")
                    retry_count += 1
                    if retry_count >= self.MAX_RETRIES:
                        logger.warning(f"Max retries ({self.MAX_RETRIES}) reached")
                        final_output = rag_output.content
                        citations = rag_output.citations
                        confidence = verification_result.overall_score
                        break
                    continue
                    
                else:  # FAIL
                    logger.warning("✗ Verification FAILED")
                    retry_count += 1
                    if retry_count >= self.MAX_RETRIES:
                        logger.warning(f"Max retries ({self.MAX_RETRIES}) reached")
                        final_output = rag_output.content
                        citations = rag_output.citations
                        confidence = verification_result.overall_score
                        break
                    continue
                
            except Exception as e:
                logger.error(f"Error in processing pipeline: {str(e)}")
                retry_count += 1
                if retry_count >= self.MAX_RETRIES:
                    final_output = f"Error processing query: {str(e)}"
                    break
        
        # Determine final status
        if verification_passed:
            status = "success"
        elif final_output:
            status = "partial"
        else:
            status = "failed"
        
        # Create result
        result = QueryResult(
            query=query,
            intent=intent,
            status=status,
            output=final_output or "Unable to process query",
            citations=citations,
            confidence=confidence,
            verification_passed=verification_passed,
            retry_count=retry_count,
            processing_steps=processing_steps,
            timestamp=datetime.now().isoformat()
        )
        
        logger.info(f"Query processing complete. Status: {status}, Retries: {retry_count}")
        
        return result
    
    def _convert_to_rag_input(self, reranked_result: RerankedResult) -> Any:
        """
        Convert RerankedResult to format expected by RAG.
        
        Mock conversion - adjust based on actual RAG expectations.
        """
        class RAGInput:
            def __init__(self, rr):
                self.content_id = rr.content_id
                self.content = rr.content
                self.combined_score = rr.reranked_score
                self.reranked_score = rr.reranked_score
                self.metadata = {"quality_check": rr.quality_check}
        
        return RAGInput(reranked_result)
    
    def process_batch(self, queries: List[str]) -> List[QueryResult]:
        """
        Process multiple queries in batch.
        
        Args:
            queries: List of queries
            
        Returns:
            List of query results
        """
        logger.info(f"Processing batch of {len(queries)} queries")
        results = []
        
        for query in queries:
            try:
                result = self.process_query(query)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch processing error for query '{query}': {str(e)}")
                results.append(QueryResult(
                    query=query,
                    intent="unknown",
                    status="failed",
                    output=f"Error: {str(e)}",
                    citations=[],
                    confidence=0.0,
                    verification_passed=False,
                    retry_count=0,
                    processing_steps=[],
                    timestamp=datetime.now().isoformat()
                ))
        
        return results


# Example usage
def main():
    """Example of using the core agent."""
    
    # Initialize agent
    agent = CoreAgent()
    
    # Example queries
    queries = [
        "Find the document about machine learning",  # FILE intent
        "What is machine learning and how does it work?",  # RESPONSE intent
        "Where can I find the AI research paper?",  # FILE intent
    ]
    
    # Process queries
    for query in queries:
        print(f"\n{'='*70}")
        print(f"Query: {query}")
        print('='*70)
        
        result = agent.process_query(query)
        
        print(f"\nIntent: {result.intent}")
        print(f"Status: {result.status}")
        print(f"Confidence: {result.confidence:.2f}")
        print(f"Verification Passed: {result.verification_passed}")
        print(f"Retries: {result.retry_count}")
        print(f"\nOutput:\n{result.output}")
        
        if result.citations:
            print(f"\nCitations:")
            for i, citation in enumerate(result.citations, 1):
                print(f"  {i}. {citation.get('source_id')} (Score: {citation.get('relevance_score', 'N/A')})")
        
        print(f"\nProcessing Steps:")
        for step in result.processing_steps:
            print(f"  - {step['step']}: {step.get('result', step.get('status', 'N/A'))}")


if __name__ == "__main__":
    main()
