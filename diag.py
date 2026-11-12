import os, json, asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
async def main():
    tr = StreamableHttpTransport("https://mcp.zapier.com/api/v1/connect", headers={"Authorization": f"Bearer {os.environ['ZAPIER_MCP_TOKEN']}"})
    async with Client(tr) as c:
        tools = await c.list_tools()
        print("TOOLS:", [t.name for t in tools])
        for t in tools:
            if t.name in ("execute_zapier_write_action", "inspect_zapier_actions"):
                print(t.name, "schema props:", list((t.inputSchema or {}).get("properties", {}).keys()), "required:", (t.inputSchema or {}).get("required"))
        res = await c.call_tool("inspect_zapier_actions", {})
        txt = " ".join(getattr(x, "text", "") for x in res.content)
        print("INSPECT:", txt[:900])
asyncio.run(main())
