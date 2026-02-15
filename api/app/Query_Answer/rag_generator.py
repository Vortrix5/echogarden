"""
RAG (Retrieval-Augmented Generation) - Generates responses and file references.

Takes reranked results and:
1. Generates responses using LLM + context (for RESPONSE intent)
2. Returns file references (for FILE intent)
3. Formats output for evidence verification
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class RAGOutput:
    """Output from RAG generation."""
    intent: str  # "file" or "response"
    output_type: str  # "file_list" or "generated_response"
    content: str  # File paths as string or generated response text
    citations: List[Dict[str, Any]]  # Source documents used
    confidence: float
    generation_timestamp: str


class RAGGenerator:
    """
    Generates responses or file references using retrieved context.
    """
    
    def __init__(self, llm_model=None):
        """
        Initialize the RAG generator.
        
        Args:
            llm_model: Language model for response generation
        """
        self.llm_model = llm_model
        logger.info("Initialized RAGGenerator")
    
    def generate(self, 
                query: str,
                intent: str,
                reranked_results: List[Any],
                max_context_tokens: int = 2048) -> RAGOutput:
        """
        Generate output based on intent and reranked results.
        
        Args:
            query: Original user query
            intent: Classification intent ("file" or "response")
            reranked_results: Reranked retrieval results
            max_context_tokens: Maximum tokens for context
            
        Returns:
            RAGOutput with generated content
        """
        logger.info(f"Generating {intent} output for query: {query}")
        
        if intent == "file":
            return self._generate_file_output(query, reranked_results)
        elif intent == "response":
            return self._generate_response_output(query, reranked_results, max_context_tokens)
        else:
            return self._generate_unknown_output(query, reranked_results)
    
    def _generate_file_output(self, 
                             query: str, 
                             results: List[Any]) -> RAGOutput:
        """
        Generate file reference output.
        
        Returns file paths/locations for user to access.
        """
        logger.info(f"Generating file output for query: {query}")
        
        # Extract file metadata from results
        file_references = []
        citations = []
        
        for result in results:
            # Check if result has file metadata
            if self._is_file_reference(result):
                file_ref = {
                    "path": result.metadata.get("file_path", result.content_id),
                    "name": result.metadata.get("file_name", "Unknown"),
                    "type": result.metadata.get("file_type", "document"),
                    "relevance": result.reranked_score
                }
                file_references.append(file_ref)
                citations.append({
                    "source_id": result.content_id,
                    "source": result.metadata.get("source", "unknown"),
                    "relevance_score": result.reranked_score
                })
        
        # Format file output
        if file_references:
            file_list = "\n".join([
                f"📄 {ref['name']} ({ref['type']})\n   Path: {ref['path']}"
                for ref in file_references
            ])
            output_content = f"Found {len(file_references)} matching file(s):\n\n{file_list}"
            confidence = file_references[0]["relevance"] if file_references else 0.0
        else:
            output_content = "No file found matching your query."
            confidence = 0.0
        
        return RAGOutput(
            intent="file",
            output_type="file_list",
            content=output_content,
            citations=citations,
            confidence=confidence,
            generation_timestamp=datetime.now().isoformat()
        )
    
    def _generate_response_output(self, 
                                 query: str, 
                                 results: List[Any],
                                 max_context_tokens: int) -> RAGOutput:
        """
        Generate LLM response using retrieved context.
        
        Creates a RAG prompt with retrieved documents and generates response.
        """
        logger.info(f"Generating response for query: {query}")
        
        # 1. Build context from reranked results
        context = self._build_context(results, max_context_tokens)
        citations = self._extract_citations(results)
        
        # 2. Build RAG prompt
        rag_prompt = self._build_rag_prompt(query, context)
        
        # 3. Generate response using LLM
        response = self._generate_response_from_llm(rag_prompt)
        
        # 4. Calculate confidence based on context quality
        confidence = self._calculate_response_confidence(results)
        
        return RAGOutput(
            intent="response",
            output_type="generated_response",
            content=response,
            citations=citations,
            confidence=confidence,
            generation_timestamp=datetime.now().isoformat()
        )
    
    def _generate_unknown_output(self, 
                                query: str,
                                results: List[Any]) -> RAGOutput:
        """
        Generate output for unknown intent.
        
        Combines file references and response generation.
        """
        logger.info(f"Generating unknown intent output for query: {query}")
        
        output_content = f"""
Unable to clearly determine your request. Here's what I found:

