"""Global tool registry — register agents, list metadata, resolve by name."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.base import BasePassiveAgent


@dataclass
class ToolEntry:
    name: str
    version: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    agent_factory: Callable[[], "BasePassiveAgent"] | None = None


class ToolRegistry:
    """Simple in-process tool registry."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def register(
        self,
        name: str,
        version: str,
        description: str,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        agent_factory: Callable[[], "BasePassiveAgent"] | None = None,
    ) -> None:
        self._tools[name] = ToolEntry(
            name=name,
            version=version,
            description=description,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            agent_factory=agent_factory,
        )

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": t.name, "version": t.version, "description": t.description}
            for t in self._tools.values()
        ]

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def schema(self, name: str) -> dict[str, Any] | None:
        entry = self._tools.get(name)
        if entry is None:
            return None
        return {
            "tool": entry.name,
            "version": entry.version,
            "input_schema": entry.input_schema,
            "output_schema": entry.output_schema,
        }


# Global singleton
registry = ToolRegistry()
