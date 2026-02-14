from fastapi import APIRouter, Query

from app.db.conn import get_conn

router = APIRouter()


@router.get("/cards")
async def list_cards(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM memory_card ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
