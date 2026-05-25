class WorkspaceToolProvider:
    def __init__(self, workspace_service):
        self.workspace_service = workspace_service

    def build_tools(self, context=None):
        context = context or {}
        workspace = context.get("workspace")
        if not workspace:
            return []

        workspace_id = workspace["id"]
        conversation_id = context.get("conversation_id")

        return [
            self._build_read_file_tool(workspace_id),
            self._build_search_tool(workspace_id),
            self._build_write_file_tool(workspace_id, conversation_id),
        ]

    def _build_read_file_tool(self, workspace_id):
        return {
            "id": "runtime:workspace_read_file",
            "name": "workspace_read_file",
            "display_name": "workspace read file",
            "description": "Reads a UTF-8 text file from the active project workspace using a relative path.",
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
            "is_active": True,
            "is_available": True,
            "runner": lambda arguments: self.workspace_service.read_file(
                workspace_id,
                (arguments or {}).get("path"),
            ),
        }

    def _build_search_tool(self, workspace_id):
        return {
            "id": "runtime:workspace_search",
            "name": "workspace_search",
            "display_name": "workspace search",
            "description": "Searches indexed text files in the active project workspace.",
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
            "is_active": True,
            "is_available": True,
            "runner": lambda arguments: self.workspace_service.search({
                "workspace_id": workspace_id,
                "query": (arguments or {}).get("query"),
                "limit": (arguments or {}).get("limit", 50),
            }),
        }

    def _build_write_file_tool(self, workspace_id, conversation_id):
        return {
            "id": "runtime:workspace_write_file",
            "name": "workspace_write_file",
            "display_name": "workspace write file",
            "description": (
                "Creates or replaces a UTF-8 text file in the active project workspace. "
                "Use relative paths only. Set overwrite to true only when replacing an existing file is intended."
            ),
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
            "is_active": True,
            "is_available": True,
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
        }
