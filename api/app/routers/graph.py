"""Router: Graph API — upsert, query, expand."""

from fastapi import APIRouter

from app.graph.models import (
    ExpandRequest,
    ExpandResponse,
    QueryRequest,
    QueryResponse,
    UpsertRequest,
    UpsertResponse,
)
from app.graph.service import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])
_svc = GraphService()


@router.post("/upsert", response_model=UpsertResponse)
async def graph_upsert(req: UpsertRequest):
    """Upsert nodes and/or edges into the property graph."""
    n = _svc.upsert_nodes(req.nodes)
    e = _svc.upsert_edges(req.edges)
    return UpsertResponse(nodes_upserted=n, edges_upserted=e)


@router.post("/query", response_model=QueryResponse)
async def graph_query(req: QueryRequest):
    """Query a node and its immediate neighbors."""
    return _svc.neighbors(
        node_id=req.node_id,
        direction=req.direction,
        edge_types=req.edge_types,
        time_min=req.time_min,
        time_max=req.time_max,
        limit=req.limit,
    )


@router.post("/expand", response_model=ExpandResponse)
async def graph_expand(req: ExpandRequest):
    """BFS expand from seed nodes (1–2 hops)."""
    return _svc.expand(
        seed_node_ids=req.seed_node_ids,
        hops=req.hops,
        direction=req.direction,
        edge_types=req.edge_types,
        time_min=req.time_min,
        time_max=req.time_max,
        max_nodes=req.max_nodes,
        max_edges=req.max_edges,
    )
