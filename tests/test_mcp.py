"""Spawn the real server over stdio and call it like the agent does."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).parent.parent


async def _run(db_file):
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server.py")],
                                   env={"RECRUITING_DB": str(db_file)}, cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            roles = await session.call_tool("list_roles", {})
            bad = await session.call_tool("get_candidate_profile", {"application_id": "APP-999"})
            return tools.tools, roles, bad


def test_server_lists_five_tools_and_answers(db_file):
    tools, roles, bad = asyncio.run(_run(db_file))
    assert sorted(t.name for t in tools) == [
        "get_candidate_profile", "get_pending_tasks", "get_pipeline_funnel", "list_roles",
        "search_applications"]
    assert all(t.description and t.input_schema for t in tools)
    data = json.loads(roles.content[0].text)
    assert [r["role_id"] for r in data["roles"]] == ["R1", "R2", "R3"]
    assert bad.is_error and "No application with id" in bad.content[0].text
