"""Phase 5 — bounded graph expansion for retrieval augmentation.

Given a set of seed memory_ids, expands 1–2 hops through shared entities
to discover related memory cards.  Returns scored candidates with the
entity path that connected them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.db.conn import get_conn

logger = logging.getLogger("echogarden.retrieval.graph_expand")

_MAX_EXPANSION_CANDIDATES = 200

# Scores assigned by hop distance
_HOP_SCORES: dict[int, float] = {1: 0.7, 2: 0.4}


@dataclass
class GraphCandidate:
    memory_id: str
    graph_score: float = 0.0
    via_entity_ids: list[str] = field(default_factory=list)
    hop: int = 0


def expand_from_seeds(
    seed_memory_ids: list[str],
    hops: int = 1,
    max_candidates: int = _MAX_EXPANSION_CANDIDATES,
) -> list[GraphCandidate]:
    """Expand from seed memory nodes through entity neighbours.

    Algorithm:
      1. For each seed mem:{memory_id} node, find entity neighbours (ent:* nodes).
      2. For each discovered entity, find other mem:* nodes connected to it (hop-1).
      3. Optionally repeat one more hop from the hop-1 memory nodes.
      4. Assign graph_score based on hop distance.

    Returns candidates sorted by graph_score descending.
    """
    if not seed_memory_ids or hops < 1:
        return []

    hops = min(hops, 2)
    conn = get_conn()
    try:
        return _expand(conn, seed_memory_ids, hops, max_candidates)
    finally:
        conn.close()


def _expand(
    conn,
    seed_memory_ids: list[str],
    hops: int,
    max_candidates: int,
) -> list[GraphCandidate]:
    seed_node_ids = [f"mem:{mid}" for mid in seed_memory_ids]
    seed_set = set(seed_memory_ids)

    # Collect candidates: memory_id -> GraphCandidate
    candidates: dict[str, GraphCandidate] = {}

    # ── Hop 1: seed mem → entity → other mem ────────────
    hop1_entities = _entity_neighbours_of_mem_nodes(conn, seed_node_ids)
    if not hop1_entities:
        return []

    entity_ids_hop1 = [e["entity_node_id"] for e in hop1_entities]
    # Map entity→set of source seeds (for provenance)
    entity_to_seeds: dict[str, list[str]] = {}
    for e in hop1_entities:
        entity_to_seeds.setdefault(e["entity_node_id"], []).append(e["mem_node_id"])

    hop1_mems = _mem_neighbours_of_entities(conn, entity_ids_hop1)
    for m in hop1_mems:
        mid = m["memory_id"]
        if mid in seed_set:
            continue
        ent_id = m["entity_node_id"]
        if mid not in candidates:
            candidates[mid] = GraphCandidate(
                memory_id=mid,
                graph_score=_HOP_SCORES[1],
                via_entity_ids=[ent_id],
                hop=1,
            )
        else:
            # Merge: keep highest score, extend entity path
            c = candidates[mid]
            if ent_id not in c.via_entity_ids:
                c.via_entity_ids.append(ent_id)

        if len(candidates) >= max_candidates:
            break

    # ── Hop 2 (optional) ────────────────────────────────
    if hops >= 2 and len(candidates) < max_candidates:
        hop1_mem_node_ids = [f"mem:{mid}" for mid in candidates]
        hop2_entities = _entity_neighbours_of_mem_nodes(conn, hop1_mem_node_ids)
        if hop2_entities:
            entity_ids_hop2 = list({e["entity_node_id"] for e in hop2_entities})
            hop2_mems = _mem_neighbours_of_entities(conn, entity_ids_hop2)
            for m in hop2_mems:
                mid = m["memory_id"]
                if mid in seed_set or mid in candidates:
                    continue
                ent_id = m["entity_node_id"]
                candidates[mid] = GraphCandidate(
                    memory_id=mid,
                    graph_score=_HOP_SCORES[2],
                    via_entity_ids=[ent_id],
                    hop=2,
                )
                if len(candidates) >= max_candidates:
                    break

    result = sorted(candidates.values(), key=lambda c: c.graph_score, reverse=True)
    return result[:max_candidates]


# ── SQL helpers ──────────────────────────────────────────


def _entity_neighbours_of_mem_nodes(
    conn, mem_node_ids: list[str]
) -> list[dict[str, str]]:
    """Return entity node_ids connected to the given mem:* nodes."""
    if not mem_node_ids:
        return []
    ph = ",".join("?" for _ in mem_node_ids)
    rows = conn.execute(
        f"""
        SELECT from_node_id AS mem_node_id, to_node_id AS entity_node_id
        FROM graph_edge
        WHERE from_node_id IN ({ph}) AND to_node_id LIKE 'ent:%'
        UNION
        SELECT to_node_id AS mem_node_id, from_node_id AS entity_node_id
        FROM graph_edge
        WHERE to_node_id IN ({ph}) AND from_node_id LIKE 'ent:%'
        """,
        mem_node_ids + mem_node_ids,
    ).fetchall()
    return [{"mem_node_id": r[0], "entity_node_id": r[1]} for r in rows]


def _mem_neighbours_of_entities(
    conn, entity_node_ids: list[str]
) -> list[dict[str, str]]:
    """Return mem:* node_ids connected to the given entity nodes."""
    if not entity_node_ids:
        return []
    ph = ",".join("?" for _ in entity_node_ids)
    rows = conn.execute(
        f"""
        SELECT to_node_id AS mem_node_id, from_node_id AS entity_node_id
        FROM graph_edge
        WHERE from_node_id IN ({ph}) AND to_node_id LIKE 'mem:%'
        UNION
        SELECT from_node_id AS mem_node_id, to_node_id AS entity_node_id
        FROM graph_edge
        WHERE to_node_id IN ({ph}) AND from_node_id LIKE 'mem:%'
        """,
        entity_node_ids + entity_node_ids,
    ).fetchall()
    results = []
    for r in rows:
        mem_node_id: str = r[0]
        # Strip "mem:" prefix
        memory_id = mem_node_id[4:] if mem_node_id.startswith("mem:") else mem_node_id
        results.append({"memory_id": memory_id, "entity_node_id": r[1]})
    return results
