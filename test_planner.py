import asyncio
from omnimac_daemon.core.local_plan_client import OllamaPlanClient
from omnimac_daemon.core.claude_planner import build_system_prompt, PLAN_SCHEMA
from omnimac_daemon.tools.registry import ToolRegistry
from omnimac_daemon.tools.app_tools import register_app_tools

async def main():
    client = OllamaPlanClient(model="qwen3:8b", endpoint="http://127.0.0.1:11434", isolation=False)
    registry = ToolRegistry()
    register_app_tools(registry, None)
    
    system = build_system_prompt(registry)
    try:
        raw = await asyncio.to_thread(client.complete_plan, system, "open vs code", PLAN_SCHEMA)
        print("RAW OUTPUT:", raw)
    except Exception as e:
        print("ERROR:", e)

asyncio.run(main())
