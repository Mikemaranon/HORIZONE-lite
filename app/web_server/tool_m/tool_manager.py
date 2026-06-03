import os

from .tool_call_orchestrator import ToolCallOrchestrator
from .tool_call_parser import ToolCallParser
from .tool_call_policy import ToolCallPolicy
from .tool_catalog import ToolCatalog


class ToolManager:
    def __init__(
        self,
        *,
        db_manager,
        model_manager,
        tool_loader,
        tool_registry,
        tool_executor,
        workspace_tool_provider=None,
        tool_call_parser=None,
        tool_call_policy=None,
        tool_call_orchestrator=None,
        max_tool_round_trips=3,
        custom_tools_enabled=None,
    ):
        self.db = db_manager
        self.model_manager = model_manager
        self.tool_loader = tool_loader
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.workspace_tool_provider = workspace_tool_provider
        self.max_tool_round_trips = max_tool_round_trips
        self.custom_tools_enabled = custom_tools_enabled
        self.tool_call_parser = tool_call_parser or ToolCallParser()
        self.tool_call_policy = tool_call_policy or ToolCallPolicy()
        self.tool_call_orchestrator = tool_call_orchestrator or ToolCallOrchestrator(
            model_manager=self.model_manager,
            tool_executor=self.tool_executor,
            tool_call_parser=self.tool_call_parser,
            tool_call_policy=self.tool_call_policy,
            max_tool_round_trips=max_tool_round_trips,
        )

    def list_tools(self, *, include_inactive=True, refresh=True):
        return self.tool_registry.list_tools(
            include_inactive=include_inactive,
            refresh=refresh,
        )

    def list_workspace_tools(self, *, include_inactive=True):
        if not self.workspace_tool_provider:
            return []
        return self.workspace_tool_provider.list_tools(
            include_inactive=include_inactive,
        )

    def refresh_catalog(self):
        return self.tool_registry.refresh_catalog()

    def has_active_tools(self):
        return bool(self.list_active_tools())

    def list_active_tools(self):
        return self.tool_registry.list_tools(
            include_inactive=False,
            refresh=True,
        )

    def list_available_tools(self, *, tool_context=None):
        return [
            self._strip_runtime_runner(tool)
            for tool in self._list_active_tools(tool_context=tool_context)
        ]

    def build_tool_aware_messages(self, messages, *, tool_context=None):
        tools = self._list_active_tools(tool_context=tool_context)
        if not tools:
            return [*list(messages or [])]

        return ToolCatalog(tools).build_messages(messages)

    def set_tool_active(self, tool_id, is_active):
        if self._is_runtime_tool_id(tool_id):
            if not self.workspace_tool_provider:
                raise LookupError("Tool not found.")
            return self.workspace_tool_provider.set_tool_active(tool_id, is_active)

        tool = self.db.tools.get(tool_id)
        if not tool:
            raise LookupError("Tool not found.")

        self.db.tools.set_active(tool_id, is_active)
        return self.db.tools.get(tool_id)

    def upload_tool(self, *, filename=None, source_text=None, uploaded_file=None):
        if not self._custom_tools_enabled():
            raise ValueError("Custom tools are disabled. Set ENABLE_CUSTOM_TOOLS=1 to enable uploads.")

        if uploaded_file is not None:
            tool_path = self.tool_loader.save_uploaded_file(uploaded_file)
        else:
            tool_path = self.tool_loader.save_source_file(filename, source_text or "")

        try:
            descriptor = self.tool_loader.load_tool_from_path(tool_path)
            if self.db.tools.get_by_name(descriptor["name"]):
                existing_tool = self.db.tools.get_by_name(descriptor["name"])
                if existing_tool["filename"] != descriptor["filename"]:
                    raise ValueError("A tool with that TOOL_NAME already exists.")
        except Exception:
            self.tool_loader.delete_tool_file(tool_path.name)
            raise

        try:
            self.refresh_catalog()
        except Exception:
            self.tool_loader.delete_tool_file(tool_path.name)
            self.refresh_catalog()
            raise

        return self.db.tools.get_by_name(descriptor["name"])

    def chat(
        self,
        provider_name,
        messages,
        model,
        settings=None,
        should_stop=None,
        tool_context=None,
    ):
        active_tools = self._list_active_tools(tool_context=tool_context)
        if not active_tools:
            return self.model_manager.chat(provider_name, messages, model, settings or {})

        return self.tool_call_orchestrator.chat(
            provider_name,
            messages,
            model,
            settings or {},
            tool_catalog=ToolCatalog(active_tools),
            should_stop=should_stop,
            tool_context=tool_context,
        )

    def stream_chat(
        self,
        provider_name,
        messages,
        model,
        settings=None,
        should_stop=None,
        tool_context=None,
    ):
        active_tools = self._list_active_tools(tool_context=tool_context)
        if not active_tools:
            yield from self.model_manager.stream_chat(
                provider_name,
                messages,
                model,
                settings or {},
                should_stop=should_stop,
            )
            return

        yield from self.tool_call_orchestrator.stream_chat(
            provider_name,
            messages,
            model,
            settings or {},
            tool_catalog=ToolCatalog(active_tools),
            should_stop=should_stop,
            tool_context=tool_context,
        )

    def _list_active_tools(self, *, tool_context=None):
        tools = [
            self._attach_runtime_runner(tool)
            for tool in self.list_active_tools()
        ]
        if self.workspace_tool_provider:
            tools = [*tools, *self.workspace_tool_provider.build_tools(tool_context)]
        return tools

    def _attach_runtime_runner(self, tool):
        runtime_tool = self.tool_registry.get_runtime_tool(tool.get("name"), refresh=False)
        if not runtime_tool:
            return tool
        return {
            **tool,
            "runner": runtime_tool.get("runner"),
        }

    def _strip_runtime_runner(self, tool):
        sanitized_tool = dict(tool or {})
        sanitized_tool.pop("runner", None)
        return sanitized_tool

    def _is_runtime_tool_id(self, tool_id):
        return str(tool_id or "").startswith("runtime:")

    def _custom_tools_enabled(self):
        if self.custom_tools_enabled is not None:
            return bool(self.custom_tools_enabled)
        return str(os.environ.get("ENABLE_CUSTOM_TOOLS") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
