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

    def test_tools_endpoint_can_upload_and_activate_tool(self):
        create_response = self.client.post(
            "/api/tools",
            json={
                "filename": "echo_tool.py",
                "source": """
TOOL_NAME = "echo_tool"
TOOL_DISPLAY_NAME = "Echo Tool"
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

    def test_chat_endpoint_runs_active_tool_calls(self):
        create_response = self.client.post(
            "/api/tools",
            json={
                "filename": "current_date_override.py",
                "source": """
TOOL_NAME = "current_date_override"
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
