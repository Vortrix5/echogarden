import httpx
from fastapi import APIRouter

from app.core.config import QDRANT_URL
from app.db.conn import get_conn

router = APIRouter()


@router.get("/healthz")
async def healthz():
    # ── SQLite check ──
    sqlite_status = "ok"
    try:
        conn = get_conn()
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        sqlite_status = "error"

    # ── Qdrant check ──
    qdrant_status = "ok"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{QDRANT_URL}/collections")
            if resp.status_code != 200:
                qdrant_status = "error"
    except Exception:
        qdrant_status = "unreachable"

    ok = sqlite_status == "ok" and qdrant_status == "ok"
    return {"ok": ok, "sqlite": sqlite_status, "qdrant": qdrant_status}
