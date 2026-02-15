#!/usr/bin/env python3
"""graph_compact.py — Compact duplicate graph nodes after canonicalization.

Finds entity nodes that share the same (node_type, canonical) and merges
them: picks a primary node_id, repoints all edges from duplicates to the
primary, and deletes the duplicate nodes.

Usage (inside Docker):
    python -m scripts.graph_compact --dry-run   # preview
    python -m scripts.graph_compact              # execute

Or from host via docker compose exec:
    docker compose exec api python /app/scripts/graph_compact.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import os

# Allow running from repo root or inside container
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
sys.path.insert(0, "/app")

from app.db.conn import get_conn
from app.graph.canonicalize import canonicalize_entity_name, normalize_entity_type

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("graph_compact")


def _canonical_node_id(norm_type: str, canon: str) -> str:
    raw = f"{norm_type}|{canon}"
    return f"ent:{hashlib.sha1(raw.encode()).hexdigest()[:16]}"


def compact(dry_run: bool = True) -> dict:
    """Find and merge duplicate entity nodes.

    Returns stats: {groups_found, nodes_deleted, edges_repointed}.
    """
    conn = get_conn()
    stats = {"groups_found": 0, "nodes_deleted": 0, "edges_repointed": 0}

    try:
        # 1. Load all entity nodes
        rows = conn.execute(
            "SELECT node_id, node_type, props FROM graph_node WHERE node_id LIKE 'ent:%'"
        ).fetchall()

        # Type priority: prefer more specific types over generic ones
        _TYPE_PRIORITY = {
            "Person": 10, "Org": 9, "Place": 8, "Project": 7,
            "Technology": 6, "Component": 5, "Topic": 4, "Other": 1,
        }

        # 2. Group by canonical name ONLY (ignoring type differences)
        #    This catches duplicates like ("Other","dog") + ("Topic","dog")
        groups: dict[str, list[dict]] = {}
        for node_id, node_type, props_json in rows:
            props = json.loads(props_json) if props_json else {}
            norm_type = normalize_entity_type(node_type)

            # Compute canonical — use stored canonical if available, else derive
            canon = props.get("canonical")
            if not canon:
                raw_name = props.get("name") or props.get("raw_name") or ""
                canon = canonicalize_entity_name(raw_name, entity_type=norm_type)
            if not canon:
                continue

            groups.setdefault(canon, []).append({
                "node_id": node_id,
                "node_type": norm_type,
                "raw_db_type": node_type,
                "props": props,
                "canon": canon,
            })

        # 3. Process groups with duplicates
        for canon, nodes in groups.items():
            if len(nodes) < 2:
                continue

            stats["groups_found"] += 1

            # Pick the best type: highest priority among the group
            best_type = max(
                (n["node_type"] for n in nodes),
                key=lambda t: _TYPE_PRIORITY.get(t, 0),
            )
            # Compute the canonical node_id using best_type
            target_id = _canonical_node_id(best_type, canon)

            # Pick primary: prefer node whose id already matches target_id,
            # else highest confidence
            primary = None
            for n in nodes:
                if n["node_id"] == target_id:
                    primary = n
                    break
            if primary is None:
                nodes.sort(key=lambda x: -float(x["props"].get("confidence", 0)))
                primary = nodes[0]

            primary_id = primary["node_id"]
            duplicates = [n for n in nodes if n["node_id"] != primary_id]

            logger.info(
                "GROUP canon=%r best_type=%s: primary=%s, merging %d duplicates",
                canon, best_type, primary_id, len(duplicates),
            )

            for dup in duplicates:
                dup_id = dup["node_id"]

                # Repoint edges
                for col in ("from_node_id", "to_node_id"):
                    edge_rows = conn.execute(
                        f"SELECT edge_id FROM graph_edge WHERE {col} = ?",
                        (dup_id,),
                    ).fetchall()
                    for (edge_id,) in edge_rows:
                        stats["edges_repointed"] += 1
                        if not dry_run:
                            conn.execute(
                                f"UPDATE graph_edge SET {col} = ? WHERE edge_id = ?",
                                (primary_id, edge_id),
                            )
                        logger.info(
                            "  %s edge %s: %s.%s -> %s",
                            "WOULD repoint" if dry_run else "Repointed",
                            edge_id[:12], col, dup_id[:20], primary_id[:20],
                        )

                # Merge props into primary (highest confidence, longest name)
                merged_props = {**primary["props"], **dup["props"]}
                merged_props["confidence"] = max(
                    float(primary["props"].get("confidence", 0)),
                    float(dup["props"].get("confidence", 0)),
                )
                merged_props["canonical"] = canon
                old_name = primary["props"].get("name", "")
                dup_name = dup["props"].get("name", "")
                merged_props["name"] = old_name if len(old_name) >= len(dup_name) else dup_name
                primary["props"] = merged_props

                if not dry_run:
                    conn.execute(
                        "UPDATE graph_node SET node_type = ?, props = ? WHERE node_id = ?",
                        (best_type, json.dumps(merged_props), primary_id),
                    )
                    conn.execute("DELETE FROM graph_node WHERE node_id = ?", (dup_id,))

                stats["nodes_deleted"] += 1
                logger.info(
                    "  %s duplicate node %s",
                    "WOULD delete" if dry_run else "Deleted",
                    dup_id,
                )

        if not dry_run:
            conn.commit()

        return stats

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Compact duplicate entity nodes in the graph.")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Preview changes without modifying the database.")
    args = parser.parse_args()

    logger.info("Graph compaction — %s mode", "DRY RUN" if args.dry_run else "LIVE")
    stats = compact(dry_run=args.dry_run)
    logger.info(
        "Done: %d duplicate groups, %d nodes %s, %d edges %s",
        stats["groups_found"],
        stats["nodes_deleted"],
        "would be deleted" if args.dry_run else "deleted",
        stats["edges_repointed"],
        "would be repointed" if args.dry_run else "repointed",
    )


if __name__ == "__main__":
    main()
