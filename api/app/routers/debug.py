"""Debug / visualisation router — inspect DB state, graph, Qdrant."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.db import repo as db_repo
from app.db.conn import get_conn

router = APIRouter(tags=["debug"])


# ──────────────────────────────────────────────────────────
# JSON endpoints
# ──────────────────────────────────────────────────────────

@router.get("/debug/tables")
def table_counts() -> dict[str, int]:
    """Row counts for every table."""
    db = get_conn()
    tables = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    return {t: db.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0] for t in tables}


@router.get("/debug/memory_cards")
def list_memory_cards() -> list[dict]:
    db = get_conn()
    rows = db.execute(
        "SELECT memory_id, type, summary, metadata, created_at "
        "FROM memory_card ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    out = []
    for r in rows:
        meta = json.loads(r[3]) if r[3] else {}
        out.append({
            "id": r[0],
            "card_type": r[1],
            "summary": r[2][:200] if r[2] else "",
            "metadata": meta,
            "created_at": r[4],
        })
    return out


@router.get("/debug/sources")
def list_sources() -> list[dict]:
    db = get_conn()
    rows = db.execute(
        "SELECT source_id, source_type, uri, created_ts FROM source ORDER BY created_ts DESC LIMIT 50"
    ).fetchall()
    return [{"id": r[0], "source_type": r[1], "uri": r[2], "created_at": r[3]} for r in rows]


@router.get("/debug/blobs")
def list_blobs() -> list[dict]:
    db = get_conn()
    rows = db.execute(
        "SELECT blob_id, sha256, size_bytes, path, mime, created_ts "
        "FROM blob ORDER BY created_ts DESC LIMIT 50"
    ).fetchall()
    return [
        {"id": r[0], "sha256": r[1], "size_bytes": r[2], "path": r[3], "mime": r[4], "created_at": r[5]}
        for r in rows
    ]


@router.get("/debug/embeddings")
def list_embeddings() -> list[dict]:
    db = get_conn()
    rows = db.execute(
        "SELECT embedding_id, memory_id, modality, vector_ref "
        "FROM embedding LIMIT 50"
    ).fetchall()
    return [
        {"id": r[0], "memory_id": r[1], "modality": r[2], "vector_ref": r[3]}
        for r in rows
    ]


@router.get("/debug/graph")
def get_graph() -> dict[str, Any]:
    """Return nodes + edges for visualization."""
    db = get_conn()
    nodes_raw = db.execute("SELECT node_id, node_type, props FROM graph_node").fetchall()
    edges_raw = db.execute(
        "SELECT from_node_id, to_node_id, edge_type, weight FROM graph_edge"
    ).fetchall()

    nodes = []
    for r in nodes_raw:
        props = json.loads(r[2]) if r[2] else {}
        label = props.get("label", props.get("text", r[0][:20]))
        nodes.append({"id": r[0], "label": label, "kind": r[1] or "Unknown", "meta": props})

    edges = []
    for r in edges_raw:
        edges.append({
            "source": r[0],
            "target": r[1],
            "rel_type": r[2] or "related",
            "weight": r[3] if r[3] is not None else 1.0,
        })

    return {"nodes": nodes, "edges": edges}


@router.get("/debug/tool_calls")
def list_tool_calls() -> list[dict]:
    db = get_conn()
    rows = db.execute(
        "SELECT call_id, tool_name, status, ts FROM tool_call "
        "ORDER BY ts DESC LIMIT 50"
    ).fetchall()
    return [
        {"id": r[0], "tool_name": r[1], "status": r[2], "created_at": r[3]}
        for r in rows
    ]


@router.get("/debug/exec_traces")
def list_exec_traces() -> list[dict]:
    db = get_conn()
    rows = db.execute(
        "SELECT trace_id, status, metadata_json, started_ts FROM exec_trace "
        "ORDER BY started_ts DESC LIMIT 50"
    ).fetchall()
    out = []
    for r in rows:
        meta = json.loads(r[2]) if r[2] else {}
        out.append({"id": r[0], "status": r[1], "metadata": meta, "created_at": r[3]})
    return out


@router.get("/debug/qdrant")
def qdrant_info() -> dict[str, Any]:
    """Query Qdrant for collection stats and sample points."""
    import httpx

    from app.core.config import QDRANT_URL

    result: dict[str, Any] = {}
    for coll in ("text", "vision"):
        try:
            resp = httpx.get(f"{QDRANT_URL}/collections/{coll}", timeout=5)
            if resp.status_code == 200:
                info = resp.json().get("result", {})
                # Get sample points (scroll first 5)
                scroll_resp = httpx.post(
                    f"{QDRANT_URL}/collections/{coll}/points/scroll",
                    json={"limit": 10, "with_payload": True, "with_vector": False},
                    timeout=5,
                )
                points = []
                if scroll_resp.status_code == 200:
                    pts = scroll_resp.json().get("result", {}).get("points", [])
                    for p in pts:
                        points.append({
                            "id": p.get("id"),
                            "payload": p.get("payload", {}),
                        })
                result[coll] = {
                    "status": info.get("status"),
                    "points_count": info.get("points_count", 0),
                    "vectors_count": info.get("vectors_count", 0),
                    "config": info.get("config", {}),
                    "sample_points": points,
                }
            else:
                result[coll] = {"status": "not_found"}
        except Exception as e:
            result[coll] = {"status": "error", "detail": str(e)}
    return result


# ──────────────────────────────────────────────────────────
# Visual dashboard (single HTML page)
# ──────────────────────────────────────────────────────────

@router.get("/debug", response_class=HTMLResponse)
def debug_dashboard() -> str:
    """Interactive dashboard: tables, graph visualization, Qdrant inspector."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>EchoGarden — Debug Dashboard</title>
