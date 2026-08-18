import json
from omnimac_daemon.tools.registry import ToolRegistry
from omnimac_daemon.tools.app_tools import register_app_tools

registry = ToolRegistry()
register_app_tools(registry, None)
schema = registry.json_schema()
print(json.dumps(schema, indent=2))
