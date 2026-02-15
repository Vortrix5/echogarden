# Query & Answer Module - Production Ready Architecture

This module implements a sophisticated Query & Answer system with:

- Intent classification
- Hybrid retrieval (FTS5 + Vector DB + Recency + Graph DB)
- Cross-encoder reranking
- RAG-based response generation
- Evidence verification with automatic retry logic

## Architecture Overview

```
User Query
    ↓
1. Intent Classifier → Determine FILE or RESPONSE
    ↓
2. Retriever (Hybrid)
    ├─ FTS5 (Full-Text Search)
    ├─ Vector DB (Semantic Similarity)
    ├─ Recency Weighting (Recent = Higher Priority)
    └─ Graph DB (Relationships)
    ↓
3. Reranker (Cross-Encoder)
    ├─ Quality Check
    ├─ Diversity Check
    └─ Relevance Re-scoring
    ↓
4. RAG Generator
    ├─ For FILES: Return file references
    └─ For RESPONSE: Generate LLM response with citations
    ↓
5. Evidence Verifier
    ├─ Claim Support Check
    ├─ Factuality Check
    ├─ Consistency Check
    ├─ Completeness Check
    └─ Safety Check
    ↓
    ├─ PASS → Return to user ✓
    ├─ RETRY → Adjust parameters and restart
    └─ FAIL → Return partial result (after max retries)
```

## Components

### 1. Intent Classifier (`intent_classifier.py`)

Determines user's intent: FILE vs RESPONSE

**Usage:**

```python
from intent_classifier import IntentClassifier

classifier = IntentClassifier()
result = classifier.classify("Find the AI paper")
# Returns: {"intent": Intent.FILE, "confidence": 0.95, "reason": "..."}
```

### 2. Retriever (`retriever.py`)

Hybrid retrieval from multiple sources

**Features:**

- Full-Text Search (FTS5)
- Semantic Search (Vector DB)
- Recency weighting
- Graph-based relationships
- Automatic source merging and deduplication

**Usage:**

```python
from retriever import Retriever

retriever = Retriever(fts5_index, vector_db, graph_db)
results = retriever.retrieve("machine learning", top_k=10)
```

### 3. Reranker (`reranker.py`)

Cross-encoder based reranking with quality filtering

**Features:**

- Cross-encoder scoring
- Quality assessment
- Diversity checking
- Spam detection
- Result filtering

**Usage:**

```python
from reranker import Reranker

reranker = Reranker()
reranked = reranker.rerank(query, retrieval_results)
```

### 4. RAG Generator (`rag_generator.py`)

Generates responses or file references

**Features:**

- FILE intent: Returns structured file references
- RESPONSE intent: Generates LLM responses with citations
- Context building from retrieved documents
- RAG prompt engineering

**Usage:**

```python
from rag_generator import RAGGenerator

generator = RAGGenerator(llm_model)
output = generator.generate(query, intent, reranked_results)
```

### 5. Evidence Verifier (`evidence_verifier.py`)

Validates output through multiple verification stages

**Stages:**

1. Claim Support - Are claims backed by sources?
2. Factuality - Are facts accurate?
3. Consistency - Is output internally consistent?
4. Completeness - Does it answer the query?
5. Safety - Is content safe/appropriate?

**Usage:**

```python
from evidence_verifier import EvidenceVerifier

verifier = EvidenceVerifier()
result = verifier.verify(query, rag_output, intent)
# Returns: VerificationResult with status (PASS/RETRY/FAIL)
```

### 6. Core Agent (`core_agent.py`)

Orchestrates the entire pipeline with retry logic

**Usage:**

```python
from core_agent import CoreAgent

agent = CoreAgent(fts5_index, vector_db, graph_db, llm_model)

# Single query
result = agent.process_query("What is machine learning?")
print(result.output)
print(result.status)  # "success", "partial", or "failed"

# Batch queries
results = agent.process_batch(["query1", "query2", "query3"])
```

## Data Flow Example

### FILE Intent Query

```
User: "Find the document about machine learning"
    ↓
Intent Classifier: "FILE" (0.95 confidence)
    ↓
Retriever: Returns 10 results from vector DB + FTS5
    ↓
Reranker: Filters and ranks by relevance (0.7+)
    ↓
RAG Generator: Extracts file references
    ↓
Evidence Verifier:
    - Checks files exist and are accessible ✓
    - Validates paths ✓
    - Status: PASS
    ↓
Output:
Found 3 matching documents:
1. machine_learning_basics.pdf
2. neural_networks_guide.pdf
3. ml_algorithms.docx
```

### RESPONSE Intent Query

```
User: "What is machine learning?"
    ↓
Intent Classifier: "RESPONSE" (0.92 confidence)
    ↓
Retriever: Returns 10 results from all sources
    ↓
Reranker: Filters and ranks by quality
    ↓
RAG Generator: Generates response with context
    ↓
Evidence Verifier:
    - Claims supported by sources? ✓
    - Factually accurate? ✓
    - Consistent? ✓
    - Complete answer? ✓
    - Safe content? ✓
    - Score: 0.85 (PASS)
    ↓
Output:
"Machine learning is a subset of artificial intelligence that enables
systems to learn and improve from experience without being explicitly
programmed... [response continues]"

Citations:
1. ml_basics.pdf (0.92)
2. ai_research_paper.pdf (0.88)
```

## Configuration

Edit `config.py` to customize:

- Retrieval weights (FTS5 vs Vector vs Recency)
- Reranking thresholds
- Verification score requirements
- LLM model selection
- Max retries and retry strategies

## Retry Logic

When evidence verification fails:

1. **PASS**: Return immediately to user
2. **RETRY**: Adjust parameters (increase top_k, modify prompt) and restart
3. **FAIL**: After max retries, return partial result

Retry strategies automatically adjust:

- Increase retrieval result count
- Modify RAG prompt for more context
- Lower relevance thresholds
- Use alternative search terms

## Output Format

### QueryResult

```python
QueryResult(
    query="user query",
    intent="file|response",
    status="success|partial|failed",
    output="user-facing output",
    citations=[...],
    confidence=0.85,
    verification_passed=True,
    retry_count=0,
    processing_steps=[...],
    timestamp="2026-02-15T10:30:00"
)
```

## Performance Considerations

1. **Hybrid Retrieval**: Combines multiple sources for better coverage
2. **Deduplication**: Removes duplicate results across sources
3. **Reranking**: Expensive operation but improves quality
4. **Verification**: Can be slow but necessary for safety
5. **Retry Logic**: Limits retries to prevent infinite loops

## Extending the System

### Add New Retrieval Source

```python
# In retriever.py, add new method:
def _retrieve_custom_source(self, query):
    # Implementation
    return results

# Update retrieve() to include it
results.update(self._retrieve_custom_source(query))
```

### Add New Verification Check

```python
# In evidence_verifier.py, add new method:
def _verify_custom_aspect(self, rag_output):
    # Implementation
    return score, issues
```

### Customize Intent Classification

Edit `intent_classifier.py` FILE_KEYWORDS and RESPONSE_KEYWORDS

## Testing

```bash
# Run single query
python core_agent.py

# Test batch processing
from core_agent import CoreAgent
agent = CoreAgent()
results = agent.process_batch([...])
```

## Requirements

- Python 3.8+
- sentence-transformers (for cross-encoder)
- OpenAI/other LLM API (for response generation)
- Qdrant (vector DB)
- SQLite (FTS5)
- Neo4j or similar (graph DB - optional)

## Installation

```bash
pip install sentence-transformers
pip install qdrant-client
pip install openai  # or other LLM provider
```

## Version

1.0.0 - Production Ready
