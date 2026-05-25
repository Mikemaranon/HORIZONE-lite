import json
import re

from .deterministic_tool_router import DeterministicToolRouter
from .model_tool_planner import ModelToolPlanner


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
        deterministic_tool_router=None,
        model_tool_planner=None,
        max_tool_round_trips=3,
    ):
        self.db = db_manager
        self.model_manager = model_manager
        self.tool_loader = tool_loader
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.workspace_tool_provider = workspace_tool_provider
        self.deterministic_tool_router = (
            deterministic_tool_router or DeterministicToolRouter()
        )
        self.model_tool_planner = model_tool_planner or ModelToolPlanner()
        self.max_tool_round_trips = max_tool_round_trips

    def list_tools(self, *, include_inactive=True, refresh=True):
        return self.tool_registry.list_tools(
            include_inactive=include_inactive,
            refresh=refresh,
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

    def set_tool_active(self, tool_id, is_active):
        tool = self.db.tools.get(tool_id)
        if not tool:
            raise LookupError("Tool not found.")

        self.db.tools.set_active(tool_id, is_active)
        return self.db.tools.get(tool_id)

    def upload_tool(self, *, filename=None, source_text=None, uploaded_file=None):
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

        forced_tool_call = self.deterministic_tool_router.resolve(messages, active_tools)
        should_use_planner = (
            not forced_tool_call
            and self.model_tool_planner.should_plan(messages, active_tools)
        )
        if not forced_tool_call and not should_use_planner:
            return self.model_manager.chat(provider_name, messages, model, settings or {})

        tool_aware_messages = self._prepare_tool_aware_messages(
            messages,
            active_tools,
            should_use_planner=should_use_planner,
        )
        tool_events = []
        response = None
        if forced_tool_call:
            self._append_tool_result_to_messages(
                tool_aware_messages,
                tool_events,
                forced_tool_call,
                active_tools=active_tools,
            )

        for _ in range(self.max_tool_round_trips + 1):
            if self._is_stop_requested(should_stop):
                return self._build_cancelled_response(provider_name, model, tool_events)

            response = self.model_manager.chat(
                provider_name,
                tool_aware_messages,
                model,
                settings or {},
            )
            tool_call = self._extract_tool_call(response)
            if not tool_call:
                return self._finalize_response(
                    response,
                    tool_events,
                    provider_name=provider_name,
                    model=model,
                )

            self._append_tool_result_to_messages(
                tool_aware_messages,
                tool_events,
                tool_call,
                active_tools=active_tools,
            )

        if response is None:
            return self._build_cancelled_response(provider_name, model, tool_events)

        tool_aware_messages.append(
            {
                "role": "user",
                "content": (
                    "Tool limit reached. Do not request more tools. "
                    "Answer the user with the information already available."
                ),
            }
        )
        final_response = self.model_manager.chat(
            provider_name,
            tool_aware_messages,
            model,
            settings or {},
        )
        return self._finalize_response(
            final_response,
            tool_events,
            provider_name=provider_name,
            model=model,
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

        forced_tool_call = self.deterministic_tool_router.resolve(messages, active_tools)
        should_use_planner = (
            not forced_tool_call
            and self.model_tool_planner.should_plan(messages, active_tools)
        )
        if not forced_tool_call and not should_use_planner:
            yield from self.model_manager.stream_chat(
                provider_name,
                messages,
                model,
                settings or {},
                should_stop=should_stop,
            )
            return

        tool_aware_messages = self._prepare_tool_aware_messages(
            messages,
            active_tools,
            should_use_planner=should_use_planner,
        )
        tool_events = []
        response = None
        if forced_tool_call:
            yield self._build_tool_start_stream_event(forced_tool_call)
            tool_event = self._append_tool_result_to_messages(
                tool_aware_messages,
                tool_events,
                forced_tool_call,
                active_tools=active_tools,
            )
            yield self._build_tool_result_stream_event(tool_event)

        for _ in range(self.max_tool_round_trips + 1):
            if self._is_stop_requested(should_stop):
                yield {
                    "type": "response",
                    "response": self._build_cancelled_response(
                        provider_name,
                        model,
                        tool_events,
                    ),
                }
                return

            response = self.model_manager.chat(
                provider_name,
                tool_aware_messages,
                model,
                settings or {},
            )
            tool_call = self._extract_tool_call(response)
            if not tool_call:
                final_response = self._finalize_response(
                    response,
                    tool_events,
                    provider_name=provider_name,
                    model=model,
                )
                content = (final_response.get("message") or {}).get("content", "")
                if content:
                    yield {
                        "type": "delta",
                        "delta": content,
                    }
                yield {
                    "type": "response",
                    "response": final_response,
                }
                return

            yield self._build_tool_start_stream_event(tool_call)
            tool_event = self._append_tool_result_to_messages(
                tool_aware_messages,
                tool_events,
                tool_call,
                active_tools=active_tools,
            )
            yield self._build_tool_result_stream_event(tool_event)

        if response is None:
            yield {
                "type": "response",
                "response": self._build_cancelled_response(provider_name, model, tool_events),
            }
            return

        tool_aware_messages.append(
            {
                "role": "user",
                "content": (
                    "Tool limit reached. Do not request more tools. "
                    "Answer the user with the information already available."
                ),
            }
        )
        final_response = self.model_manager.chat(
            provider_name,
            tool_aware_messages,
            model,
            settings or {},
        )
        final_response = self._finalize_response(
            final_response,
            tool_events,
            provider_name=provider_name,
            model=model,
        )
        content = (final_response.get("message") or {}).get("content", "")
        if content:
            yield {
                "type": "delta",
                "delta": content,
            }
        yield {
            "type": "response",
            "response": final_response,
        }

    def _prepare_tool_aware_messages(self, messages, active_tools, *, should_use_planner):
        if should_use_planner:
            return self.model_tool_planner.build_messages(messages, active_tools)
        return [*list(messages or [])]

    def _extract_tool_call(self, response):
        content = str((response.get("message") or {}).get("content", "")).strip()
        if not content:
            return None

        normalized_content = self._strip_markdown_fences(content)
        payload = self._extract_json_payload(normalized_content)
        if not isinstance(payload, dict):
            return None

        tool_call = payload.get("tool_call")
        if not isinstance(tool_call, dict):
            return None

        name = str(tool_call.get("name", "")).strip()
        arguments = tool_call.get("arguments") or {}
        if not name or not isinstance(arguments, dict):
            return None

        return {
            "name": name,
            "arguments": arguments,
        }

    def _strip_markdown_fences(self, content):
        stripped = content.strip()
        if not stripped.startswith("```"):
            return stripped

        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()

        return stripped

    def _extract_json_payload(self, content):
        try:
            payload = json.loads(content)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for index, character in enumerate(content):
            if character != "{":
                continue

            try:
                payload, _ = decoder.raw_decode(content[index:])
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                return payload

        wrapped_payload = self._extract_wrapped_tool_call(content)
        if wrapped_payload:
            return wrapped_payload

        return None

    def _extract_wrapped_tool_call(self, content):
        match = re.search(r'"tool_call"\s*:\s*(\{.*\})', content, flags=re.DOTALL)
        if not match:
            return None

        wrapped = "{" + match.group(0).strip() + "}"
        try:
            payload = json.loads(wrapped)
        except json.JSONDecodeError:
            return None

        return payload if isinstance(payload, dict) else None

    def _build_tool_result_message(self, tool_name, tool_result_payload):
        return (
            f"Tool result for {tool_name}:\n"
            f"{json.dumps(tool_result_payload, ensure_ascii=False, sort_keys=True)}\n"
            "Use this result to continue helping the user. "
            "If you still need another tool, request it using the exact JSON contract."
        )

    def _append_tool_result_to_messages(self, tool_aware_messages, tool_events, tool_call, *, active_tools=None):
        tool_event = self._execute_tool_call(tool_call, active_tools=active_tools)
        tool_events.append(tool_event)
        tool_aware_messages.extend(
            self._build_tool_exchange_messages(tool_call, tool_event)
        )
        return tool_event

    def _execute_tool_call(self, tool_call, *, active_tools=None):
        runtime_tool = self._resolve_runtime_tool(tool_call["name"], active_tools=active_tools)
        if not runtime_tool:
            tool_result_payload = {
                "ok": False,
                "error": f"Tool '{tool_call['name']}' is not available.",
            }
            return self._build_tool_event_payload(
                tool_call,
                tool_result_payload,
                runtime_tool=runtime_tool,
            )

        try:
            tool_result = self.tool_executor.execute(
                runtime_tool,
                tool_call["arguments"],
            )
            tool_result_payload = {
                "ok": True,
                "result": tool_result,
            }
        except Exception as error:
            tool_result_payload = {
                "ok": False,
                "error": str(error),
            }

        return self._build_tool_event_payload(
            tool_call,
            tool_result_payload,
            runtime_tool=runtime_tool,
        )

    def _build_tool_event_payload(self, tool_call, tool_result_payload, runtime_tool=None):
        return {
            "tool_name": tool_call["name"],
            "tool_display_name": self._resolve_tool_display_name(
                tool_call["name"],
                runtime_tool=runtime_tool,
            ),
            "arguments": tool_call["arguments"],
            **tool_result_payload,
        }

    def _build_tool_exchange_messages(self, tool_call, tool_result_payload):
        return [
            {
                "role": "assistant",
                "content": json.dumps(
                    {"tool_call": tool_call},
                    ensure_ascii=False,
                ),
            },
            {
                "role": "user",
                "content": self._build_tool_result_message(
                    tool_call["name"],
                    tool_result_payload,
                ),
            },
        ]

    def _build_tool_start_stream_event(self, tool_call):
        return {
            "type": "tool_start",
            "tool_name": tool_call["name"],
            "display_name": self._resolve_tool_display_name(tool_call["name"]),
            "arguments": tool_call["arguments"],
        }

    def _build_tool_result_stream_event(self, tool_event):
        return {
            "type": "tool_result",
            "tool_name": tool_event["tool_name"],
            "display_name": tool_event.get("tool_display_name", ""),
            "ok": bool(tool_event.get("ok")),
        }

    def _attach_tool_events(self, response, tool_events):
        if not tool_events:
            return response

        raw_response = response.get("raw") or {}
        raw_response["tool_events"] = tool_events
        response["raw"] = raw_response
        return response

    def _finalize_response(self, response, tool_events, *, provider_name, model):
        response = self._attach_tool_events(response, tool_events)
        if not tool_events or not self._extract_tool_call(response):
            return response

        fallback_response = self._build_tool_only_fallback_response(
            provider_name,
            model,
            tool_events,
        )
        if not fallback_response:
            return response

        return self._attach_tool_events(fallback_response, tool_events)

    def _build_tool_only_fallback_response(self, provider_name, model, tool_events):
        content = self._build_tool_only_fallback_content(tool_events)
        if not content:
            return None

        return {
            "provider": provider_name,
            "model": model,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "usage": {},
            "finish_reason": "stop",
            "message_id": None,
            "raw": {
                "tool_only_fallback": True,
            },
        }

    def _build_tool_only_fallback_content(self, tool_events):
        if not tool_events:
            return ""

        tool_event = tool_events[-1]
        tool_name = tool_event.get("tool_name", "")
        display_name = tool_event.get("tool_display_name") or self._resolve_tool_display_name(tool_name)

        if not tool_event.get("ok"):
            error = str(tool_event.get("error") or "The tool could not complete.")
            return f"I could not complete {display_name}: {error}"

        if tool_name == "web_search":
            result = tool_event.get("result") or {}
            query = str(tool_event.get("arguments", {}).get("query") or result.get("query") or "").strip()
            results = result.get("results") or []
            if not results:
                if query:
                    return f"I could not find relevant results on the web for \"{query}\"."
                return "I could not find relevant results on the web."

            lines = []
            if query:
                lines.append(f"I searched the web for \"{query}\". Here is the most relevant information:")
            else:
                lines.append("I searched the web. Here is the most relevant information:")

            for item in results[:5]:
                title = str(item.get("title") or "Result").strip()
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                line = f"- {title}: {url}" if url else f"- {title}"
                if snippet:
                    line = f"{line} — {snippet}"
                lines.append(line)

            return "\n".join(lines)

        if tool_name == "current_date":
            result = tool_event.get("result") or {}
            date = str(result.get("date") or "").strip()
            time = str(result.get("time") or "").strip()
            timezone = str(result.get("timezone") or "").strip()
            details = [value for value in [date, time, timezone] if value]
            if details:
                return f"Current date and time: {', '.join(details)}."
            return "I checked the current date."

        if tool_name == "workspace_write_file":
            result = tool_event.get("result") or {}
            file_payload = result.get("file") or {}
            path = str(file_payload.get("path") or "").strip()
            if path:
                action = "created" if file_payload.get("created") else "updated"
                return f"I {action} `{path}` in the connected workspace."
            return "I wrote the requested file in the connected workspace."

        if tool_name in {"workspace_read_file", "workspace_search"}:
            return f"I used {display_name} in the connected workspace."

        result = tool_event.get("result")
        if isinstance(result, dict):
            compact_fields = []
            for key, value in result.items():
                if isinstance(value, (str, int, float, bool)) and str(value).strip():
                    compact_fields.append(f"{key}: {value}")

            if compact_fields:
                return f"I used {display_name}. Result: {'; '.join(compact_fields)}"

        return f"I used {display_name} to prepare the response."

    def _resolve_tool_display_name(self, tool_name, runtime_tool=None):
        if runtime_tool and runtime_tool.get("display_name"):
            return str(runtime_tool["display_name"]).strip()

        stored_tool = self.db.tools.get_by_name(tool_name)
        if stored_tool and stored_tool.get("display_name"):
            return str(stored_tool["display_name"]).strip()

        return str(tool_name or "tool").replace("_", " ").strip()

    def _list_active_tools(self, *, tool_context=None):
        tools = self.list_active_tools()
        if self.workspace_tool_provider:
            tools = [*tools, *self.workspace_tool_provider.build_tools(tool_context)]
        return tools

    def _resolve_runtime_tool(self, tool_name, *, active_tools=None):
        for tool in active_tools or []:
            if tool.get("name") == tool_name and tool.get("runner"):
                return tool

        return self.tool_registry.get_runtime_tool(tool_name)

    def _build_cancelled_response(self, provider_name, model, tool_events):
        response = {
            "provider": provider_name,
            "model": model,
            "message": {
                "role": "assistant",
                "content": "",
            },
            "usage": {},
            "finish_reason": "cancelled",
            "message_id": None,
            "raw": {
                "cancelled": True,
            },
        }
        return self._attach_tool_events(response, tool_events)

    def _is_stop_requested(self, should_stop=None):
        return bool(should_stop and should_stop())
