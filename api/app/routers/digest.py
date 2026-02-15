"""Phase 9 — Daily Digest / Today Feed endpoint."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.db.conn import get_conn

logger = logging.getLogger("echogarden.routers.digest")
router = APIRouter(tags=["digest"])

_WINDOWS = {"24h": 1, "7d": 7, "30d": 30}

# Mime prefix → activity category
_MIME_CATEGORY = {
    "image/": "new_images",
    "audio/": "new_audio",
    "video/": "new_video",
}


def _meta_from_row(row) -> dict:
    """Parse metadata dict from a row."""
    for key in ("metadata_json", "metadata"):
        val = row[key] if key in row.keys() else None
        if val and isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(val, dict):
            return val
    return {}


def _card_title(row, meta: dict) -> str:
    fp = meta.get("file_path", "")
    if fp:
        return os.path.basename(fp)
    summary = (row["summary"] or "")[:80]
    return summary or row["memory_id"][:16]


@router.get("/feed/today")
async def feed_today(
    window: str = Query("24h", pattern="^(24h|7d|30d)$"),
    limit: int = Query(10, ge=1, le=50),
):
    """Personal-assistant-style daily digest."""
    days = _WINDOWS.get(window, 1)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_conn()
    try:
        # ── 1. Reminders (from metadata actions) ─────────
        reminders: list[dict] = []
        action_rows = conn.execute(
            """SELECT memory_id, summary, created_at,
                      metadata, metadata_json
               FROM memory_card
               WHERE created_at >= ?
               ORDER BY created_at DESC
               LIMIT 200""",
            (cutoff,),
        ).fetchall()

        for r in action_rows:
            meta = _meta_from_row(r)
            actions = meta.get("actions") or []
            if not isinstance(actions, list):
                continue
            for a in actions:
                if not isinstance(a, dict):
                    continue
                text = a.get("text", "").strip()
                if not text:
                    continue
                mid = r["memory_id"]
                blob_id = meta.get("blob_id", "")
                file_path = meta.get("file_path", "")
                reminders.append({
                    "memory_id": mid,
                    "title": _card_title(r, meta),
                    "text": text,
                    "due": a.get("due") or "",
                    "priority": a.get("priority") or "medium",
                    "open_url": f"/api/cards/{mid}/open" if (blob_id or file_path) else "",
                })

        # Sort: overdue first, then by priority
        _prio_map = {"high": 0, "medium": 1, "low": 2}
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        def _reminder_sort(r: dict):
            due = r.get("due") or "9999-12-31"
            is_overdue = 0 if due <= now_str else 1
            return (is_overdue, _prio_map.get(r["priority"], 1), due)

        reminders.sort(key=_reminder_sort)
        reminders = reminders[:limit]

        # ── 2. Recent memories (enriched with media URLs) ─
        card_rows = conn.execute(
            """SELECT mc.memory_id, mc.summary, mc.created_at, mc.type,
                      mc.metadata, mc.metadata_json,
                      b.mime AS blob_mime, b.blob_id AS b_blob_id
               FROM memory_card mc
               LEFT JOIN blob b ON b.blob_id = json_extract(mc.metadata, '$.blob_id')
               WHERE mc.created_at >= ?
               ORDER BY mc.created_at DESC
               LIMIT ?""",
            (cutoff, limit),
        ).fetchall()

        recent_memories: list[dict] = []
        activity: dict[str, int] = {"new_files": 0, "new_audio": 0, "new_images": 0, "new_video": 0, "total_new": 0}

        for r in card_rows:
            meta = _meta_from_row(r)
            mid = r["memory_id"]
            blob_id = meta.get("blob_id") or (r["b_blob_id"] if "b_blob_id" in r.keys() else "")
            file_path = meta.get("file_path", "")
            mime = (r["blob_mime"] if "blob_mime" in r.keys() else None) or meta.get("mime", "")
            source_type = r["type"] or meta.get("source_type", "")

            thumb_url = ""
            media_url = ""
            if blob_id:
                media_url = f"/api/blobs/{blob_id}"
                if mime and mime.startswith("image/"):
                    thumb_url = f"/api/blobs/{blob_id}/thumb?w=320&h=320"

            open_url = f"/api/cards/{mid}/open" if (blob_id or file_path) else ""

            recent_memories.append({
                "memory_id": mid,
                "title": _card_title(r, meta),
                "summary": (r["summary"] or "")[:200],
                "mime": mime,
                "source_type": source_type,
                "created_at": r["created_at"] or "",
                "thumb_url": thumb_url,
                "media_url": media_url,
                "open_url": open_url,
            })

            # Activity counting
            activity["total_new"] += 1
            categorized = False
            if mime:
                for prefix, key in _MIME_CATEGORY.items():
                    if mime.startswith(prefix):
                        activity[key] = activity.get(key, 0) + 1
                        categorized = True
                        break
            if not categorized:
                activity["new_files"] += 1

        # ── 3. Emerging topics (entities with ≥2 mentions) ─
        ent_rows = conn.execute(
            """SELECT gn.node_id AS entity_id,
                      COALESCE(json_extract(gn.props, '$.canonical'),
                               json_extract(gn.props, '$.name'),
                               gn.node_id) AS label,
                      gn.node_type AS type,
                      COUNT(ge.edge_id) AS count_recent
               FROM graph_node gn
               JOIN graph_edge ge
                 ON (ge.from_node_id = gn.node_id OR ge.to_node_id = gn.node_id)
               WHERE gn.node_type != 'MemoryCard'
                 AND gn.created_at >= ?
               GROUP BY gn.node_id
               HAVING count_recent >= 2
               ORDER BY count_recent DESC
               LIMIT 5""",
            (cutoff,),
        ).fetchall()

        emerging_topics = [
            {
                "entity_id": r["entity_id"],
                "label": r["label"],
                "type": r["type"] or "Entity",
                "count_recent": r["count_recent"],
            }
            for r in ent_rows
        ]

        return {
            "date": datetime.now(timezone.utc).strftime("%A, %B %d"),
            "window": window,
            "generated_at": now_iso,
            "reminders": [
                {**r, "overdue": bool(r.get("due") and r["due"] <= now_str)}
                for r in reminders
            ],
            "recent_memories": recent_memories,
            "emerging_topics": [
                {"entity": e["label"], "type": e["type"], "count_recent": e["count_recent"]}
                for e in emerging_topics
            ],
            "activity_summary": {
                "total": activity["total_new"],
                "images": activity.get("new_images", 0),
                "audio": activity.get("new_audio", 0),
                "video": activity.get("new_video", 0),
                "files": activity.get("new_files", 0),
            },
            # backward-compat aliases
            "recent_cards": recent_memories,
            "top_entities": [{"canonical": e["label"], "type": e["type"], "count": e["count_recent"]} for e in emerging_topics],
            "actions": reminders,
            "suggested_clusters": [],
        }
    finally:
        conn.close()


# Keep old endpoint as alias
@router.get("/digest")
async def digest_compat(
    window: str = Query("24h", pattern="^(24h|7d|30d)$"),
    limit: int = Query(50, ge=1, le=200),
):
    """Backward-compatible digest (delegates to /feed/today)."""
    return await feed_today(window=window, limit=min(limit, 50))
