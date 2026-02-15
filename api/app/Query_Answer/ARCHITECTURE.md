"""
Architecture Diagram and System Overview

# Query & Answer Module Architecture

This file documents the complete system architecture including:

1. Component relationships
2. Data flow
3. Decision points
4. Retry mechanisms
5. Integration points
   """

# ============================================================================

# SYSTEM ARCHITECTURE

# ============================================================================

"""
┌─────────────────────────────────────────────────────────────────────────┐
│ │
│ USER QUERY INPUT │
│ │
└────────────────────────────────┬────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. INTENT CLASSIFIER │
│ ──────────────────── │
│ Determines: FILE or RESPONSE (or UNKNOWN) │
│ Confidence: 0.0 - 1.0 │
│ Keywords: Pattern matching + heuristics │
└────────────────────────────────┬────────────────────────────────────────┘
│
┌────────────┴────────────┐
│ │
▼ FILE INTENT ▼ RESPONSE INTENT
(search for documents) (generate answer)
│ │
└────────────┬────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. HYBRID RETRIEVER │
│ ────────────────── │
│ ┌─────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│ │ FTS5 │ │ Vector │ │ Recency │ │ Graph │ │
│ │ Full-Text │ │ DB │ │ Weight │ │ DB │ │
│ │ Search │ │ (Qdrant) │ │ Scoring │ │(Neo4j) │ │
│ │ │ │ │ │ │ │ │ │
│ │ Exact match │ │Semantic │ │ Recent │ │Relation-│ │
│ └─────────────┘ │ similar │ │ docs ↑ │ │ ships │ │
│ └──────────┘ │ priority │ └─────────┘ │
│ └──────────┘ │
│ │
│ Merging Strategy: │
│ - Source weighting: Vector(0.4) > Recency(0.2) > FTS5(0.2) > Graph(0.2)
│ - Deduplication by content_id │
│ - Combined score: 70% relevance + 30% recency │
│ │
│ Results: List of RetrievalResult (top_k documents) │
└────────────────────────────────┬────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. RERANKER (Cross-Encoder) │
│ ──────────────────────────── │
│ │
│ For each result: │
│ ┌──────────────────────────────┐ │
│ │ Cross-Encoder Score: 0.0-1.0 │ │
│ │ Quality Check │ │
│ │ Diversity Check │ │
│ │ Spam Detection │ │
│ └──────────────────────────────┘ │
│ │ │ │ │
│ ▼ ▼ ▼ │
│ [0-0.3] ──────── [0.3-0.5] ──────── [0.5-1.0] │
│ LOW MEDIUM HIGH │
│ Filter Filter Keep │
│ │
│ Final Score = 0.6 _ cross_encoder │
│ + 0.3 _ retrieval_score │
│ + 0.1 * quality_score │
│ - diversity_penalty │
│ │
│ Results: Filtered & ranked RerankedResult │
└────────────────────────────────┬────────────────────────────────────────┘
│
┌────────────┴────────────┐
│ │
▼ FILE INTENT ▼ RESPONSE INTENT
Extract file paths Add LLM context
│ │
└────────────┬────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. RAG GENERATOR (Response/File Output) │
│ ────────────────────────────────────────── │
│ │
│ FILE INTENT: RESPONSE INTENT: │
│ ┌──────────────────────┐ ┌──────────────────────┐ │
│ │ Extract file paths │ │ Build context │ │
│ │ Format references │ │ Create RAG prompt │ │
│ │ Sort by relevance │ │ Call LLM model │ │
│ │ Add metadata │ │ Generate response │ │
│ │ │ │ Add citations │ │
│ │ Output: │ │ Confidence scoring │ │
│ │ ┌──────────────────┐ │ │ │ │
│ │ │ file_1.pdf 0.95 │ │ │ Output: │ │
│ │ │ file_2.pdf 0.92 │ │ │ ┌──────────────────┐ │ │
│ │ │ file_3.pdf 0.88 │ │ │ │Generated response│ │ │
│ │ └──────────────────┘ │ │ │with citations │ │ │
│ └──────────────────────┘ │ └──────────────────┘ │ │
│ └──────────────────────┘ │
│ │
│ RAGOutput structure: │
│ - intent: "file" or "response" │
│ - output_type: "file_list" or "generated_response" │
│ - content: The actual output │
│ - citations: List of sources used │
│ - confidence: 0.0-1.0 │
└────────────────────────────────┬────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. EVIDENCE VERIFIER (Quality & Validity Check) │
│ ────────────────────────────────────────────── │
│ │
│ 5 Verification Stages: │
│ │
│ ┌─────────────────────────────────────────────────┐ │
│ │1. CLAIM SUPPORT (40%) │ │
│ │ - Are claims backed by citations? │ │
│ │ - Do sources exist and are accessible? │30% for files = 1 │
│ └─────────────────────────────────────────────────┘ │
│ │
│ ┌─────────────────────────────────────────────────┐ │
│ │2. FACTUALITY (30%) │ │
│ │ - Are facts accurate? │ │
│ │ - No contradictions with sources? │ │
│ │ - No hallucinations? │ │
│ └─────────────────────────────────────────────────┘ │
│ │
│ ┌─────────────────────────────────────────────────┐ │
│ │3. CONSISTENCY (15%) │ │
│ │ - Internal consistency? │ │
│ │ - Logical flow? │ │
│ │ - No contradictions? │ │
│ └─────────────────────────────────────────────────┘ │
│ │
│ ┌─────────────────────────────────────────────────┐ │
│ │4. COMPLETENESS (10%) │ │
│ │ - Does it answer the query? │ │
│ │ - Are key points covered? │ │
│ │ - Substantive enough? │ │
│ └─────────────────────────────────────────────────┘ │
│ │
│ ┌─────────────────────────────────────────────────┐ │
│ │5. SAFETY (5%) │ │
│ │ - No harmful content? │ │
│ │ - Privacy preserved? │ │
│ │ - Appropriate language? │ │
│ └─────────────────────────────────────────────────┘ │
│ │
│ Weighted Score = (1*0.4 + 0.85*0.3 + 0.9*0.15 + 0.75*0.1 + 0.99*0.05)
│ = 0.89 │
│ │
│ Decision Tree: │
│ ┌─────────────────────────────────────────────────┐ │
│ │ Is Score ≥ 0.70? │ │
│ └──────────┬──────────────────────┬───────────────┘ │
│ YES NO │
│ │ │ │
│ ▼ ▼ │
│ ┌─────────┐ ┌──────────────┐ │
│ │ PASS │ │ Score ≥ 0.50?│ │
│ └─────────┘ └──────┬───────┘ │
│ ↓ YES│ NO │
│ ✓ Send to user │ ▼ │ │
│ │ ┌─────────┴─────────┐ │
│ │ │ RETRY │ │
│ │ │ ──────── │ │
│ │ │ Increase results │ │
│ │ │ New search terms │ │
│ │ │ Modify prompt │ │
│ │ └────────┬──────────┘ │
│ │ │ │
│ │ ▼ (if retries < MAX) │
│ │ ╔═════════════╗ │
│ │ ║ LOOP BACK ║ │
│ │ ║ to Retriever║ │
│ │ ╚═════════════╝ │
│ │ │ │
│ │ └─→ FAIL (after max retries) │
│ │ │
│ └──────────→ ┌──────┐ │
│ │ FAIL │ │
│ └──────┘ │
│ ↓ │
│ ✗ Return partial result │
└────────────────────────────────┬────────────────────────────────────────┘
│
┌────────────┴────────────┐
│ │
▼ SUCCESS ▼ FAILED/PARTIAL
┌──────────────────┐ ┌──────────────────┐
│ Return to User │ │ Return to User │
│ ✓ Full Output │ │ ⚠ Partial/Error │
│ ✓ Citations │ │ ⚠ With retry info│
│ ✓ High Confidence│ │ ✗ Lower Conf │
└──────────────────┘ └──────────────────┘
│ │
└────────────┬────────────┘
│
▼
┌──────────────────┐
│ QUERY COMPLETE │
│ QueryResult │
│ ────────────── │
│ - query │
│ - intent │
│ - status │
│ - output │
│ - citations │
│ - confidence │
│ - verification │
│ - retry_count │
│ - steps (trace) │
└──────────────────┘
"""

