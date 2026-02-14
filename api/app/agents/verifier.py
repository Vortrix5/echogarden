"""VerifierAgent — stub that always returns verdict=pass."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class VerifierAgent(BasePassiveAgent):
    name = "verifier"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        return {"verdict": "pass", "issues": []}


registry.register(
    name="verifier",
    version="0.1.0",
    description="Verify an answer for factual consistency (stub).",
    input_schema={
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "context": {"type": "array"},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "verdict": {"type": "string"},
            "issues": {"type": "array"},
        },
    },
    agent_factory=VerifierAgent,
)
