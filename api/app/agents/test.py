from pathlib import Path
from app.core.tool_contracts import ToolEnvelope
from .doc_parse import DocParseAgent
import asyncio
import json

BASE_DIR = Path(__file__).resolve().parent
file_path = BASE_DIR / "example.pdf"


async def main():
    agent = DocParseAgent()

    envelope = ToolEnvelope(
        tool_name="doc_parse",
        callee="doc_parse",
        inputs={"text": str(file_path)},
        metadata={}
    )

    result = await agent.execute(envelope)

    # Print as formatted JSON
    print(json.dumps(result, indent=4, ensure_ascii=False))


asyncio.run(main())