# ============================================================================

# ERROR HANDLING AND RETRY LOGIC

# ============================================================================

"""
RETRY MECHANISM:

When Evidence Verifier returns RETRY or FAIL:

Current State: top_k=10, strict threshold
│
▼
VERIFICATION FAIL
│
┌───────┴────────┐
│ │
< MAX_RETRIES? ≥ MAX_RETRIES?
│ │
▼ YES ▼ NO
┌──────────────┐ ┌──────────────┐
│ Retry #1 │ │ Return │
│ top_k = 15 │ │ Partial │
│ threshold ↓ │ │ Result │
└──────┬───────┘ └──────────────┘
│
▼
Re-retrieve documents
│
▼
Re-rerank
│
▼
Re-generate output
│
▼
Re-verify
│
┌──────┴──────┐
│ │
PASS? FAIL?
✓ Return │ Retry #2
│ top_k = 20
│ threshold ↓↓
│
▼ ... continues up to MAX_RETRIES
"""

# ============================================================================

# INTEGRATION WITH DATA INGESTION

# ============================================================================

"""
SYSTEM-WIDE DATA FLOW:

┌──────────────────────────────┐
│ Data Ingestion Module │ (from Data Ingestion/)
│ ──────────────────────── │
│ - Document Parser │
│ - Speech-to-Text │
│ - Document Processing Agent │
└──────────────┬───────────────┘
│
▼ Processed documents + metadata
┌────────────────────┐
│ Indexing Pipeline │
├────────────────────┤
│ FTS5 Index (SQL) │
│ Vector DB (Qdrant) │
│ Graph DB (Neo4j) │
└────────┬───────────┘
│
▼ Ready for retrieval
┌────────────────────┐
│ Query & Answer │
│ Module │ (from Query_Answer/)
│ ────────────────── │
│ Intent Classifier │
│ Retriever │
│ Reranker │
│ RAG Generator │
│ Evidence Verifier │
│ Core Agent │
└────────┬───────────┘
│
▼ Query Results
┌────────────────────┐
│ User Interface │
│ API Layer │
│ Streaming Output │
└────────────────────┘
"""

# ============================================================================

# KEY METRICS AND MONITORING

# ============================================================================

"""
SYSTEM METRICS TO TRACK:

1. Intent Classification Accuracy
   - FILE vs RESPONSE classification rate
   - False positive rate
   - Confidence distribution

2. Retrieval Quality
   - Sources used (FTS5 %, Vector %, Graph %, Recency %)
   - Deduplication rate
   - Average ranking position

3. Reranker Performance
   - Filter-out rate (% of results filtered)
   - Quality score distribution
   - Diversity effectiveness

4. Verification Results
   - Pass rate (% that pass on first try)
   - Retry need rate
   - Failure rate (% after max retries)
   - Average retry count

5. Output Quality
   - User satisfaction rating
   - Citation accuracy
   - Response length distribution
   - File search success rate

6. Performance
   - Query latency (ms)
   - Retrieval time
   - Reranking time
   - Verification time
   - Total pipeline time

7. Retry Statistics
   - Retry trigger reasons
   - Success rate after retry
   - Total retry count distribution
     """

if **name** == "**main**":
print(**doc**)
