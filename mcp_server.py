"""MCP server: registers the five tools from tools.py over stdio. No business logic here.
Never print to stdout in this process: stdout is the MCP protocol channel."""
import functools

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from tools import get_candidate_profile, get_pending_tasks, get_pipeline_funnel, list_roles, search_applications

mcp = MCPServer("recruiting")


def readable_errors(fn):
    """tools.py raises ValueError for bad input. Only ToolError text reaches the model, so convert."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    return wrapper


for fn in (list_roles, search_applications, get_candidate_profile, get_pipeline_funnel, get_pending_tasks):
    mcp.tool()(readable_errors(fn))

if __name__ == "__main__":
    mcp.run()
