"""Router: Tool Registry + Tool Execution."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.tool_contracts import ToolEnvelope, ToolResult
from app.core.tool_registry import registry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def list_tools():
    """Return all registered tools (name, version, description)."""
    return registry.list_tools()


@router.get("/{tool_name}/schema")
async def tool_schema(tool_name: str):
    """Return the JSON schema for a tool's inputs and outputs."""
    schema = registry.schema(tool_name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return schema


@router.post("/{tool_name}/run", response_model=ToolResult)
async def run_tool(tool_name: str, envelope: ToolEnvelope):
    """Execute a tool and return a ToolResult with full tracing."""
    entry = registry.get(tool_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    # Ensure callee matches the route
    envelope.callee = tool_name

    agent = entry.agent_factory()
    result = await agent.run(envelope)
    return result
