"""
Integration guide - How to use Query & Answer module in your main project.
"""

# ============================================================================
# USAGE: IMPORTING AND USING THE QUERY & ANSWER MODULE
# ============================================================================

# 1. BASIC SINGLE QUERY PROCESSING
# ============================================================================
from Query_Answer.core_agent import CoreAgent

# Initialize agent
agent = CoreAgent()

# Process a query
result = agent.process_query("Find the AI research document")

print(f"Intent: {result.intent}")
print(f"Status: {result.status}")
print(f"Output:\n{result.output}")
print(f"Confidence: {result.confidence:.2f}")

if result.citations:
    print("\nCitations:")
    for citation in result.citations:
        print(f"  - {citation['source_id']}")


# 2. BATCH PROCESSING
# ============================================================================
queries = [
    "What is machine learning?",
    "Find the neural networks paper",
    "Explain deep learning"
]

results = agent.process_batch(queries)

for result in results:
    print(f"Query: {result.query}")
    print(f"Status: {result.status}\n")


# 3. DIRECT ACCESS TO COMPONENTS
# ============================================================================
from Query_Answer.intent_classifier import IntentClassifier
from Query_Answer.retriever import Retriever
from Query_Answer.reranker import Reranker
from Query_Answer.rag_generator import RAGGenerator
from Query_Answer.evidence_verifier import EvidenceVerifier

# Step 1: Classify intent
classifier = IntentClassifier()
intent = classifier.classify("Find the document")
print(f"Intent: {intent['intent'].value}")

# Step 2: Retrieve documents
retriever = Retriever()
results = retriever.retrieve("machine learning", top_k=10)

# Step 3: Rerank
reranker = Reranker()
reranked = reranker.rerank("machine learning", results)

# Step 4: Generate output
generator = RAGGenerator()
output = generator.generate(
    query="machine learning",
    intent="response",
    reranked_results=reranked
)

# Step 5: Verify
verifier = EvidenceVerifier()
verification = verifier.verify(
    query="machine learning",
    rag_output=output,
    intent="response"
)
print(f"Verification Status: {verification.status.value}")


# 4. CUSTOM CONFIGURATION
# ============================================================================
from Query_Answer.config import (
    CORE_AGENT_CONFIG,
    RETRIEVER_CONFIG,
    VERIFICATION_CONFIG
)

# Customize settings
CORE_AGENT_CONFIG["max_retries"] = 5
RETRIEVER_CONFIG["top_k_default"] = 15
VERIFICATION_CONFIG["min_pass_score"] = 0.75

# Use with custom config
agent = CoreAgent()


# 5. INTEGRATION IN A LARGER SYSTEM
# ============================================================================
class MainApplicationAgent:
    """Main application that uses Query & Answer module."""
    
    def __init__(self):
        self.qa_agent = CoreAgent()
    
    def handle_user_input(self, user_message: str):
        """Handle user input and return response."""
        
        # Process through Query & Answer system
        result = self.qa_agent.process_query(user_message)
        
        # Handle different outcomes
        if result.status == "success":
            return {
                "output": result.output,
                "citations": result.citations,
                "confidence": result.confidence,
                "status": "success"
            }
        elif result.status == "partial":
            return {
                "output": result.output,
                "warning": "Lower confidence result",
                "status": "partial"
            }
        else:
            return {
                "output": "Unable to process query",
                "status": "failed"
            }


# 6. ERROR HANDLING
# ============================================================================
from Query_Answer.core_agent import CoreAgent

agent = CoreAgent()

try:
    result = agent.process_query("complex query")
    
    if result.status == "failed":
        print("Processing failed, trying alternative method...")
        # Implement fallback logic
    
    if result.verification_passed is False:
        print(f"Verification issues: {result.processing_steps[-1]}")
        
except Exception as e:
    print(f"Error: {str(e)}")


# 7. MONITORING AND DEBUGGING
# ============================================================================
from Query_Answer.core_agent import CoreAgent
import json

agent = CoreAgent()
result = agent.process_query("What is AI?")

# Check processing steps
for step in result.processing_steps:
    print(f"Step: {step['step']}")
    print(f"  Timestamp: {step.get('timestamp')}")
    print(f"  Result: {step.get('result', step.get('status'))}")

# Export result for analysis
export_data = {
    "query": result.query,
    "intent": result.intent,
    "status": result.status,
    "retry_count": result.retry_count,
    "confidence": result.confidence,
    "processing_steps": result.processing_steps
}

with open("query_log.json", "w") as f:
    json.dump(export_data, f, indent=2)


# 8. WITH CUSTOM DATABASE CONNECTIONS
# ============================================================================
from Query_Answer.core_agent import CoreAgent
# Assume you have these set up
# fts5_index = setup_fts5_index()
# vector_db = connect_to_qdrant()
# graph_db = connect_to_neo4j()
# llm_model = load_llm_model()

# Initialize with custom connections
agent = CoreAgent(
    fts5_index=None,  # Paste fts5_index
    vector_db=None,   # Paste vector_db
    graph_db=None,    # Paste graph_db
    llm_model=None    # Paste llm_model
)

result = agent.process_query("Find data")


# 9. INTENT-SPECIFIC PROCESSING
# ============================================================================
from Query_Answer.intent_classifier import IntentClassifier

classifier = IntentClassifier()
classification = classifier.classify("Where is the ML document?")

if classification["intent"].value == "file":
    print("User is looking for a file")
    # Handle file search
elif classification["intent"].value == "response":
    print("User wants an answer")
    # Handle response generation


if __name__ == "__main__":
    print("Query & Answer Module - Integration Examples")
    
    # Run basic example
    agent = CoreAgent()
    result = agent.process_query("What is machine learning?")
    print(f"\nQuery: {result.query}")
    print(f"Status: {result.status}")
    print(f"Output:\n{result.output}")
