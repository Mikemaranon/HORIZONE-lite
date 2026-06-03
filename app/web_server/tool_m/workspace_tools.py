class WorkspaceToolProvider:
    def __init__(self, workspace_service):
        self.workspace_service = workspace_service
        self.db = workspace_service.db

    def list_tools(self, *, include_inactive=True):
        tools = [
            self._strip_runner(tool)
            for tool in self._build_tools(workspace_id=None, conversation_id=None)
        ]
        if include_inactive:
            return tools
        return [tool for tool in tools if tool["is_active"]]

    def get_tool(self, tool_id_or_name):
        tool_name = self._normalize_tool_name(tool_id_or_name)
        for tool in self.list_tools(include_inactive=True):
            if tool["name"] == tool_name:
                return tool
        return None

    def set_tool_active(self, tool_id_or_name, is_active):
        tool = self.get_tool(tool_id_or_name)
        if not tool:
            raise LookupError("Tool not found.")

        self.db.settings.set(self._setting_key(tool["name"]), "1" if is_active else "0")
        return self.get_tool(tool["name"])

    def build_tools(self, context=None):
        context = context or {}
        workspace = context.get("workspace")
        if not workspace:
            return []

        workspace_id = workspace["id"]
        conversation_id = context.get("conversation_id")
        return [
            tool
            for tool in self._build_tools(workspace_id, conversation_id)
            if tool["is_active"]
        ]

    def _build_tools(self, workspace_id, conversation_id):
        return [
            self._build_read_file_tool(workspace_id),
            self._build_search_tool(workspace_id),
            self._build_append_file_tool(workspace_id, conversation_id),
            self._build_write_file_tool(workspace_id, conversation_id),
        ]

    def _with_active_state(self, tool):
        return {
            **tool,
            "is_active": self._is_tool_active(tool["name"]),
            "is_available": True,
        }

    def _is_tool_active(self, tool_name):
        setting = self.db.settings.get(self._setting_key(tool_name))
        if not setting:
            return True
        return str(setting.get("value") or "").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

    def _setting_key(self, tool_name):
        return f"workspace_tool_active.{tool_name}"

    def _normalize_tool_name(self, tool_id_or_name):
        value = str(tool_id_or_name or "").strip()
        if value.startswith("runtime:"):
            return value.split(":", 1)[1]
        return value

    def _strip_runner(self, tool):
        sanitized_tool = dict(tool or {})
        sanitized_tool.pop("runner", None)
        return sanitized_tool

    def _build_read_file_tool(self, workspace_id):
        return self._with_active_state({
            "id": "runtime:workspace_read_file",
            "name": "workspace_read_file",
            "display_name": "workspace read file",
            "description": "Reads a UTF-8 text file from the active project workspace using a relative path.",
            "capabilities": [
                "read exact file contents from the connected project workspace",
                "ground answers in local project files",
            ],
            "use_when": [
                "The model needs evidence from a known file before explaining or changing code.",
                "The user references a specific path in the connected workspace.",
            ],
            "risk_level": "read_only",
            "parameters": {
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "Relative file path inside the active workspace.",
                },
            },
            "filename": "runtime_workspace_tools.py",
            "module_path": "tool_m.workspace_tools",
            "is_builtin": True,
            "runner": lambda arguments: self.workspace_service.read_file(
                workspace_id,
                (arguments or {}).get("path"),
            ),
        })

    def _build_search_tool(self, workspace_id):
        return self._with_active_state({
            "id": "runtime:workspace_search",
            "name": "workspace_search",
            "display_name": "workspace search",
            "description": "Searches indexed text files in the active project workspace.",
            "capabilities": [
                "find relevant project files",
                "locate symbols, functions, text, errors, or filenames",
            ],
            "use_when": [
                "The user asks about code that may exist in the connected workspace.",
                "The model needs to discover relevant files before reading or editing.",
            ],
            "risk_level": "read_only",
            "parameters": {
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "Text to search for.",
                },
                "limit": {
                    "type": "integer",
                    "required": False,
                    "description": "Maximum number of matches to return.",
                },
            },
            "filename": "runtime_workspace_tools.py",
            "module_path": "tool_m.workspace_tools",
            "is_builtin": True,
            "runner": lambda arguments: self.workspace_service.search({
                "workspace_id": workspace_id,
                "query": (arguments or {}).get("query"),
                "limit": (arguments or {}).get("limit", 50),
            }),
        })

    def _build_write_file_tool(self, workspace_id, conversation_id):
        return self._with_active_state({
            "id": "runtime:workspace_write_file",
            "name": "workspace_write_file",
            "display_name": "workspace write file",
            "description": (
                "Creates or replaces a UTF-8 text file in the active project workspace. "
                "Use this when you have the complete desired file content. "
                "Use relative paths only. Set overwrite to true only when replacing an existing file is intended."
            ),
            "capabilities": [
                "create UTF-8 files in the connected project workspace",
                "replace existing workspace files when overwrite is explicitly true",
            ],
            "use_when": [
                "The user asks the assistant to create or update a workspace file.",
                "The model has enough file content to perform a small, controlled write.",
            ],
            "risk_level": "writes_workspace",
            "parameters": {
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "Relative file path inside the active workspace.",
                },
                "content": {
                    "type": "string",
                    "required": True,
                    "description": "Complete UTF-8 file content to write.",
                },
                "overwrite": {
                    "type": "boolean",
                    "required": False,
                    "description": "Whether to replace an existing file.",
                },
                "create_dirs": {
                    "type": "boolean",
                    "required": False,
                    "description": "Whether to create missing parent directories.",
                },
            },
            "filename": "runtime_workspace_tools.py",
            "module_path": "tool_m.workspace_tools",
            "is_builtin": True,
            "runner": lambda arguments: self.workspace_service.write_file(
                {
                    "workspace_id": workspace_id,
                    "path": (arguments or {}).get("path"),
                    "content": (arguments or {}).get("content", ""),
                    "overwrite": bool((arguments or {}).get("overwrite")),
                    "create_dirs": bool((arguments or {}).get("create_dirs")),
                },
                conversation_id=conversation_id,
            ),
        })

    def _build_append_file_tool(self, workspace_id, conversation_id):
        return self._with_active_state({
            "id": "runtime:workspace_append_file",
            "name": "workspace_append_file",
            "display_name": "workspace append file",
            "description": (
                "Appends UTF-8 text to an existing file in the active project workspace. "
                "Use relative paths only. This does not replace the existing file content."
            ),
            "capabilities": [
                "add text to the end of an existing workspace file",
                "preserve existing file content while adding a phrase, line, or block",
            ],
            "use_when": [
                "The user asks to add, append, or include text in an existing workspace file.",
                "The requested change can be safely made by adding content at the end of a file.",
            ],
            "risk_level": "writes_workspace",
            "parameters": {
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "Relative file path inside the active workspace.",
                },
                "content": {
                    "type": "string",
                    "required": True,
                    "description": "UTF-8 text to append to the file.",
                },
                "ensure_newline_before": {
                    "type": "boolean",
                    "required": False,
                    "description": "Whether to insert a newline before appended text when the file does not already end with one. Defaults to true.",
                },
                "ensure_newline_after": {
                    "type": "boolean",
                    "required": False,
                    "description": "Whether to ensure appended text ends with a newline.",
                },
            },
            "filename": "runtime_workspace_tools.py",
            "module_path": "tool_m.workspace_tools",
            "is_builtin": True,
            "runner": lambda arguments: self.workspace_service.append_file(
                {
                    "workspace_id": workspace_id,
                    "path": (arguments or {}).get("path"),
                    "content": (arguments or {}).get("content", ""),
                    "ensure_newline_before": (arguments or {}).get(
                        "ensure_newline_before",
                        True,
                    ),
                    "ensure_newline_after": (arguments or {}).get(
                        "ensure_newline_after",
                        False,
                    ),
                },
                conversation_id=conversation_id,
            ),
        })
