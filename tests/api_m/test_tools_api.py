import os

from tests.test_support import ApiTestCase


class ToolsApiTests(ApiTestCase):
    def _create_chat(self, title="Command chat", project_id=None):
        profile = self.db.profiles.get_default()
        return self.db.conversations.create(
            title=title,
            project_id=project_id,
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )

    def test_tools_endpoint_lists_builtin_catalog(self):
        response = self.client.get("/api/tools", headers=self.auth_headers)
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("tools", payload)
        self.assertEqual(
            {tool["name"] for tool in payload["tools"]},
            {"current_date", "web_search"},
        )
        self.assertEqual(
            {tool["display_name"] for tool in payload["tools"]},
            {"current date", "web search"},
        )

    def test_tools_endpoint_blocks_custom_upload_by_default(self):
        response = self.client.post(
            "/api/tools",
            json={
                "filename": "echo_tool.py",
                "source": """
TOOL_NAME = "echo_tool"
TOOL_RISK_LEVEL = "read_only"
TOOL_DESCRIPTION = "Echoes a value."
TOOL_PARAMETERS = {"value": {"type": "string"}}

def run(arguments):
    return {"echo": arguments.get("value", "")}
""".strip(),
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"]["code"], "bad_request")
        self.assertIn("Custom tools are disabled", payload["error"]["message"])

    def test_tools_endpoint_can_upload_and_activate_tool(self):
        os.environ["ENABLE_CUSTOM_TOOLS"] = "1"
        create_response = self.client.post(
            "/api/tools",
            json={
                "filename": "echo_tool.py",
                "source": """
TOOL_NAME = "echo_tool"
TOOL_DISPLAY_NAME = "Echo Tool"
TOOL_RISK_LEVEL = "read_only"
TOOL_DESCRIPTION = "Echoes a value."
TOOL_PARAMETERS = {"value": {"type": "string"}}

def run(arguments):
    return {"echo": arguments.get("value", "")}
""".strip(),
            },
            headers=self.auth_headers,
        )
        created_tool = create_response.get_json()["tool"]

        update_response = self.client.patch(
            "/api/tools",
            json={
                "id": created_tool["id"],
                "is_active": True,
            },
            headers=self.auth_headers,
        )
        updated_tool = update_response.get_json()["tool"]

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(created_tool["name"], "echo_tool")
        self.assertEqual(created_tool["display_name"], "Echo Tool")
        self.assertEqual(update_response.status_code, 200)
        self.assertTrue(updated_tool["is_active"])

    def test_tools_endpoint_can_toggle_workspace_runtime_tools(self):
        list_response = self.client.get("/api/tools", headers=self.auth_headers)
        listed_tool = next(
            tool
            for tool in list_response.get_json()["workspace_tools"]
            if tool["name"] == "workspace_search"
        )

        update_response = self.client.patch(
            "/api/tools",
            json={
                "id": listed_tool["id"],
                "is_active": False,
            },
            headers=self.auth_headers,
        )
        payload = update_response.get_json()
        refresh_response = self.client.get("/api/tools", headers=self.auth_headers)
        refreshed_tool = next(
            tool
            for tool in refresh_response.get_json()["workspace_tools"]
            if tool["name"] == "workspace_search"
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertFalse(payload["tool"]["is_active"])
        self.assertFalse(refreshed_tool["is_active"])

    def test_tools_endpoint_requires_custom_tool_risk_level(self):
        os.environ["ENABLE_CUSTOM_TOOLS"] = "1"
        response = self.client.post(
            "/api/tools",
            json={
                "filename": "missing_risk.py",
                "source": """
TOOL_NAME = "missing_risk"
TOOL_DESCRIPTION = "Missing risk."
TOOL_PARAMETERS = {}

def run(arguments):
    return {}
""".strip(),
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertIn("TOOL_RISK_LEVEL", payload["error"]["message"])

    def test_tools_endpoint_rejects_blocked_custom_imports(self):
        os.environ["ENABLE_CUSTOM_TOOLS"] = "1"
        response = self.client.post(
            "/api/tools",
            json={
                "filename": "shell_tool.py",
                "source": """
import subprocess

TOOL_NAME = "shell_tool"
TOOL_RISK_LEVEL = "runs_command"
TOOL_DESCRIPTION = "Runs a command."
TOOL_PARAMETERS = {}

def run(arguments):
    return {}
""".strip(),
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertIn("subprocess", payload["error"]["message"])

    def test_chat_endpoint_runs_active_tool_calls(self):
        os.environ["ENABLE_CUSTOM_TOOLS"] = "1"
        create_response = self.client.post(
            "/api/tools",
            json={
                "filename": "current_date_override.py",
                "source": """
TOOL_NAME = "current_date_override"
TOOL_RISK_LEVEL = "read_only"
TOOL_DESCRIPTION = "Returns a deterministic date for tests."
TOOL_PARAMETERS = {}

def run(arguments):
    return {"date": "2026-05-12", "timezone": "Europe/Madrid"}
""".strip(),
            },
            headers=self.auth_headers,
        )
        tool_id = create_response.get_json()["tool"]["id"]
        self.client.patch(
            "/api/tools",
            json={"id": tool_id, "is_active": True},
            headers=self.auth_headers,
        )

        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Tool chat",
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )

        model_calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            model_calls["count"] += 1
            if model_calls["count"] == 1:
                self.assertEqual(messages[0]["role"], "system")
                self.assertIn("current_date_override", messages[0]["content"])
                return {
                    "provider": provider,
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
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "The current date is 2026-05-12.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-tool-api-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "What is the date today?"}],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(model_calls["count"], 2)
        self.assertEqual(payload["response"]["message"]["content"], "The current date is 2026-05-12.")
        self.assertEqual(
            payload["response"]["raw"]["tool_events"][0]["tool_name"],
            "current_date_override",
        )
        self.assertIn(
            "2026-05-12",
            payload["response"]["raw"]["tool_events"][0]["tool_summary"],
        )
        stored_messages = self.db.messages.for_conversation(conversation_id)
        stored_tool_event = stored_messages[-1]["tool_events"][0]
        self.assertEqual(stored_tool_event["tool_name"], "current_date_override")
        self.assertIn("2026-05-12", stored_tool_event["tool_summary"])

    def test_chat_endpoint_forces_current_date_without_tool_selection(self):
        tool = self.db.tools.get_by_name("current_date")
        self.client.patch(
            "/api/tools",
            json={"id": tool["id"], "is_active": True},
            headers=self.auth_headers,
        )
        self.api_manager.services.tool_registry._runtime_catalog["current_date"]["runner"] = (
            lambda arguments: {"date": "2026-06-22", "timezone": "Europe/Madrid"}
        )
        model_calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            model_calls["count"] += 1
            self.assertIn("Tool result for current_date", messages[-1]["content"])
            return {
                "provider": provider,
                "model": model,
                "message": {"role": "assistant", "content": "Today is 2026-06-22."},
                "usage": {},
                "finish_reason": "stop",
                "message_id": "forced-date-api",
                "raw": {},
            }

        self.model_manager.chat = fake_chat
        content = "/current_date tell me today"
        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": self._create_chat(),
                "messages": [{"role": "user", "content": content}],
                "tool_directives": [
                    {
                        "tool_name": "current_date",
                        "instruction": "tell me today",
                        "start": 0,
                        "end": len(content),
                    }
                ],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(model_calls["count"], 1)
        self.assertEqual(payload["response"]["raw"]["tool_events"][0]["tool_name"], "current_date")

    def test_chat_endpoint_forced_chain_preserves_result_dependency(self):
        for name in ("current_date", "web_search"):
            tool = self.db.tools.get_by_name(name)
            self.client.patch(
                "/api/tools",
                json={"id": tool["id"], "is_active": True},
                headers=self.auth_headers,
            )
        registry = self.api_manager.services.tool_registry._runtime_catalog
        registry["current_date"]["runner"] = lambda arguments: {"date": "2026-06-22"}
        registry["web_search"]["runner"] = lambda arguments: {
            "query": arguments["query"],
            "results": [],
        }
        calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            calls["count"] += 1
            if calls["count"] == 1:
                self.assertIn("Tool result for current_date", messages[-1]["content"])
                return {
                    "provider": provider,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"web_search","arguments":{"query":"KOI latest match 2026-06-22"}}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }
            return {
                "provider": provider,
                "model": model,
                "message": {"role": "assistant", "content": "Latest match found."},
                "usage": {},
                "finish_reason": "stop",
                "message_id": "forced-chain-api",
                "raw": {},
            }

        self.model_manager.chat = fake_chat
        content = "/current_date get today /web_search find KOI's latest match"
        split = content.index("/web_search")
        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": self._create_chat("Forced chain"),
                "messages": [{"role": "user", "content": content}],
                "tool_directives": [
                    {"tool_name": "current_date", "instruction": "get today", "start": 0, "end": split},
                    {"tool_name": "web_search", "instruction": "find KOI's latest match", "start": split, "end": len(content)},
                ],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls["count"], 2)
        self.assertEqual(
            [event["tool_name"] for event in payload["response"]["raw"]["tool_events"]],
            ["current_date", "web_search"],
        )

    def test_chat_endpoint_rejects_unknown_inactive_and_contextless_project_commands(self):
        cases = [
            ("/unknown do it", "Unknown tool command"),
            ("/current_date now", "inactive"),
            ("/workspace_search query", "connected project workspace"),
        ]
        for content, expected_error in cases:
            response = self.client.post(
                "/api/chat",
                json={
                    "conversation_id": self._create_chat(expected_error),
                    "messages": [{"role": "user", "content": content}],
                },
                headers=self.auth_headers,
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn(expected_error, response.get_json()["error"]["message"])

    def test_streaming_forced_current_date_emits_tool_events_and_persists_trace(self):
        tool = self.db.tools.get_by_name("current_date")
        self.client.patch(
            "/api/tools",
            json={"id": tool["id"], "is_active": True},
            headers=self.auth_headers,
        )
        self.api_manager.services.tool_registry._runtime_catalog["current_date"]["runner"] = (
            lambda arguments: {"date": "2026-06-22"}
        )
        self.model_manager.stream_chat = lambda *args, **kwargs: iter(
            [
                {"type": "delta", "delta": "Today is 2026-06-22."},
                {
                    "type": "response",
                    "response": {
                        "provider": "ollama",
                        "model": "qwen3",
                        "message": {"role": "assistant", "content": "Today is 2026-06-22."},
                        "usage": {},
                        "finish_reason": "stop",
                        "message_id": "forced-date-stream",
                        "raw": {},
                    },
                },
            ]
        )
        conversation_id = self._create_chat("Forced stream")
        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "/current_date now"}],
                "stream": True,
            },
            headers=self.auth_headers,
        )
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: tool_start", body)
        self.assertIn("event: tool_result", body)
        self.assertIn('"tool_name": "current_date"', body)
        self.assertEqual(
            self.db.messages.for_conversation(conversation_id)[-1]["tool_events"][0]["tool_name"],
            "current_date",
        )

    def test_streaming_forced_date_and_web_search_preserves_event_order(self):
        for name in ("current_date", "web_search"):
            tool = self.db.tools.get_by_name(name)
            self.client.patch(
                "/api/tools",
                json={"id": tool["id"], "is_active": True},
                headers=self.auth_headers,
            )
        registry = self.api_manager.services.tool_registry._runtime_catalog
        registry["current_date"]["runner"] = lambda arguments: {"date": "2026-06-22"}
        registry["web_search"]["runner"] = lambda arguments: {
            "query": arguments["query"],
            "results": [],
        }

        def fake_chat(provider, messages, model, settings):
            self.assertIn("Tool result for current_date", messages[-1]["content"])
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": '{"tool_call":{"name":"web_search","arguments":{"query":"KOI latest match 2026-06-22"}}}',
                },
                "usage": {},
                "finish_reason": None,
                "message_id": None,
                "raw": {},
            }

        self.model_manager.chat = fake_chat
        self.model_manager.stream_chat = lambda *args, **kwargs: iter(
            [
                {"type": "delta", "delta": "Found it."},
                {
                    "type": "response",
                    "response": {
                        "provider": "ollama",
                        "model": "qwen3",
                        "message": {"role": "assistant", "content": "Found it."},
                        "usage": {},
                        "finish_reason": "stop",
                        "message_id": "forced-chain-stream",
                        "raw": {},
                    },
                },
            ]
        )
        content = "/current_date get today /web_search find KOI"
        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": self._create_chat("Forced chain stream"),
                "messages": [{"role": "user", "content": content}],
                "stream": True,
            },
            headers=self.auth_headers,
        )
        body = response.get_data(as_text=True)

        self.assertLess(body.index('"tool_name": "current_date"'), body.index('"tool_name": "web_search"'))
        self.assertIn('"finish_reason": "stop"', body)

    def test_chat_endpoint_rechecks_temporal_claim_after_correction(self):
        tool = self.db.tools.get_by_name("web_search")
        self.client.patch(
            "/api/tools",
            json={"id": tool["id"], "is_active": True},
            headers=self.auth_headers,
        )

        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="KOI check",
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )

        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="when did KOI, league of legends team played last time?",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="KOI last played on November 18, 2023.",
            profile_id=profile["id"],
            profile_name=profile["name"],
        )

        runtime_tool = self.api_manager.services.tool_registry._runtime_catalog["web_search"]
        runtime_tool["runner"] = lambda arguments: {
            "query": arguments.get("query", ""),
            "results": [
                {
                    "title": "Liquipedia",
                    "url": "https://example.com/liquipedia",
                    "snippet": "Recent KOI result",
                }
            ],
            "result_count": 1,
        }

        captured = {}

        model_calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            model_calls["count"] += 1
            captured["messages"] = messages
            if model_calls["count"] == 1:
                return {
                    "provider": provider,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"web_search","arguments":{"query":"when did KOI, league of legends team played last time","max_results":5},"reason":"The previous answer needs external verification."}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }

            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "I rechecked it and found a more recent match.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-koi-recheck-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [
                    {"role": "user", "content": "when did KOI, league of legends team played last time?"},
                    {"role": "assistant", "content": "KOI last played on November 18, 2023."},
                    {"role": "user", "content": "incorrect, you didnt look it up"},
                ],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(
            payload["response"]["raw"]["tool_events"][0]["tool_name"],
            "web_search",
        )
        self.assertEqual(
            payload["response"]["raw"]["tool_events"][0]["arguments"]["query"],
            "when did KOI, league of legends team played last time",
        )

    def test_chat_endpoint_prioritizes_current_date_over_web_search_for_date_questions(self):
        date_tool = self.db.tools.get_by_name("current_date")
        search_tool = self.db.tools.get_by_name("web_search")
        self.client.patch(
            "/api/tools",
            json={"id": date_tool["id"], "is_active": True},
            headers=self.auth_headers,
        )
        self.client.patch(
            "/api/tools",
            json={"id": search_tool["id"], "is_active": True},
            headers=self.auth_headers,
        )

        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Date first",
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )

        self.api_manager.services.tool_registry._runtime_catalog["current_date"]["runner"] = (
            lambda arguments: {
                "date": "2026-05-25",
                "time": "09:45:00",
                "timezone": "Europe/Madrid",
            }
        )
        self.api_manager.services.tool_registry._runtime_catalog["web_search"]["runner"] = (
            lambda arguments: {
                "query": arguments.get("query", ""),
                "results": [],
                "result_count": 0,
            }
        )

        captured = {}

        model_calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            model_calls["count"] += 1
            captured["messages"] = messages
            if model_calls["count"] == 1:
                return {
                    "provider": provider,
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
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Today's date is 2026-05-25.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-date-priority-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "What's today's date?"}],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(
            payload["response"]["raw"]["tool_events"][0]["tool_name"],
            "current_date",
        )
