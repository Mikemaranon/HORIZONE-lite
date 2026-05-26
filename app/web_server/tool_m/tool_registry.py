import json


class ToolRegistry:
    def __init__(self, db_manager, tool_loader, *, default_is_active=False):
        self.db = db_manager
        self.tool_loader = tool_loader
        self.default_is_active = bool(default_is_active)
        self._runtime_catalog = {}
        self._catalog_signature = None
        self.refresh_catalog()

    def list_tools(self, *, include_inactive=True, refresh=True):
        if refresh:
            self.ensure_fresh_catalog()

        tools = self.db.tools.all() if include_inactive else self.db.tools.active()
        return [self._merge_runtime_details(tool) for tool in tools]

    def get_runtime_tool(self, tool_name, *, refresh=True):
        if refresh:
            self.ensure_fresh_catalog()
        return self._runtime_catalog.get(tool_name)

    def ensure_fresh_catalog(self):
        current_signature = self.tool_loader.get_catalog_signature()
        if current_signature == self._catalog_signature:
            return
        self.refresh_catalog()

    def refresh_catalog(self):
        discovered_tools = self.tool_loader.load_tools()
        self._validate_unique_names(discovered_tools)

        runtime_catalog = {}
        discovered_filenames = set()

        for tool in discovered_tools:
            runtime_catalog[tool["name"]] = tool
            discovered_filenames.add(tool["filename"])
            self.db.tools.upsert_discovered(
                name=tool["name"],
                display_name=tool["display_name"],
                description=tool["description"],
                parameters=tool["parameters"],
                filename=tool["filename"],
                module_path=tool["module_path"],
                is_builtin=tool["is_builtin"],
                default_is_active=self.default_is_active,
            )

        for stored_tool in self.db.tools.all():
            if stored_tool["filename"] in discovered_filenames:
                continue
            self.db.tools.delete(stored_tool["id"])

        self._runtime_catalog = runtime_catalog
        self._catalog_signature = self.tool_loader.get_catalog_signature()
        return self.list_tools(refresh=False)

    def _validate_unique_names(self, discovered_tools):
        tool_names = {}
        for tool in discovered_tools:
            existing_file = tool_names.get(tool["name"])
            if not existing_file:
                tool_names[tool["name"]] = tool["filename"]
                continue

            details = json.dumps(
                {
                    "tool_name": tool["name"],
                    "first_filename": existing_file,
                    "second_filename": tool["filename"],
                },
                ensure_ascii=False,
            )
            raise ValueError(f"Duplicate tool name detected: {details}")

    def _merge_runtime_details(self, stored_tool):
        runtime_tool = self._runtime_catalog.get(stored_tool["name"])
        if not runtime_tool:
            return {
                **stored_tool,
                "is_available": False,
            }

        return {
            **stored_tool,
            "display_name": runtime_tool["display_name"],
            "description": runtime_tool["description"],
            "parameters": runtime_tool["parameters"],
            "capabilities": runtime_tool.get("capabilities") or [],
            "use_when": runtime_tool.get("use_when") or [],
            "risk_level": runtime_tool.get("risk_level") or "read_only",
            "module_path": runtime_tool["module_path"],
            "filename": runtime_tool["filename"],
            "is_builtin": runtime_tool["is_builtin"],
            "is_available": True,
        }
