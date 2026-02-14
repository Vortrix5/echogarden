"""Base class for all passive core-agents."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod

from app.core.tool_contracts import (
    ToolEnvelope,
    ToolErrorDetail,
    ToolResult,
    ToolStatus,
    utcnow_iso,
)
from app.db import repo


class BasePassiveAgent(ABC):
    """Every agent exposes *name*, *version* and an async *execute* method.
    The public ``run`` method handles:
    - DB persistence (TOOL_CALL + EXEC_NODE)
    - timeout enforcement
    - max_output_bytes enforcement
    """

    name: str
    version: str = "0.1.0"

    # ── subclass override ─────────────────────────────────
    @abstractmethod
    async def execute(self, envelope: ToolEnvelope) -> dict:
        """Return the outputs dict. Raise on error."""
        ...

    # ── public entry point ────────────────────────────────
    async def run(self, envelope: ToolEnvelope) -> ToolResult:
        call_id = uuid.uuid4().hex
        exec_node_id = uuid.uuid4().hex
        started_at = utcnow_iso()

        # Persist initial state
        full_inputs = {
            **envelope.inputs,
            "_meta": {
                "trace_id": envelope.trace_id,
                "span_id": envelope.span_id,
                "caller": envelope.caller,
                "intent": envelope.intent,
                "idempotency_key": envelope.idempotency_key,
            },
        }
        repo.insert_tool_call(call_id, self.name, full_inputs, status="running")
        repo.insert_exec_node(
            exec_node_id,
            call_id,
            state="running",
            timeout_ms=envelope.constraints.timeout_ms,
        )

        status = ToolStatus.ok
        outputs: dict = {}
        error: ToolErrorDetail | None = None

        try:
            outputs = await asyncio.wait_for(
                self.execute(envelope),
                timeout=envelope.constraints.timeout_ms / 1000.0,
            )

            # Enforce max_output_bytes
            serialized = json.dumps(outputs)
            if len(serialized.encode()) > envelope.constraints.max_output_bytes:
                outputs = {"_truncated": True, "_preview": serialized[:500]}
                status = ToolStatus.error
                error = ToolErrorDetail(
                    type="max_output_bytes_exceeded",
                    message=f"Output exceeded {envelope.constraints.max_output_bytes} bytes",
                )

        except asyncio.TimeoutError:
            status = ToolStatus.timeout
            error = ToolErrorDetail(
                type="timeout",
                message=f"Tool {self.name} exceeded {envelope.constraints.timeout_ms}ms",
            )
        except Exception as exc:
            status = ToolStatus.error
            error = ToolErrorDetail(type=type(exc).__name__, message=str(exc))

        finished_at = utcnow_iso()

        # Persist final state
        repo.update_tool_call(call_id, outputs if status == ToolStatus.ok else (outputs or None), status.value)
        repo.update_exec_node(exec_node_id, status.value)

        return ToolResult(
            trace_id=envelope.trace_id,
            span_id=envelope.span_id,
            tool_name=self.name,
            status=status,
            outputs=outputs,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_ms=_elapsed(started_at, finished_at),
        )


def _elapsed(started: str, finished: str) -> int:
    """Compute elapsed milliseconds from ISO timestamps."""
    from datetime import datetime, timezone

    t0 = datetime.fromisoformat(started)
    t1 = datetime.fromisoformat(finished)
    return max(0, int((t1 - t0).total_seconds() * 1000))
