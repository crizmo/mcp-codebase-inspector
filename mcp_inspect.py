#!/usr/bin/env python3
"""Show the raw MCP flow: initialize -> discover -> get prompt -> call tools."""
import asyncio
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server = Path(__file__).with_name("mcp_server.py")
    params = StdioServerParameters(command=sys.executable, args=[str(server)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            prompts = await session.list_prompts()
            print("PROMPTS:", [p.name for p in prompts.prompts])

            prompt = await session.get_prompt("codebase_report", {"path": "."})
            print("\nPROMPT:\n" + prompt.messages[0].content.text)

            calls = [
                ("project_summary", {"path": "."}),
                ("list_directory", {"path": "."}),
                ("search_code", {"query": "def |class ", "file_glob": "*.py"}),
            ]
            for name, args in calls:
                result = await session.call_tool(name, args)
                print(f"\n--- {name}({args}) ---\n{result.content[0].text}")


def cli():
    asyncio.run(main())


if __name__ == "__main__":
    cli()
