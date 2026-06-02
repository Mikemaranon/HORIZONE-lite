import os

from tests.test_support import ApiTestCase


class ToolsApiTests(ApiTestCase):
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
        self.assertIn("Custom tools are disabled", payload["error"])

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
        self.assertIn("TOOL_RISK_LEVEL", payload["error"])

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
        self.assertIn("subprocess", payload["error"])

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