**For Your Reference:**
{self._format_file_references(results)}

**Summary:**
{self._generate_summary(results)}
        """
        
        citations = self._extract_citations(results)
        confidence = 0.5
        
        return RAGOutput(
            intent="unknown",
            output_type="hybrid",
            content=output_content.strip(),
            citations=citations,
            confidence=confidence,
            generation_timestamp=datetime.now().isoformat()
        )
    
    def _build_context(self, results: List[Any], max_tokens: int) -> str:
        """Build context string from reranked results."""
        context_parts = []
        token_count = 0
        
        for result in results:
            # Rough token estimation (1 token ≈ 4 chars)
            content_tokens = len(result.content) // 4
            
            if token_count + content_tokens > max_tokens:
                break
            
            context_parts.append(
                f"[Source: {result.content_id}]\n{result.content}\n"
            )
            token_count += content_tokens
        
        return "\n---\n".join(context_parts)
    
    def _build_rag_prompt(self, query: str, context: str) -> str:
        """Build the RAG prompt for LLM."""
        prompt = f"""Based on the following retrieved context, answer the user's question.

**Retrieved Context:**
{context}

**User Question:**
{query}

**Instructions:**
1. Provide a clear, concise answer based on the context
2. If the context doesn't contain sufficient information, say so
3. Cite sources from the provided context
4. Be accurate and avoid hallucination

**Answer:**"""
        
        return prompt
    
    def _generate_response_from_llm(self, prompt: str) -> str:
        """
        Generate response using LLM.
        
        Mock implementation - replace with actual LLM call.
        """
        if self.llm_model:
            # Use actual LLM
            # response = self.llm_model.generate(prompt)
            pass
        
        # Mock response for now
        mock_response = """Based on the provided context, here is a comprehensive answer to your question.

The retrieved documents indicate that this is an important topic with multiple aspects to consider. 

Key points from the sources:
- Point 1: Details from source material
- Point 2: Additional relevant information
- Point 3: Concluding remarks

This answer is generated based on the most relevant sources found in the knowledge base."""
        
        logger.info("Generated LLM response (mock)")
        return mock_response
    
    def _calculate_response_confidence(self, results: List[Any]) -> float:
        """
        Calculate confidence in generated response.
        
        Based on:
        - Number of relevant sources
        - Quality of top sources
        - Coverage of query
        """
        if not results:
            return 0.0
        
        # Average score of top results
        top_scores = [r.reranked_score for r in results[:3]]
        avg_score = sum(top_scores) / len(top_scores) if top_scores else 0.0
        
        # Boost confidence if we have multiple sources
        source_boost = min(0.2, len(results) * 0.05)
        
        confidence = min(1.0, avg_score + source_boost)
        
        return confidence
    
    def _extract_citations(self, results: List[Any]) -> List[Dict[str, Any]]:
        """Extract citation information from results."""
        citations = []
        
        for result in results[:5]:  # Top 5 sources
            citations.append({
                "source_id": result.content_id,
                "source_type": result.metadata.get("type", "unknown"),
                "relevance_score": result.reranked_score,
                "content_preview": result.content[:200] + "..." if len(result.content) > 200 else result.content
            })
        
        return citations
    
    def _is_file_reference(self, result: Any) -> bool:
        """Check if result is a file reference."""
        return (
            hasattr(result, 'metadata') and 
            ("file_path" in result.metadata or "file_name" in result.metadata)
        )
    
    def _format_file_references(self, results: List[Any]) -> str:
        """Format file references for output."""
        files = [r for r in results if self._is_file_reference(r)]
        
        if not files:
            return "No specific files found."
        
        return "\n".join([
            f"- {f.metadata.get('file_name', f.content_id)}"
            for f in files[:5]
        ])
    
    def _generate_summary(self, results: List[Any]) -> str:
        """Generate summary of retrieved results."""
        if not results:
            return "No relevant information found."
        
        summary = f"Found {len(results)} relevant sources with average confidence {sum(r.reranked_score for r in results) / len(results):.2f}"
        
        return summary


# Convenience function
def generate_rag_output(query: str, 
                       intent: str,
                       reranked_results: List[Any]) -> RAGOutput:
    """
    Convenience function to generate RAG output.
    
    Args:
        query: User query
        intent: Classification intent
        reranked_results: Reranked results
        
    Returns:
        RAG output
    """
    generator = RAGGenerator()
    return generator.generate(query, intent, reranked_results)