<style>
  :root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
          --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922;
          --purple: #bc8cff; --orange: #f0883e; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); padding: 20px; }
  h1 { color: var(--accent); margin-bottom: 6px; font-size: 1.6em; }
  .subtitle { color: #8b949e; margin-bottom: 20px; font-size: 0.9em; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .card h2 { font-size: 1.1em; color: var(--accent); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
  .card h2 .badge { background: var(--border); color: var(--text); font-size: 0.75em;
                     padding: 2px 8px; border-radius: 10px; font-weight: normal; }
  .wide { grid-column: 1 / -1; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); }
  th { color: #8b949e; font-weight: 600; font-size: 0.8em; text-transform: uppercase; }
  td { word-break: break-all; }
  .mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.8em; }
  .tag { display: inline-block; padding: 1px 7px; border-radius: 4px; font-size: 0.78em; font-weight: 600; }
  .tag-ok { background: #0d2818; color: var(--green); }
  .tag-error { background: #2d1115; color: var(--red); }
  .tag-done { background: #0d2818; color: var(--green); }
  .tag-running { background: #1c1d00; color: var(--yellow); }
  .tag-kind { background: #1c1026; color: var(--purple); }
  .tag-modality { background: #1c1a0d; color: var(--orange); }
  #graph-container { width: 100%; height: 480px; background: #0d1117; border-radius: 6px; border: 1px solid var(--border); }
  .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; }
  .stat { text-align: center; }
  .stat .num { font-size: 1.8em; font-weight: bold; color: var(--accent); }
  .stat .lab { font-size: 0.78em; color: #8b949e; margin-top: 2px; }
  .refresh-btn { background: var(--accent); color: #0d1117; border: none; padding: 6px 16px;
                  border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85em; }
  .refresh-btn:hover { opacity: 0.85; }
  .loading { color: #8b949e; font-style: italic; }
  .payload { max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .payload:hover { white-space: normal; word-break: break-all; }
</style>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
</head>
<body>

<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
  <div>
    <h1>EchoGarden Debug Dashboard</h1>
    <div class="subtitle">Real-time view of SQLite tables, knowledge graph, and Qdrant vector store</div>
  </div>
  <button class="refresh-btn" onclick="loadAll()">&#8635; Refresh All</button>
</div>

<!-- Stats row -->
<div class="card" style="margin-bottom:16px;" id="stats-card">
  <div class="stat-grid" id="stats">
    <div class="loading">Loading…</div>
  </div>
</div>

<div class="grid">
  <!-- Memory Cards -->
  <div class="card">
    <h2>Memory Cards <span class="badge" id="mc-count">…</span></h2>
    <div id="mc-table" class="loading">Loading…</div>
  </div>

  <!-- Sources & Blobs -->
  <div class="card">
    <h2>Sources & Blobs <span class="badge" id="sb-count">…</span></h2>
    <div id="sb-table" class="loading">Loading…</div>
  </div>

  <!-- Embeddings -->
  <div class="card">
    <h2>Embeddings <span class="badge" id="emb-count">…</span></h2>
    <div id="emb-table" class="loading">Loading…</div>
  </div>

  <!-- Tool Calls -->
  <div class="card">
    <h2>Tool Calls <span class="badge" id="tc-count">…</span></h2>
    <div id="tc-table" class="loading">Loading…</div>
  </div>

  <!-- Exec Traces -->
  <div class="card">
    <h2>Execution Traces <span class="badge" id="et-count">…</span></h2>
    <div id="et-table" class="loading">Loading…</div>
  </div>

  <!-- Qdrant -->
  <div class="card">
    <h2>Qdrant Vector Collections</h2>
    <div id="qdrant-info" class="loading">Loading…</div>
  </div>
</div>

<!-- Knowledge Graph (full width) -->
<div class="card wide">
  <h2>Knowledge Graph <span class="badge" id="graph-count">…</span></h2>
  <div id="graph-container"></div>
</div>

<script>
const API = '';

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function tag(cls, text) { return '<span class="tag tag-' + cls + '">' + esc(text) + '</span>'; }
function short(id) { return id ? id.substring(0, 12) : '—'; }

async function loadAll() {
  const [tables, cards, sources, blobs, embeddings, graph, toolCalls, traces, qdrant] = await Promise.all([
    fetch(API + '/debug/tables').then(r => r.json()),
    fetch(API + '/debug/memory_cards').then(r => r.json()),
    fetch(API + '/debug/sources').then(r => r.json()),
    fetch(API + '/debug/blobs').then(r => r.json()),
    fetch(API + '/debug/embeddings').then(r => r.json()),
    fetch(API + '/debug/graph').then(r => r.json()),
    fetch(API + '/debug/tool_calls').then(r => r.json()),
    fetch(API + '/debug/exec_traces').then(r => r.json()),
    fetch(API + '/debug/qdrant').then(r => r.json()),
  ]);

  // Stats
  const statsHtml = Object.entries(tables).map(([t, c]) =>
    '<div class="stat"><div class="num">' + c + '</div><div class="lab">' + esc(t) + '</div></div>'
  ).join('');
  document.getElementById('stats').innerHTML = statsHtml;

  // Memory Cards
  document.getElementById('mc-count').textContent = cards.length;
  if (cards.length === 0) {
    document.getElementById('mc-table').innerHTML = '<em>No memory cards yet</em>';
  } else {
    let h = '<table><tr><th>ID</th><th>Type</th><th>Summary</th><th>Created</th></tr>';
    cards.forEach(c => {
      h += '<tr><td class="mono">' + short(c.id) + '</td><td>' + tag('kind', c.card_type) + '</td>'
        + '<td>' + esc(c.summary.substring(0, 100)) + '</td><td class="mono">' + esc((c.created_at||'').substring(0,19)) + '</td></tr>';
    });
    h += '</table>';
    document.getElementById('mc-table').innerHTML = h;
  }

  // Sources & Blobs
  document.getElementById('sb-count').textContent = sources.length + ' / ' + blobs.length;
  let sbh = '';
  if (sources.length > 0) {
    sbh += '<strong style="color:#8b949e;font-size:0.8em;">Sources</strong><table><tr><th>ID</th><th>URI</th><th>MIME</th></tr>';
    sources.forEach(s => {
      sbh += '<tr><td class="mono">' + short(s.id) + '</td><td class="mono" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;">' + esc(s.uri) + '</td><td>' + esc(s.mime) + '</td></tr>';
    });
    sbh += '</table><br/>';
  }
  if (blobs.length > 0) {
    sbh += '<strong style="color:#8b949e;font-size:0.8em;">Blobs</strong><table><tr><th>ID</th><th>SHA256</th><th>Size</th></tr>';
    blobs.forEach(b => {
      sbh += '<tr><td class="mono">' + short(b.id) + '</td><td class="mono">' + (b.sha256||'').substring(0,16) + '…</td><td>' + b.size_bytes + 'B</td></tr>';
    });
    sbh += '</table>';
  }
  document.getElementById('sb-table').innerHTML = sbh || '<em>No sources/blobs yet</em>';

  // Embeddings
  document.getElementById('emb-count').textContent = embeddings.length;
  if (embeddings.length === 0) {
    document.getElementById('emb-table').innerHTML = '<em>No embeddings yet</em>';
  } else {
    let eh = '<table><tr><th>ID</th><th>Memory</th><th>Modality</th><th>Vector Ref</th></tr>';
    embeddings.forEach(e => {
      eh += '<tr><td class="mono">' + short(e.id) + '</td><td class="mono">' + short(e.memory_id)
        + '</td><td>' + tag('modality', e.modality) + '</td><td class="mono" style="font-size:0.75em;">' + esc(e.vector_ref) + '</td></tr>';
    });
    eh += '</table>';
    document.getElementById('emb-table').innerHTML = eh;
  }

  // Tool Calls
  document.getElementById('tc-count').textContent = toolCalls.length;
  if (toolCalls.length === 0) {
    document.getElementById('tc-table').innerHTML = '<em>No tool calls yet</em>';
  } else {
    let th = '<table><tr><th>ID</th><th>Tool</th><th>Status</th><th>Time</th></tr>';
    toolCalls.forEach(t => {
      const sc = t.status === 'ok' ? 'ok' : t.status === 'error' ? 'error' : 'running';
      th += '<tr><td class="mono">' + short(t.id) + '</td><td>' + esc(t.tool_name) + '</td><td>'
        + tag(sc, t.status) + '</td><td class="mono">' + esc((t.created_at||'').substring(0,19)) + '</td></tr>';
    });
    th += '</table>';
    document.getElementById('tc-table').innerHTML = th;
  }

  // Exec Traces
  document.getElementById('et-count').textContent = traces.length;
  if (traces.length === 0) {
    document.getElementById('et-table').innerHTML = '<em>No traces yet</em>';
  } else {
    let eth = '<table><tr><th>ID</th><th>Status</th><th>Pipeline</th><th>Time</th></tr>';
    traces.forEach(t => {
      const sc = t.status === 'done' ? 'done' : t.status === 'error' ? 'error' : 'running';
      eth += '<tr><td class="mono">' + short(t.id) + '</td><td>' + tag(sc, t.status) + '</td><td>'
        + esc(t.metadata.pipeline||'?') + '</td><td class="mono">' + esc((t.created_at||'').substring(0,19)) + '</td></tr>';
    });
    eth += '</table>';
    document.getElementById('et-table').innerHTML = eth;
  }

  // Qdrant
  let qh = '';
  for (const [coll, info] of Object.entries(qdrant)) {
    qh += '<div style="margin-bottom:12px;"><strong style="color:var(--orange);">' + esc(coll) + '</strong>';
    if (info.status === 'not_found') {
      qh += ' <span class="tag tag-error">not created</span></div>';
      continue;
    }
    if (info.status === 'error') {
      qh += ' <span class="tag tag-error">error: ' + esc(info.detail) + '</span></div>';
      continue;
    }
    qh += ' — <span class="mono">' + info.points_count + ' points, ' + info.vectors_count + ' vectors</span>';
    const dim = info.config?.params?.vectors?.size || '?';
    qh += ', dim=' + dim + '</div>';
    if (info.sample_points && info.sample_points.length > 0) {
      qh += '<table><tr><th>Point ID</th><th>Payload</th></tr>';
      info.sample_points.forEach(p => {
        qh += '<tr><td class="mono">' + esc(String(p.id)) + '</td><td class="payload mono">' + esc(JSON.stringify(p.payload)) + '</td></tr>';
      });
      qh += '</table>';
    }
  }
  document.getElementById('qdrant-info').innerHTML = qh || '<em>No Qdrant data</em>';

  // Knowledge Graph (vis.js)
  renderGraph(graph);
}

const KIND_COLORS = {
  'Memory': '#58a6ff',
  'Phrase': '#3fb950',
  'Entity': '#bc8cff',
  'URL': '#f0883e',
  'Email': '#d29922',
  'Date': '#f85149',
};

function renderGraph(data) {
  document.getElementById('graph-count').textContent = data.nodes.length + ' nodes, ' + data.edges.length + ' edges';

  if (data.nodes.length === 0) {
    document.getElementById('graph-container').innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b949e;">No graph nodes yet</div>';
    return;
  }

  const nodes = data.nodes.map(n => ({
    id: n.id,
    label: n.label.length > 30 ? n.label.substring(0, 28) + '…' : n.label,
    title: n.label + '\\nKind: ' + n.kind + (n.meta.confidence ? '\\nConf: ' + n.meta.confidence : ''),
    color: {
      background: KIND_COLORS[n.kind] || '#8b949e',
      border: '#30363d',
      highlight: { background: '#ffffff', border: KIND_COLORS[n.kind] || '#8b949e' },
    },
    font: { color: '#c9d1d9', size: 12 },
    shape: n.kind === 'Memory' ? 'diamond' : 'dot',
    size: n.kind === 'Memory' ? 20 : 12 + (n.meta.confidence || 0.5) * 10,
  }));

  const edges = data.edges.map(e => ({
    from: e.source,
    to: e.target,
    label: e.rel_type,
    font: { color: '#8b949e', size: 9, strokeWidth: 0 },
    color: { color: '#30363d', highlight: '#58a6ff' },
    arrows: 'to',
    width: 1 + (e.weight || 0.5) * 2,
  }));

  const container = document.getElementById('graph-container');
  const network = new vis.Network(container, { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) }, {
    physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -40, springLength: 120 } },
    interaction: { hover: true, tooltipDelay: 100 },
    layout: { improvedLayout: true },
  });
}

// Auto-load on page open
loadAll();
</script>
</body>
</html>"""
