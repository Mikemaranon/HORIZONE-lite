from pathlib import Path

from data_m import DBManager
from model_m import ModelManager
from config_m import ConfigManager
from tests.test_support import IsolatedDatabaseTestCase
from tool_m import ToolCallParser, ToolExecutor, ToolLoader, ToolManager, ToolRegistry


class ToolManagerTests(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.db = DBManager()
        self.model_manager = ModelManager(ConfigManager(), self.db)
        self.tools_dir = Path(self.temp_dir.name) / "tools"
        self.tools_dir.mkdir()
        self.loader = ToolLoader(self.tools_dir)
        self.registry = ToolRegistry(
            self.db,
            self.loader,
            default_is_active=False,
        )
        self.executor = ToolExecutor(self.db)
        self.manager = ToolManager(
            db_manager=self.db,
            model_manager=self.model_manager,
            tool_loader=self.loader,
            tool_registry=self.registry,
            tool_executor=self.executor,
        )

    def test_upload_tool_registers_catalog_entry(self):
        tool = self.manager.upload_tool(
            filename="echo_tool.py",
            source_text="""
TOOL_NAME = "echo_tool"
TOOL_DISPLAY_NAME = "Echo Tool"
TOOL_DESCRIPTION = "Echoes back the received payload."
TOOL_PARAMETERS = {"value": {"type": "string"}}

def run(arguments):
    return {"echo": arguments.get("value", "")}
""".strip(),
        )

        self.assertEqual(tool["name"], "echo_tool")
        self.assertEqual(tool["display_name"], "Echo Tool")
        self.assertEqual(tool["filename"], "echo_tool.py")
        self.assertFalse(tool["is_active"])
        self.assertTrue((self.tools_dir / "echo_tool.py").exists())

    def test_set_tool_active_updates_catalog_state(self):
        tool = self.manager.upload_tool(
            filename="echo_tool.py",
            source_text="""
TOOL_NAME = "echo_tool"
TOOL_DESCRIPTION = "Echoes back the received payload."
TOOL_PARAMETERS = {}

def run(arguments):
    return {"echo": arguments}
""".strip(),
        )

        updated_tool = self.manager.set_tool_active(tool["id"], True)

        self.assertTrue(updated_tool["is_active"])
        self.assertEqual(
            [item["name"] for item in self.manager.list_active_tools()],
            ["echo_tool"],
        )

    def test_tool_display_name_falls_back_to_readable_name(self):
        tool = self.manager.upload_tool(
            filename="echo_tool.py",
            source_text="""
TOOL_NAME = "echo_tool"
TOOL_DESCRIPTION = "Echoes back the received payload."
TOOL_PARAMETERS = {}

def run(arguments):
    return {"echo": arguments}
""".strip(),
        )

        self.assertEqual(tool["display_name"], "echo tool")

    def test_chat_executes_requested_tool_and_returns_final_response(self):
        tool = self.manager.upload_tool(
            filename="current_date_override.py",
            source_text="""
TOOL_NAME = "current_date_override"
TOOL_DESCRIPTION = "Returns a deterministic date for tests."
TOOL_PARAMETERS = {}

def run(arguments):
    return {"date": "2026-05-12", "timezone": "Europe/Madrid"}
""".strip(),
        )
        self.manager.set_tool_active(tool["id"], True)

        model_calls = {"count": 0}

        def fake_chat(provider_name, messages, model, settings):
            model_calls["count"] += 1
            if model_calls["count"] == 1:
                self.assertEqual(messages[0]["role"], "system")
                self.assertIn("current_date_override", messages[0]["content"])
                self.assertEqual(messages[1]["role"], "user")
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"current_date_override","arguments":{}}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            self.assertEqual([message["role"] for message in messages], ["system", "user", "assistant", "user"])
            self.assertIn("Tool result for current_date_override", messages[-1]["content"])
            return {
                "provider": provider_name,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Today is 2026-05-12 in Europe/Madrid.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-tool-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.manager.chat(
            "ollama",
            [{"role": "user", "content": "What day is it?"}],
            "qwen3",
            {},
        )

        self.assertEqual(model_calls["count"], 2)
        self.assertEqual(
            response["message"]["content"],
            "Today is 2026-05-12 in Europe/Madrid.",
        )
        self.assertEqual(response["raw"]["tool_events"][0]["tool_name"], "current_date_override")
        self.assertTrue(response["raw"]["tool_events"][0]["ok"])

    def test_invalid_tool_call_shape_is_recoverable(self):
        tool = self.manager.upload_tool(
            filename="echo_tool.py",
            source_text="""
TOOL_NAME = "echo_tool"
TOOL_DESCRIPTION = "Echoes a value."
TOOL_PARAMETERS = {"value": {"type": "string", "required": True}}

def run(arguments):
    return {"echo": arguments.get("value", "")}
""".strip(),
        )
        self.manager.set_tool_active(tool["id"], True)
        model_calls = {"count": 0}
        captured = {}

        def fake_chat(provider_name, messages, model, settings):
            model_calls["count"] += 1
            captured["messages"] = messages
            if model_calls["count"] == 1:
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"echo_tool","arguments":"hello"}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }
            if model_calls["count"] == 2:
                self.assertIn("Tool call was invalid", messages[-1]["content"])
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"echo_tool","arguments":{"value":"hello"},"reason":"Retry with valid arguments."}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            return {
                "provider": provider_name,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Echoed hello.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-echo-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.manager.chat(
            "ollama",
            [{"role": "user", "content": "Echo hello"}],
            "qwen3",
            {},
        )

        self.assertEqual(model_calls["count"], 3)
        self.assertIn("Tool result for echo_tool", captured["messages"][-1]["content"])
        self.assertEqual(response["raw"]["tool_events"][0]["result"]["echo"], "hello")

    def test_model_requested_web_search_executes_before_final_reply(self):
        tool = self.db.tools.get_by_name("web_search")
        self.manager.set_tool_active(tool["id"], True)
        self.registry._runtime_catalog["web_search"]["runner"] = lambda arguments: {
            "query": arguments.get("query", ""),
            "results": [
                {
                    "title": "Mikemaranon on GitHub",
                    "url": "https://github.com/Mikemaranon",
                    "snippet": "GitHub profile",
                }
            ],
            "result_count": 1,
        }

        captured = {}

        model_calls = {"count": 0}

        def fake_chat(provider_name, messages, model, settings):
            model_calls["count"] += 1
            captured["messages"] = messages
            if model_calls["count"] == 1:
                self.assertEqual(messages[0]["role"], "system")
                self.assertIn("web_search", messages[0]["content"])
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"web_search","arguments":{"query":"Mikemaranon GitHub profile","max_results":5},"reason":"The user asks for web-backed information."}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            return {
                "provider": provider_name,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "I found the profile https://github.com/Mikemaranon.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-web-search-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.manager.chat(
            "ollama",
            [{"role": "user", "content": "search for Mikemaranon's GitHub profile."}],
            "qwen3",
            {},
        )

        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertIn("Tool result for web_search", captured["messages"][-1]["content"])
        self.assertEqual(response["raw"]["tool_events"][0]["tool_name"], "web_search")
        self.assertEqual(
            response["raw"]["tool_events"][0]["arguments"]["query"],
            "Mikemaranon GitHub profile",
        )
        self.assertIn("web-backed information", response["raw"]["tool_events"][0]["reason"])

    def test_chat_includes_tool_catalog_for_regular_prompts_without_forcing_tool(self):
        tool = self.db.tools.get_by_name("web_search")
        self.manager.set_tool_active(tool["id"], True)
        captured = {}
        model_calls = {"count": 0}

        def fake_chat(provider_name, messages, model, settings):
            model_calls["count"] += 1
            captured["messages"] = messages
            if model_calls["count"] == 1:
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_decision":{"needs_tool":false,"reason":"A haiku does not need external state."}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            return {
                "provider": provider_name,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Soft rain drifts over the hill.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-haiku-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.manager.chat(
            "ollama",
            [{"role": "user", "content": "Write a haiku about rain."}],
            "qwen3",
            {},
        )

        self.assertEqual(model_calls["count"], 2)
        self.assertEqual(captured["messages"][0]["role"], "system")
        self.assertIn("web_search", captured["messages"][0]["content"])
        self.assertEqual(captured["messages"][1], {"role": "user", "content": "Write a haiku about rain."})
        self.assertEqual(response["message"]["content"], "Soft rain drifts over the hill.")
        self.assertNotIn("tool_events", response.get("raw", {}))

    def test_invalid_planning_response_retry_preserves_alternating_roles(self):
        tool = self.db.tools.get_by_name("web_search")
        self.manager.set_tool_active(tool["id"], True)
        model_calls = {"count": 0}
        captured_retry_roles = []

        def fake_chat(provider_name, messages, model, settings):
            model_calls["count"] += 1
            if model_calls["count"] == 1:
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": "```c\nint main(void) { return 0; }\n```",
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            if model_calls["count"] == 2:
                captured_retry_roles.extend(message["role"] for message in messages)
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_decision":{"needs_tool":false,"reason":"No tool is needed."}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            return {
                "provider": provider_name,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Final answer.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-final",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.manager.chat(
            "ollama",
            [{"role": "user", "content": "necesito que crees un archivo snake.c"}],
            "qwen3",
            {},
        )

        self.assertEqual(captured_retry_roles, ["system", "user", "assistant", "user"])
        self.assertEqual(response["message"]["content"], "Final answer.")

    def test_time_sensitive_query_can_use_model_selected_web_search(self):
        tool = self.db.tools.get_by_name("web_search")
        self.manager.set_tool_active(tool["id"], True)
        self.registry._runtime_catalog["web_search"]["runner"] = lambda arguments: {
            "query": arguments.get("query", ""),
            "results": [
                {
                    "title": "Liquipedia",
                    "url": "https://example.com/liquipedia",
                    "snippet": "Latest KOI match page",
                }
            ],
            "result_count": 1,
        }

        captured = {}

        model_calls = {"count": 0}

        def fake_chat(provider_name, messages, model, settings):
            model_calls["count"] += 1
            captured["messages"] = messages
            if model_calls["count"] == 1:
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"web_search","arguments":{"query":"when did KOI league of legends team play last time","max_results":5},"reason":"The answer may depend on recent match data."}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            return {
                "provider": provider_name,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "KOI last played on March 10, 2024.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-koi-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.manager.chat(
            "ollama",
            [{"role": "user", "content": "when did KOI, league of legends team played last time?"}],
            "qwen3",
            {},
        )

        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(response["raw"]["tool_events"][0]["tool_name"], "web_search")
        self.assertEqual(
            response["raw"]["tool_events"][0]["arguments"]["query"],
            "when did KOI league of legends team play last time",
        )

    def test_model_can_select_current_date_when_multiple_tools_are_available(self):
        date_tool = self.db.tools.get_by_name("current_date")
        search_tool = self.db.tools.get_by_name("web_search")
        self.manager.set_tool_active(date_tool["id"], True)
        self.manager.set_tool_active(search_tool["id"], True)
        self.registry._runtime_catalog["current_date"]["runner"] = lambda arguments: {
            "date": "2026-05-25",
            "time": "09:45:00",
            "timezone": "Europe/Madrid",
        }
        self.registry._runtime_catalog["web_search"]["runner"] = lambda arguments: {
            "query": arguments.get("query", ""),
            "results": [],
            "result_count": 0,
        }

        captured = {}

        model_calls = {"count": 0}

        def fake_chat(provider_name, messages, model, settings):
            model_calls["count"] += 1
            captured["messages"] = messages
            if model_calls["count"] == 1:
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"current_date","arguments":{},"reason":"The user asks for the current date."}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            return {
                "provider": provider_name,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Today's date is 2026-05-25.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-current-date-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.manager.chat(
            "ollama",
            [{"role": "user", "content": "What's today's date?"}],
            "qwen3",
            {},
        )

        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(response["raw"]["tool_events"][0]["tool_name"], "current_date")
        self.assertEqual(
            response["raw"]["tool_events"][0]["result"]["date"],
            "2026-05-25",
        )

    def test_correction_follow_up_can_use_model_selected_web_search(self):
        tool = self.db.tools.get_by_name("web_search")
        self.manager.set_tool_active(tool["id"], True)
        self.registry._runtime_catalog["web_search"]["runner"] = lambda arguments: {
            "query": arguments.get("query", ""),
            "results": [
                {
                    "title": "Ensigame",
                    "url": "https://example.com/ensigame",
                    "snippet": "Recent KOI result",
                }
            ],
            "result_count": 1,
        }

        captured = {}

        model_calls = {"count": 0}

        def fake_chat(provider_name, messages, model, settings):
            model_calls["count"] += 1
            captured["messages"] = messages
            if model_calls["count"] == 1:
                return {
                    "provider": provider_name,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"web_search","arguments":{"query":"when did KOI, league of legends team played last time","max_results":5},"reason":"The user challenged a previous answer that needs verification."}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            return {
                "provider": provider_name,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "I looked it up and found a more recent match.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-correction-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        system_message = {
            "role": "system",
            "content": (
                "[CONVERSATION HISTORY - READ ONLY]\n"
                "[Previous user message]\n"
                "Content:\n"
                "when did KOI, league of legends team played last time?\n\n"
                "[Previous assistant message]\n"
                "Content:\n"
                "KOI last played on November 18, 2023."
            ),
        }

        response = self.manager.chat(
            "ollama",
            [system_message, {"role": "user", "content": "incorrect, you didnt look it up"}],
            "qwen3",
            {},
        )

        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(response["raw"]["tool_events"][0]["tool_name"], "web_search")
        self.assertEqual(
            response["raw"]["tool_events"][0]["arguments"]["query"],
            "when did KOI, league of legends team played last time",
        )

    def test_extract_tool_call_accepts_json_with_prefix_text(self):
        tool_call = ToolCallParser().parse_response(
            {
                "message": {
                    "content": 'JSON\n{"tool_call":{"name":"web_search","arguments":{"query":"lol stats"}}}',
                }
            }
        )

        self.assertEqual(tool_call.name, "web_search")
        self.assertEqual(tool_call.arguments, {"query": "lol stats"})

    def test_chat_falls_back_to_user_facing_tool_response_when_model_keeps_returning_tool_call(self):
        tool = self.db.tools.get_by_name("web_search")
        self.manager.set_tool_active(tool["id"], True)
        self.manager.tool_call_orchestrator.max_tool_round_trips = 0
        self.registry._runtime_catalog["web_search"]["runner"] = lambda arguments: {
            "query": arguments.get("query", ""),
            "results": [
                {
                    "title": "Breaking News",
                    "url": "https://example.com/breaking-news",
                    "snippet": "Brief summary",
                }
            ],
            "result_count": 1,
        }

        self.model_manager.chat = lambda provider_name, messages, model, settings: {
            "provider": provider_name,
            "model": model,
            "message": {
                "role": "assistant",
                "content": '{"tool_call":{"name":"web_search","arguments":{"query":"breaking news"}}}',
            },
            "usage": {},
            "finish_reason": None,
            "message_id": None,
            "raw": {},
        }

        response = self.manager.chat(
            "ollama",
            [{"role": "user", "content": "search for breaking news"}],
            "qwen3",
            {},
        )

        self.assertIn("I used web search", response["message"]["content"])
        self.assertEqual(response["raw"]["tool_events"][0]["tool_name"], "web_search")
