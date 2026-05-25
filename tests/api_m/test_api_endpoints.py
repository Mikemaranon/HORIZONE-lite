import io
import threading

from tests.test_support import ApiTestCase
from model_m import ProviderUnavailableError
from api_m.domains.chat_api import ChatAPI


class ApiEndpointTests(ApiTestCase):
    MODEL_ICON_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0XcAAAAASUVORK5CYII="

    def test_current_user_endpoint_returns_authenticated_user(self):
        response = self.client.get("/api/users/me", headers=self.auth_headers)
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["user"]["username"], "admin")
        self.assertEqual(payload["user"]["role"], "admin")
        self.assertNotIn("password", payload["user"])

    def test_current_user_can_update_username_and_password(self):
        response = self.client.patch(
            "/api/users/me",
            json={
                "username": "polar-admin",
                "current_password": "admin",
                "password": "new-secret",
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["user"]["username"], "polar-admin")
        self.assertNotEqual(payload["token"], self.token)
        self.assertIsNone(self.db.users.get("admin"))
        self.assertIsNotNone(self.db.users.get("polar-admin"))
        self.assertFalse(self.user_manager.validate_token(self.token))
        self.assertTrue(self.user_manager.validate_token(payload["token"]))
        self.assertTrue(self.user_manager.authenticate("polar-admin", "new-secret"))

    def test_current_user_update_requires_valid_current_password(self):
        response = self.client.patch(
            "/api/users/me",
            json={
                "username": "polar-admin",
                "current_password": "wrong-password",
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "The current password is incorrect.")
        self.assertIsNotNone(self.db.users.get("admin"))

    def test_models_endpoint_returns_configured_models(self):
        response = self.client.get("/api/models", headers=self.auth_headers)
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("models", payload)
        self.assertGreaterEqual(len(payload["models"]), 1)
        self.assertIn(payload["models"][0]["provider"], {"mlx", "ollama"})
        self.assertIn("name", payload["models"][0])
        self.assertIn("display_name", payload["models"][0])

    def test_projects_profiles_and_conversations_can_be_created(self):
        provider_response = self.client.post(
            "/api/providers",
            json={
                "name": "OpenAI Sandbox",
                "provider_type": "cloud",
                "endpoint": "https://api.openai.com/v1",
                "api_key": "test-key",
            },
            headers=self.auth_headers,
        )
        project_response = self.client.post(
            "/api/projects",
            json={"name": "Demo Project", "description": "Sandbox"},
            headers=self.auth_headers,
        )
        profile_response = self.client.post(
            "/api/profiles",
            json={
                "name": "Precise",
                "system_prompt": "Be precise.",
                "temperature": 0.1,
                "top_p": 0.9,
                "max_tokens": 512,
            },
            headers=self.auth_headers,
        )

        provider = provider_response.get_json()["provider"]
        project = project_response.get_json()["project"]
        profile = profile_response.get_json()["profile"]
        model_response = self.client.post(
            "/api/models",
            json={
                "name": "gpt-4.1",
                "display_name": "GPT-4.1 Main",
                "provider_id": provider["id"],
                "icon_image": self.MODEL_ICON_DATA_URL,
                "is_default": True,
            },
            headers=self.auth_headers,
        )
        model = model_response.get_json()["model"]

        conversation_response = self.client.post(
            "/api/conversations",
            json={
                "title": "Planning",
                "project_id": project["id"],
                "profile_id": profile["id"],
                "model_config_id": model["id"],
            },
            headers=self.auth_headers,
        )
        conversation = conversation_response.get_json()["conversation"]

        self.assertEqual(provider_response.status_code, 201)
        self.assertEqual(project_response.status_code, 201)
        self.assertEqual(profile_response.status_code, 201)
        self.assertEqual(model_response.status_code, 201)
        self.assertEqual(conversation_response.status_code, 201)
        self.assertEqual(conversation["project_id"], project["id"])
        self.assertEqual(conversation["profile_id"], profile["id"])
        self.assertEqual(conversation["provider"], "cloud")
        self.assertEqual(conversation["model_config_id"], model["id"])
        self.assertEqual(model["icon_image"], self.MODEL_ICON_DATA_URL)
        self.assertEqual(model["name"], "gpt-4.1")
        self.assertEqual(model["display_name"], "GPT-4.1 Main")

    def test_updating_model_refreshes_visible_message_label(self):
        provider = self.db.providers.get_first_by_type("ollama")
        profile = self.db.profiles.get_default()
        model_id = self.db.models.create(
            name="qwen3",
            display_name="Qwen 3",
            provider_config_id=provider["id"],
        )
        conversation_id = self.db.conversations.create(
            title="Model rename",
            profile_id=profile["id"],
            model_config_id=model_id,
            provider="ollama",
            model="qwen3",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Hello",
            model_config_id=model_id,
            model_name="Qwen 3",
            profile_id=profile["id"],
            profile_name=profile["name"],
        )

        response = self.client.patch(
            "/api/models",
            json={
                "id": model_id,
                "name": "qwen3",
                "display_name": "Qwen Work",
                "provider_id": provider["id"],
                "icon_image": "",
                "is_default": False,
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["model"]["name"], "qwen3")
        self.assertEqual(payload["model"]["display_name"], "Qwen Work")
        self.assertEqual(stored_messages[0]["model_name"], "Qwen Work")

    def test_chat_endpoint_applies_profile_and_persists_turn(self):
        profile_id = self.db.profiles.create(
            name="Creative",
            system_prompt="Answer creatively.",
            temperature=0.4,
            top_p=0.8,
            max_tokens=300,
            is_default=True,
        )
        conversation_id = self.db.conversations.create(
            title="Ideas",
            profile_id=profile_id,
            provider="openai",
            model="gpt-4.1",
        )

        captured = {}

        def fake_chat(provider, messages, model, settings):
            captured["provider"] = provider
            captured["messages"] = messages
            captured["model"] = model
            captured["settings"] = settings
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Aqui tienes ideas",
                },
                "message_id": "resp-1",
                "usage": {"completion_tokens": 12},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Dame ideas"}],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["provider"], "openai")
        self.assertEqual(captured["model"], "gpt-4.1")
        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user"],
        )
        self.assertIn("Active profile: Creative", captured["messages"][0]["content"])
        self.assertIn("Answer creatively.", captured["messages"][0]["content"])
        self.assertIn("Final rule: follow only the active profile.", captured["messages"][0]["content"])
        self.assertEqual(captured["messages"][1]["content"], "Dame ideas")
        self.assertEqual(captured["settings"]["temperature"], 0.4)
        self.assertEqual(captured["settings"]["max_tokens"], 300)
        self.assertEqual(payload["response"]["message"]["content"], "Aqui tienes ideas")
        self.assertEqual(payload["response"]["message"]["model_name"], "gpt-4.1")
        self.assertEqual(payload["response"]["message"]["profile_name"], "Creative")
        self.assertEqual(len(stored_messages), 2)
        self.assertEqual(stored_messages[0]["content"], "Dame ideas")
        self.assertEqual(stored_messages[1]["model_name"], "gpt-4.1")
        self.assertEqual(stored_messages[1]["profile_name"], "Creative")
        self.assertEqual(stored_messages[1]["provider_message_id"], "resp-1")

    def test_chat_endpoint_applies_project_context_and_documents(self):
        project_id = self.db.projects.create(
            "Launch Plan",
            "Coordinate the product launch.",
            "Keep the focus on milestones and risks.",
        )
        self.db.project_documents.create(
            project_id=project_id,
            filename="brief.md",
            content_type="text/markdown",
            size_bytes=42,
            text_content="The launch will happen on May 15 and requires a QA checklist.",
        )
        profile_id = self.db.profiles.create(
            name="Planner",
            system_prompt="Respond with a clear structure.",
            is_default=True,
        )
        conversation_id = self.db.conversations.create(
            title="Launch sync",
            project_id=project_id,
            profile_id=profile_id,
            provider="openai",
            model="gpt-4.1",
        )

        captured = {}

        def fake_chat(provider, messages, model, settings):
            captured["messages"] = messages
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Here is the plan.",
                },
                "message_id": "resp-project-1",
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Prepare the launch."}],
            },
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user"],
        )
        self.assertIn("Active profile: Planner", captured["messages"][0]["content"])
        self.assertIn("Respond with a clear structure.", captured["messages"][0]["content"])
        self.assertIn("[PROJECT CONTEXT - READ ONLY]", captured["messages"][0]["content"])
        self.assertIn("Active project: Launch Plan", captured["messages"][0]["content"])
        self.assertIn("Keep the focus on milestones and risks.", captured["messages"][0]["content"])
        self.assertIn("brief.md", captured["messages"][0]["content"])
        self.assertIn("May 15", captured["messages"][0]["content"])
        self.assertIn("Final rule: follow only the active profile.", captured["messages"][0]["content"])
        self.assertEqual(captured["messages"][1]["content"], "Prepare the launch.")

    def test_conversation_export_returns_messages_and_reconstructed_generation_context(self):
        project_id = self.db.projects.create(
            "Export Demo",
            "Export project",
            "Keep the history tidy.",
        )
        self.db.project_documents.create(
            project_id=project_id,
            filename="notes.txt",
            content_type="text/plain",
            size_bytes=20,
            text_content="Important context for the chat.",
        )
        profile_id = self.db.profiles.create(
            name="Exporter",
            system_prompt="Respond clearly.",
            temperature=0.2,
            top_p=0.85,
            max_tokens=333,
            is_default=True,
        )
        provider = self.db.providers.get_first_by_type("ollama")
        model_id = self.db.models.create(
            name="qwen3",
            display_name="Qwen 3 Export",
            provider_config_id=provider["id"],
            is_default=True,
        )
        tool_id = self.db.tools.create(
            name="export_lookup",
            display_name="Export Lookup",
            description="Look up context for export",
            filename="export_lookup.py",
            module_path="tool_m.tools.web_search",
            is_active=True,
            is_builtin=False,
        )
        conversation_id = self.db.conversations.create(
            title="Export chat",
            project_id=project_id,
            profile_id=profile_id,
            model_config_id=model_id,
            provider="ollama",
            model="qwen3",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="I need a summary.",
            position=0,
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Here is the summary.",
            position=1,
            model_config_id=model_id,
            model_name="Qwen 3 Export",
            profile_id=profile_id,
            profile_name="Exporter",
            tool_events=[
                {
                    "tool_name": "web_search",
                    "sources": ["https://example.com/source"],
                }
            ],
            provider_message_id="msg-123",
        )

        response = self.client.get(
            f"/api/conversations/export?id={conversation_id}",
            headers=self.auth_headers,
        )
        payload = response.get_json()["export"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["conversation"]["id"], conversation_id)
        self.assertEqual(payload["summary"]["message_count"], 2)
        self.assertEqual(payload["summary"]["tool_enabled_count"], 1)
        self.assertEqual(payload["active_tools"][0]["id"], tool_id)
        self.assertEqual(payload["project_documents"][0]["filename"], "notes.txt")
        self.assertEqual(payload["messages"][0]["author_label"], "You")
        self.assertEqual(payload["messages"][1]["author_label"], "Qwen 3 Export")
        self.assertEqual(payload["messages"][1]["tool_events"][0]["tool_name"], "web_search")
        self.assertEqual(payload["messages"][1]["generation"]["settings"]["temperature"], 0.2)
        self.assertEqual(
            [message["role"] for message in payload["messages"][1]["generation"]["input_messages"]],
            ["system", "user"],
        )
        self.assertIn(
            "Active profile: Exporter",
            payload["messages"][1]["generation"]["input_messages"][0]["content"],
        )
        self.assertIn(
            "Keep the history tidy.",
            payload["messages"][1]["generation"]["input_messages"][0]["content"],
        )
        self.assertEqual(
            payload["messages"][1]["generation"]["input_messages"][1]["content"],
            "I need a summary.",
        )

    def test_chat_endpoint_converts_prior_turns_into_read_only_history_context(self):
        previous_profile_id = self.db.profiles.create(
            name="Coleague",
            system_prompt="Be warm and encouraging. Use emojis.",
            is_default=False,
        )
        active_profile_id = self.db.profiles.create(
            name="Souless",
            system_prompt="Be terse. Do not use emojis or emotional language.",
            is_default=True,
        )
        conversation_id = self.db.conversations.create(
            title="Profile swap",
            profile_id=previous_profile_id,
            provider="openai",
            model="gpt-4.1",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="We shipped version 1 yesterday.",
            position=0,
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Amazing news! 🚀 Let's celebrate and plan the next step.",
            position=1,
            profile_id=previous_profile_id,
            profile_name="Coleague",
        )

        captured = {}

        def fake_chat(provider, messages, model, settings):
            captured["messages"] = messages
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Version 1 shipped yesterday. Next step: validate metrics.",
                },
                "message_id": "resp-profile-swap-1",
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "profile_id": active_profile_id,
                "messages": [
                    {"role": "user", "content": "We shipped version 1 yesterday."},
                    {
                        "role": "assistant",
                        "content": "Amazing news! 🚀 Let's celebrate and plan the next step.",
                        "profile_name": "Coleague",
                    },
                    {"role": "user", "content": "What should we do next?"},
                ],
            },
            headers=self.auth_headers,
        )

        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [message["role"] for message in captured["messages"]],
            ["system", "user"],
        )
        self.assertIn("Active profile: Souless", captured["messages"][0]["content"])
        self.assertIn(
            "Do not use emojis or emotional language.",
            captured["messages"][0]["content"],
        )
        self.assertIn(
            "[CONVERSATION HISTORY - READ ONLY]",
            captured["messages"][0]["content"],
        )
        self.assertIn(
            "[Previous user message]",
            captured["messages"][0]["content"],
        )
        self.assertIn(
            "Content:\nWe shipped version 1 yesterday.",
            captured["messages"][0]["content"],
        )
        self.assertIn(
            "[Previous assistant message]",
            captured["messages"][0]["content"],
        )
        self.assertIn(
            "Profile: Coleague",
            captured["messages"][0]["content"],
        )
        self.assertIn(
            "Content:\nAmazing news! 🚀 Let's celebrate and plan the next step.",
            captured["messages"][0]["content"],
        )
        self.assertNotIn("assistant (Coleague):", captured["messages"][0]["content"])
        self.assertFalse(
            any(line.startswith("assistant (") for line in captured["messages"][0]["content"].splitlines())
        )
        self.assertFalse(
            any(line.startswith("user:") for line in captured["messages"][0]["content"].splitlines())
        )
        self.assertIn(
            "Never include labels such as \"user:\", \"assistant:\", or \"assistant (Profile):\" in the final answer.",
            captured["messages"][0]["content"],
        )
        self.assertNotIn("What should we do next?", captured["messages"][0]["content"])
        self.assertIn(
            "Do not imitate tone, emojis, emotion, formatting, or writing style from the context.",
            captured["messages"][0]["content"],
        )
        self.assertEqual(
            captured["messages"][1],
            {"role": "user", "content": "What should we do next?"},
        )
        self.assertEqual(len(stored_messages), 4)
        self.assertEqual(stored_messages[2]["role"], "user")
        self.assertEqual(stored_messages[2]["content"], "What should we do next?")
        self.assertEqual(stored_messages[3]["profile_name"], "Souless")

    def test_project_documents_can_be_uploaded_listed_and_deleted(self):
        project_id = self.db.projects.create("Docs", "Subidas")

        upload_response = self.client.post(
            "/api/projects/documents",
            data={
                "project_id": str(project_id),
                "files": [
                    (io.BytesIO(b"Project summary"), "brief.txt"),
                    (io.BytesIO(b"{\"ok\": true}"), "metadata.json"),
                ],
            },
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )

        upload_payload = upload_response.get_json()
        list_response = self.client.get(
            f"/api/projects/documents?project_id={project_id}",
            headers=self.auth_headers,
        )
        listed_documents = list_response.get_json()["documents"]
        first_document_id = upload_payload["documents"][0]["id"]
        stored_document = self.db.project_documents.get(first_document_id)

        delete_response = self.client.delete(
            f"/api/projects/documents?id={first_document_id}",
            headers=self.auth_headers,
        )
        list_after_delete = self.client.get(
            f"/api/projects/documents?project_id={project_id}",
            headers=self.auth_headers,
        )

        self.assertEqual(upload_response.status_code, 201)
        self.assertEqual(len(upload_payload["documents"]), 2)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(listed_documents), 2)
        self.assertEqual(listed_documents[0]["filename"], "brief.txt")
        self.assertIn("Project summary", stored_document["text_content"])
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(len(list_after_delete.get_json()["documents"]), 1)

    def test_project_documents_reject_unsupported_binary_files(self):
        project_id = self.db.projects.create("Docs", "Subidas")

        response = self.client.post(
            "/api/projects/documents",
            data={
                "project_id": str(project_id),
                "files": [
                    (io.BytesIO(b"%PDF-1.4 binary"), "contract.pdf"),
                ],
            },
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not a supported text format", response.get_json()["error"])

    def test_chat_endpoint_generates_title_before_first_response(self):
        conversation_id = self.db.conversations.create(
            title="New conversation",
            provider="openai",
            model="gpt-4.1",
        )
        calls = []

        def fake_generate_title(provider, model, first_user_message, settings=None):
            calls.append(("title", provider, model, first_user_message))
            return "Quantum computing"

        def fake_chat(provider, messages, model, settings):
            calls.append(("chat", provider, model, messages[-1]["content"]))
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Quantum computing uses qubits",
                },
                "message_id": "resp-title-1",
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.generate_conversation_title = fake_generate_title
        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "Explain quantum computing to me",
                    }
                ],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()
        conversation = self.db.conversations.get(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0][0], "title")
        self.assertEqual(calls[1][0], "chat")
        self.assertEqual(calls[0][1:], ("openai", "gpt-4.1", "Explain quantum computing to me"))
        self.assertEqual(conversation["title"], "Quantum computing")
        self.assertEqual(payload["conversation"]["title"], "Quantum computing")

    def test_chat_endpoint_keeps_responding_if_title_generation_fails(self):
        conversation_id = self.db.conversations.create(
            title="New conversation",
            provider="mlx",
            model="gemma-3",
        )

        def failing_generate_title(provider, model, first_user_message, settings=None):
            raise ProviderUnavailableError("MLX offline", provider="mlx")

        def fake_chat(provider, messages, model, settings):
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "We keep responding",
                },
                "message_id": None,
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.generate_conversation_title = failing_generate_title
        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()
        conversation = self.db.conversations.get(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["response"]["message"]["content"], "We keep responding")
        self.assertEqual(conversation["title"], "New conversation")

    def test_chat_endpoint_persists_user_message_even_when_provider_fails(self):
        conversation_id = self.db.conversations.create(
            title="Broken run",
            provider="mlx",
            model="mlx-community/gemma-3-4b-it-4bit",
        )

        def failing_chat(provider, messages, model, settings):
            raise ProviderUnavailableError("MLX offline", provider="mlx")

        self.model_manager.chat = failing_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Save this"}],
            },
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 503)
        stored_messages = self.db.messages.for_conversation(conversation_id)
        self.assertEqual(len(stored_messages), 1)
        self.assertEqual(stored_messages[0]["role"], "user")
        self.assertEqual(stored_messages[0]["content"], "Save this")

    def test_chat_endpoint_persists_duplicate_user_messages_in_order(self):
        conversation_id = self.db.conversations.create(
            title="Duplicates",
            provider="mlx",
            model="mlx-community/gemma-3-4b-it-4bit",
        )

        replies = iter(["First response", "Second response"])

        def fake_chat(provider, messages, model, settings):
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": next(replies),
                },
                "message_id": None,
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        first_response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=self.auth_headers,
        )
        second_response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "First response"},
                    {"role": "user", "content": "Hello"},
                ],
            },
            headers=self.auth_headers,
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)

        stored_messages = self.db.messages.for_conversation(conversation_id)
        self.assertEqual(
            [(message["role"], message["content"]) for message in stored_messages],
            [
                ("user", "Hello"),
                ("assistant", "First response"),
                ("user", "Hello"),
                ("assistant", "Second response"),
            ],
        )

    def test_chat_endpoint_streams_and_persists_assistant_message(self):
        conversation_id = self.db.conversations.create(
            title="Streaming",
            provider="openai",
            model="gpt-4.1",
        )
        captured = {}

        def fake_stream_chat(provider, messages, model, settings, should_stop=None):
            captured["provider"] = provider
            captured["messages"] = messages
            captured["model"] = model
            captured["settings"] = settings
            yield {"type": "delta", "delta": "Hello"}
            yield {"type": "delta", "delta": " world"}
            yield {
                "type": "response",
                "response": {
                    "provider": provider,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": "Hello world",
                    },
                    "message_id": "resp-stream-1",
                    "usage": {"completion_tokens": 2},
                    "finish_reason": "stop",
                    "raw": {"streamed": True},
                },
            }

        self.model_manager.stream_chat = fake_stream_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Say hello"}],
                "stream": True,
            },
            headers=self.auth_headers,
            buffered=True,
        )

        payload = response.get_data(as_text=True)
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.content_type)
        self.assertEqual(captured["provider"], "openai")
        self.assertEqual(captured["model"], "gpt-4.1")
        self.assertIn("event: start", payload)
        self.assertIn("event: delta", payload)
        self.assertIn('"delta": "Hello"', payload)
        self.assertIn("event: end", payload)
        self.assertIn('"content": "Hello world"', payload)
        self.assertIn('"conversation"', payload)
        self.assertEqual(len(stored_messages), 2)
        self.assertEqual(stored_messages[1]["content"], "Hello world")
        self.assertEqual(stored_messages[1]["provider_message_id"], "resp-stream-1")

    def test_chat_endpoint_streams_tool_progress_before_final_response(self):
        conversation_id = self.db.conversations.create(
            title="Streaming tool progress",
            provider="ollama",
            model="qwen3",
        )
        tool = self.db.tools.get_by_name("web_search")
        self.db.tools.set_active(tool["id"], True)
        self.api_manager.services.tool_registry._runtime_catalog["web_search"]["runner"] = lambda arguments: {
            "query": arguments.get("query", ""),
            "results": [
                {
                    "title": "Breaking news",
                    "url": "https://example.com/breaking-news",
                    "snippet": "Featured news",
                }
            ],
            "result_count": 1,
        }

        self.model_manager.chat = lambda provider, messages, model, settings: {
            "provider": provider,
            "model": model,
            "message": {
                "role": "assistant",
                "content": "Here is a recent news item: https://example.com/breaking-news",
            },
            "message_id": "resp-stream-tool-1",
            "usage": {"completion_tokens": 6},
            "finish_reason": "stop",
            "raw": {},
        }

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "search for breaking news"}],
                "stream": True,
            },
            headers=self.auth_headers,
            buffered=True,
        )

        payload = response.get_data(as_text=True)
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: tool_start", payload)
        self.assertIn('"tool_name": "web_search"', payload)
        self.assertIn("event: delta", payload)
        self.assertIn("https://example.com/breaking-news", payload)
        self.assertEqual(
            stored_messages[-1]["content"],
            "Here is a recent news item: https://example.com/breaking-news",
        )

    def test_chat_endpoint_streams_error_event_when_provider_fails(self):
        conversation_id = self.db.conversations.create(
            title="Streaming broken",
            provider="mlx",
            model="mlx-community/gemma-3-4b-it-4bit",
        )

        def failing_stream_chat(provider, messages, model, settings, should_stop=None):
            raise ProviderUnavailableError("MLX offline", provider="mlx")
            yield

        self.model_manager.stream_chat = failing_stream_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Save this"}],
                "stream": True,
            },
            headers=self.auth_headers,
            buffered=True,
        )

        payload = response.get_data(as_text=True)
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: error", payload)
        self.assertIn("MLX offline", payload)
        self.assertEqual(len(stored_messages), 1)
        self.assertEqual(stored_messages[0]["content"], "Save this")

    def test_chat_cancel_endpoint_marks_active_stream(self):
        cancel_event = threading.Event()
        ChatAPI._active_streams["stream-123"] = cancel_event

        try:
            response = self.client.post(
                "/api/chat/cancel",
                json={"request_id": "stream-123"},
                headers=self.auth_headers,
            )
        finally:
            ChatAPI._active_streams.pop("stream-123", None)

        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["cancelled"])
        self.assertEqual(payload["request_id"], "stream-123")
        self.assertTrue(cancel_event.is_set())

    def test_chat_endpoint_streams_error_event_when_unexpected_exception_happens(self):
        conversation_id = self.db.conversations.create(
            title="Streaming unexpected",
            provider="mlx",
            model="mlx-community/gemma-3-4b-it-4bit",
        )

        def failing_stream_chat(provider, messages, model, settings, should_stop=None):
            raise RuntimeError("Tokenizer template exploded")
            yield

        self.model_manager.stream_chat = failing_stream_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
            headers=self.auth_headers,
            buffered=True,
        )

        payload = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: error", payload)
        self.assertIn("Tokenizer template exploded", payload)

    def test_chat_sources_follow_up_reports_no_external_sources_when_previous_answer_had_no_tools(self):
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="No sources",
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="Who played against KOI on Sunday the 10th?",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Movistar KOI played against G2 Esports.",
            profile_id=profile["id"],
            profile_name=profile["name"],
        )

        self.model_manager.stream_chat = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("stream_chat should not be called for deterministic source attribution")
        )

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [
                    {"role": "user", "content": "Who played against KOI on Sunday the 10th?"},
                    {"role": "assistant", "content": "Movistar KOI played against G2 Esports."},
                    {"role": "user", "content": "which sources did you use?"},
                ],
                "stream": True,
            },
            headers=self.auth_headers,
            buffered=True,
        )

        payload = response.get_data(as_text=True)
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: end", payload)
        self.assertIn("I did not consult external sources in the previous response.", payload)
        self.assertEqual(stored_messages[-1]["tool_events"], [])

    def test_chat_sources_follow_up_returns_sources_from_previous_tool_events(self):
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Real sources",
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="Look up the matches from Sunday the 10th.",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Movistar KOI played against G2 Esports.",
            profile_id=profile["id"],
            profile_name=profile["name"],
            tool_events=[
                {
                    "tool_name": "web_search",
                    "arguments": {"query": "Movistar KOI Sunday May 10 match"},
                    "ok": True,
                    "result": {
                        "results": [
                            {
                                "title": "Schedule",
                                "url": "https://example.com/schedule",
                            },
                            {
                                "title": "Match recap",
                                "url": "https://example.com/recap",
                            },
                        ]
                    },
                }
            ],
        )

        self.model_manager.stream_chat = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("stream_chat should not be called for deterministic source attribution")
        )

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [
                    {"role": "user", "content": "Look up the matches from Sunday the 10th."},
                    {"role": "assistant", "content": "Movistar KOI played against G2 Esports."},
                    {"role": "user", "content": "tell me the sources consulted"},
                ],
                "stream": True,
            },
            headers=self.auth_headers,
            buffered=True,
        )

        payload = response.get_data(as_text=True)
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("The sources consulted in the previous response are:", payload)
        self.assertIn("Schedule", payload)
        self.assertIn("example.com", payload)
        self.assertEqual(
            stored_messages[-1]["tool_events"][0]["tool_name"],
            "web_search",
        )

    def test_settings_endpoint_persists_api_key(self):
        write_response = self.client.post(
            "/api/settings",
            json={"key": "openai_api_key", "value": "sk-test"},
            headers=self.auth_headers,
        )
        read_response = self.client.get(
            "/api/settings?key=openai_api_key",
            headers=self.auth_headers,
        )

        self.assertEqual(write_response.status_code, 201)
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.get_json()["setting"]["value"], "sk-test")

    def test_profile_can_be_updated(self):
        profile_id = self.db.profiles.create(
            name="Research",
            system_prompt="Think step by step.",
            temperature=0.3,
            top_p=0.9,
            max_tokens=900,
        )

        response = self.client.patch(
            "/api/profiles",
            json={
                "id": profile_id,
                "name": "Research Pro",
                "personality": "Clear and technical",
                "tags": ["code", "review"],
                "system_prompt": "Be structured and concise.",
                "temperature": 0.5,
                "top_p": 0.8,
                "max_tokens": 1200,
                "is_default": True,
            },
            headers=self.auth_headers,
        )
        profile = self.db.profiles.get(profile_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["profile"]["name"], "Research Pro")
        self.assertEqual(response.get_json()["profile"]["personality"], "Clear and technical")
        self.assertEqual(profile["system_prompt"], "Be structured and concise.")
        self.assertEqual(profile["tags"], ["code", "review"])
        self.assertEqual(profile["temperature"], 0.5)
        self.assertTrue(profile["is_default"])

    def test_profile_allows_up_to_ten_tags(self):
        response = self.client.post(
            "/api/profiles",
            json={
                "name": "Dense profile",
                "tags": [
                    "analysis",
                    "docs",
                    "frontend",
                    "backend",
                    "testing",
                    "ux",
                    "local",
                    "cloud",
                    "agents",
                    "python",
                ],
            },
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.get_json()["profile"]["tags"]), 10)

    def test_profile_rejects_more_than_ten_tags(self):
        response = self.client.post(
            "/api/profiles",
            json={
                "name": "Too many",
                "tags": [
                    "one",
                    "two",
                    "three",
                    "four",
                    "five",
                    "six",
                    "seven",
                    "eight",
                    "nine",
                    "ten",
                    "eleven",
                ],
            },
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("maximum of 10", response.get_json()["error"])

    def test_profile_can_be_deleted(self):
        profile_id = self.db.profiles.create(
            name="Temporary Profile",
            personality="Brief",
            tags=["tmp"],
        )

        response = self.client.delete(
            f"/api/profiles?id={profile_id}",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["deleted"])
        self.assertIsNone(self.db.profiles.get(profile_id))

    def test_last_profile_cannot_be_deleted(self):
        default_profile = self.db.profiles.get_default()

        response = self.client.delete(
            f"/api/profiles?id={default_profile['id']}",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("last profile", response.get_json()["error"])

    def test_conversation_can_be_deleted(self):
        conversation_id = self.db.conversations.create(
            title="Temporary",
            provider="mlx",
            model="gemma-3",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="Delete this",
        )

        response = self.client.delete(
            f"/api/conversations?id={conversation_id}",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["deleted"])
        self.assertIsNone(self.db.conversations.get(conversation_id))
        self.assertEqual(self.db.messages.for_conversation(conversation_id), [])

    def test_conversation_profile_can_be_updated(self):
        profile_id = self.db.profiles.create(name="Research")
        conversation_id = self.db.conversations.create(
            title="Temporary",
            provider="mlx",
            model="gemma-3",
        )

        response = self.client.patch(
            "/api/conversations",
            json={"id": conversation_id, "profile_id": profile_id},
            headers=self.auth_headers,
        )
        conversation = self.db.conversations.get(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["conversation"]["profile_id"], profile_id)
        self.assertEqual(conversation["profile_id"], profile_id)

    def test_project_can_be_deleted_without_deleting_chats(self):
        project_id = self.db.projects.create("Temporary Project", "Delete me")
        conversation_id = self.db.conversations.create(
            title="Keep chat",
            project_id=project_id,
            provider="mlx",
            model="gemma-3",
        )

        response = self.client.delete(
            f"/api/projects?id={project_id}",
            headers=self.auth_headers,
        )
        conversation = self.db.conversations.get(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["deleted"])
        self.assertIsNone(self.db.projects.get(project_id))
        self.assertIsNotNone(conversation)
        self.assertIsNone(conversation["project_id"])

    def test_endpoints_require_authentication(self):
        response = self.client.get("/api/projects")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Unauthorized")
