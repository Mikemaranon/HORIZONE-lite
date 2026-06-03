from flask import request

from api_m.domains.base_api import BaseAPI


class ToolsAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        self.tool_manager = getattr(self.services, "tool_manager", None) if self.services else None

    def register(self):
        self.app.add_url_rule("/api/tools", view_func=self.get_tools, methods=["GET"])
        self.app.add_url_rule("/api/tools", view_func=self.create_tool, methods=["POST"])
        self.app.add_url_rule("/api/tools", view_func=self.update_tool, methods=["PATCH"])
        self.app.add_url_rule("/api/tools/reload", view_func=self.reload_tools, methods=["POST"])

    def get_tools(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        if not self.tool_manager:
            return self.error("Tool manager is not available.", 503)

        raw_active_only = request.args.get("active_only")
        active_only = self._parse_bool(raw_active_only) if raw_active_only is not None else False
        return self.ok(
            {
                "tools": self.tool_manager.list_tools(
                    include_inactive=not active_only,
                    refresh=True,
                ),
                "workspace_tools": self.tool_manager.list_workspace_tools(
                    include_inactive=not active_only,
                ),
            }
        )

    def create_tool(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        if not self.tool_manager:
            return self.error("Tool manager is not available.", 503)

        try:
            if request.files.get("file"):
                tool = self.tool_manager.upload_tool(
                    uploaded_file=request.files["file"],
                )
            else:
                data = self.get_request_json(request)
                self.require_fields(data, "filename", "source")
                tool = self.tool_manager.upload_tool(
                    filename=data["filename"],
                    source_text=str(data["source"]),
                )
        except Exception as error:
            return self.error_from_exception(error)

        return self.ok({"tool": tool}, 201)

    def update_tool(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        if not self.tool_manager:
            return self.error("Tool manager is not available.", 503)

        data = self.get_request_json(request)
        try:
            self.require_fields(data, "id", "is_active")
            tool_id = self._parse_tool_id(data.get("id"))
            is_active = self._parse_bool(data.get("is_active"))
            tool = self.tool_manager.set_tool_active(tool_id, is_active)
        except (ValueError, LookupError) as error:
            return self.error_from_exception(error)

        return self.ok({"tool": tool})

    def reload_tools(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        if not self.tool_manager:
            return self.error("Tool manager is not available.", 503)

        try:
            tools = self.tool_manager.refresh_catalog()
        except ValueError as error:
            return self.error_from_exception(error)

        return self.ok({"tools": tools})

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        raise ValueError("Invalid boolean value")

    def _parse_tool_id(self, value):
        if isinstance(value, str) and value.strip().startswith("runtime:"):
            return value.strip()
        return self.parse_int(value, "id")
