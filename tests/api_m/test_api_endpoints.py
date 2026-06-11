import io
import threading
from http.cookies import SimpleCookie
from pathlib import Path

from tests.test_support import ApiTestCase
from model_m import ProviderUnavailableError
from api_m.domains.chat_api import ChatAPI
from app_routes import AppRoutes


class ApiEndpointTests(ApiTestCase):
    MODEL_ICON_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0XcAAAAASUVORK5CYII="

    def test_login_sets_http_only_cookie_without_returning_token_by_default(self):
        AppRoutes(self.app, self.user_manager, self.db, self.config_manager)

        response = self.client.post(
            "/login",
            json={"username": "admin", "password": "admin"},
        )
        payload = response.get_json()
        cookie_header = response.headers.get("Set-Cookie", "")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload, {"ok": True})
        self.assertIn("token=", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=Lax", cookie_header)

    def test_private_pages_redirect_without_session(self):
        AppRoutes(self.app, self.user_manager, self.db, self.config_manager)

        response = self.client.get("/index")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_logout_clears_cookie_session(self):
        AppRoutes(self.app, self.user_manager, self.db, self.config_manager)
        login_response = self.client.post(
            "/login",
            json={"username": "admin", "password": "admin"},
        )
        token = SimpleCookie(login_response.headers.get("Set-Cookie", ""))["token"].value

        response = self.client.post("/logout")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.user_manager.validate_token(token))
        self.assertIn("token=;", response.headers.get("Set-Cookie", ""))

    def test_current_user_endpoint_returns_authenticated_user(self):
        response = self.client.get("/api/users/me", headers=self.auth_headers)
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["user"]["username"], "admin")
        self.assertEqual(payload["user"]["role"], "admin")
        self.assertTrue(payload["user"]["default_password_active"])
        self.assertNotIn("password", payload["user"])

    def test_current_user_can_update_username_and_password(self):
        response = self.client.patch(
            "/api/users/me",
            json={
                "username": "horizone-admin",
                "current_password": "admin",
                "password": "new-secret",
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()
        cookie = SimpleCookie(response.headers.get("Set-Cookie", ""))
        refreshed_token = cookie["token"].value

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["user"]["username"], "horizone-admin")
        self.assertFalse(payload["user"]["default_password_active"])
        self.assertNotIn("token", payload)
        self.assertNotEqual(refreshed_token, self.token)
        self.assertIsNone(self.db.users.get("admin"))
        self.assertIsNotNone(self.db.users.get("horizone-admin"))
        self.assertFalse(self.user_manager.validate_token(self.token))
        self.assertTrue(self.user_manager.validate_token(refreshed_token))
        self.assertTrue(self.user_manager.authenticate("horizone-admin", "new-secret"))

    def test_current_user_update_requires_valid_current_password(self):
        response = self.client.patch(
            "/api/users/me",
            json={
                "username": "horizone-admin",
                "current_password": "wrong-password",
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"]["code"], "bad_request")
        self.assertEqual(payload["error"]["message"], "The current password is incorrect.")
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

    def test_runtime_model_catalog_endpoint_returns_curated_models(self):
        response = self.client.get("/api/runtime/models/catalog", headers=self.auth_headers)
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("catalog", payload)
        self.assertGreaterEqual(len(payload["catalog"]), 1)
        self.assertEqual(payload["catalog"][0]["provider_type"], "llama_cpp")
        self.assertIn("download", payload["catalog"][0])

    def test_runtime_status_endpoint_returns_llama_cpp_port(self):
        class FakeRuntimeManager:
            def snapshot(self):
                return {
                    "status": "ready",
                    "error_message": "",
                    "base_url": "http://127.0.0.1:8081",
                    "openai_base_url": "http://127.0.0.1:8081/v1",
                    "port": 8081,
                    "port_range": {"start": 8080, "end": 9000},
                    "active_model": {"model_name": "runtime-model"},
                }

        self.app.view_functions["get_runtime_status"].__self__.runtime_manager = FakeRuntimeManager()

        response = self.client.get("/api/runtime/status", headers=self.auth_headers)
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["runtime"]["status"], "ready")
        self.assertEqual(payload["runtime"]["port"], 8081)
        self.assertEqual(payload["runtime"]["base_url"], "http://127.0.0.1:8081")
        self.assertEqual(payload["runtime"]["openai_base_url"], "http://127.0.0.1:8081/v1")
        self.assertEqual(payload["runtime"]["port_range"], {"start": 8080, "end": 9000})

    def test_runtime_model_catalog_search_endpoint_returns_matching_models(self):
        calls = []

        def fake_search(query):
            calls.append(query)
            return [
                {
                    "catalog_key": "hf-qwen",
                    "display_name": "Qwen 7B",
                    "provider_type": "llama_cpp",
                    "source_url": "https://huggingface.co/Qwen/Qwen-GGUF/resolve/main/qwen.gguf",
                    "filename": "qwen.gguf",
                    "is_installed": False,
                    "download": None,
                }
            ]

        self.api_manager.services.runtime_model_catalog_service.search_huggingface_catalog = fake_search

        response = self.client.get(
            "/api/runtime/models/catalog/search?query=qwen-7b",
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, ["qwen-7b"])
        self.assertEqual(payload["catalog"][0]["catalog_key"], "hf-qwen")

    def test_runtime_model_download_rejects_unknown_catalog_key(self):
        response = self.client.post(
            "/api/runtime/models/downloads",
            json={"catalog_key": "unknown-model"},
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_runtime_model_download_cancel_endpoint_removes_partial_file(self):
        models_dir = Path(self.temp_dir.name) / "runtime-models"
        models_dir.mkdir()
        partial_path = models_dir / "Kimi-K2.6-BF16-00001-of-00046.gguf.part"
        partial_path.write_bytes(b"partial")
        runtime_config = self.config_manager.runtime.__class__(
            **{
                **self.config_manager.runtime.__dict__,
                "runtime_models_dir": str(models_dir),
            }
        )
        self.api_manager.services.runtime_model_download_service.runtime_config = runtime_config
        download_id = self.db.runtime_model_downloads.create(
            catalog_key="kimi-runtime",
            status="downloading",
            source_url="https://example.test/Kimi-K2.6-BF16-00001-of-00046.gguf",
            filename="Kimi-K2.6-BF16-00001-of-00046.gguf",
            bytes_downloaded=7,
            total_bytes=46332327264,
        )

        response = self.client.post(
            "/api/runtime/models/downloads/cancel",
            json={"id": download_id},
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["download"]["status"], "cancelled")
        self.assertFalse(partial_path.exists())

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
        self.assertNotIn("api_key", provider)
        self.assertTrue(provider["has_api_key"])
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

    def test_provider_connection_test_endpoint_resolves_without_saving(self):
        response = self.client.post(
            "/api/providers/test",
            json={
                "provider_type": "cloud",
                "endpoint": "https://api.openai.com/v1",
                "api_key": "sk-test",
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["resolved_adapter"], "openai_compatible")

    def test_project_models_endpoint_defaults_to_system_model(self):
        project_response = self.client.post(
            "/api/projects",
            json={"name": "Model Project"},
            headers=self.auth_headers,
        )
        project = project_response.get_json()["project"]
        default_model = self.db.models.get_default()
        default_profile = self.db.profiles.get_default()

        response = self.client.get(
            f"/api/projects/models?project_id={project['id']}",
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["models"][0]["model_id"], default_model["id"])
        self.assertEqual(payload["models"][0]["profile_id"], default_profile["id"])
        self.assertEqual(payload["models"][0]["nickname"], "default")
        self.assertTrue(payload["models"][0]["is_default"])

    def test_project_models_can_be_created_updated_and_deleted(self):
        project_id = self.db.projects.create("Model Project")
        provider = self.db.providers.get_first_by_type("ollama")
        profile = self.db.profiles.get_default()
        model_id = self.db.models.create(
            name="qwen3",
            display_name="Qwen 3",
            provider_config_id=provider["id"],
        )

        create_response = self.client.post(
            "/api/projects/models",
            json={
                "project_id": project_id,
                "nickname": "coder",
                "model_id": model_id,
                "profile_id": profile["id"],
                "system_prompt": "Focus on implementation details.",
                "color": "#2563eb",
            },
            headers=self.auth_headers,
        )
        project_model = create_response.get_json()["model"]
        second_model_id = self.db.models.create(
            name="llama3",
            display_name="Llama 3",
            provider_config_id=provider["id"],
        )
        second_create_response = self.client.post(
            "/api/projects/models",
            json={
                "project_id": project_id,
                "nickname": "writer",
                "model_id": second_model_id,
                "profile_id": profile["id"],
                "is_default": True,
            },
            headers=self.auth_headers,
        )
        second_project_model = second_create_response.get_json()["model"]

        update_response = self.client.patch(
            "/api/projects/models",
            json={
                "id": project_model["id"],
                "nickname": "tester",
                "model_id": model_id,
                "profile_id": profile["id"],
                "system_prompt": "Focus on regressions.",
                "color": "#dc2626",
            },
            headers=self.auth_headers,
        )
        delete_response = self.client.delete(
            f"/api/projects/models?id={project_model['id']}",
            headers=self.auth_headers,
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(second_create_response.status_code, 201)
        self.assertEqual(project_model["nickname"], "coder")
        self.assertTrue(project_model["is_default"])
        self.assertTrue(second_project_model["is_default"])
        self.assertEqual(project_model["system_prompt"], "Focus on implementation details.")
        self.assertEqual(project_model["color"], "#2563eb")
        self.assertEqual(project_model["model"]["display_name"], "Qwen 3")
        self.assertEqual(project_model["profile"]["name"], profile["name"])
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.get_json()["model"]["nickname"], "tester")
        self.assertEqual(update_response.get_json()["model"]["system_prompt"], "Focus on regressions.")
        self.assertEqual(update_response.get_json()["model"]["color"], "#dc2626")
        project_models = self.client.get(
            f"/api/projects/models?project_id={project_id}",
            headers=self.auth_headers,
        ).get_json()["models"]
        self.assertEqual(sum(1 for item in project_models if item["is_default"]), 1)
        self.assertEqual(project_models[0]["id"], second_project_model["id"])
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.get_json()["deleted"])

    def test_project_chat_agent_can_change_without_changing_project_default(self):
        project_id = self.db.projects.create("Agent Project")
        provider = self.db.providers.get_first_by_type("ollama")
        profile = self.db.profiles.get_default()
        coder_model_id = self.db.models.create(
            name="coder-model",
            display_name="Coder Model",
            provider_config_id=provider["id"],
        )
        default_model_id = self.db.models.create(
            name="default-model",
            display_name="Default Model",
            provider_config_id=provider["id"],
        )
        coder_agent_id = self.db.project_models.create(
            project_id,
            coder_model_id,
            profile["id"],
            "coder",
            is_default=True,
        )
        default_agent_id = self.db.project_models.create(
            project_id,
            default_model_id,
            profile["id"],
            "default",
            is_default=False,
        )
        conversation_id = self.db.conversations.create(
            title="Project chat",
            project_id=project_id,
            project_model_id=coder_agent_id,
            profile_id=profile["id"],
            model_config_id=coder_model_id,
            provider="ollama",
            model="coder-model",
        )

        response = self.client.patch(
            "/api/conversations",
            json={
                "id": conversation_id,
                "project_model_id": default_agent_id,
            },
            headers=self.auth_headers,
        )
        conversation = self.db.conversations.get(conversation_id)
        project_models = self.db.project_models.list_models(project_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(conversation["project_model_id"], default_agent_id)
        self.assertEqual(conversation["model_config_id"], default_model_id)
        self.assertEqual(conversation["model"], "default-model")
        self.assertEqual(conversation["profile_id"], profile["id"])
        self.assertEqual(
            [item["id"] for item in project_models if item["is_default"]],
            [coder_agent_id],
        )

    def test_project_chat_can_store_quick_agents_without_changing_active_agent(self):
        project_id = self.db.projects.create("Quick Agent Project")
        provider = self.db.providers.get_first_by_type("ollama")
        profile = self.db.profiles.get_default()
        main_model_id = self.db.models.create(
            name="main-model",
            display_name="Main Model",
            provider_config_id=provider["id"],
        )
        review_model_id = self.db.models.create(
            name="review-model",
            display_name="Review Model",
            provider_config_id=provider["id"],
        )
        main_agent_id = self.db.project_models.create(
            project_id,
            main_model_id,
            profile["id"],
            "main",
            is_default=True,
        )
        review_agent_id = self.db.project_models.create(
            project_id,
            review_model_id,
            profile["id"],
            "reviewer",
        )
        conversation_id = self.db.conversations.create(
            title="Project chat",
            project_id=project_id,
            project_model_id=main_agent_id,
            profile_id=profile["id"],
            model_config_id=main_model_id,
            provider="ollama",
            model="main-model",
        )

        response = self.client.patch(
            "/api/conversations",
            json={
                "id": conversation_id,
                "quick_project_model_ids": [review_agent_id],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()["conversation"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["project_model_id"], main_agent_id)
        self.assertEqual(payload["model_config_id"], main_model_id)
        self.assertEqual(payload["quick_project_model_ids"], [review_agent_id])

    def test_project_agent_prompt_is_applied_and_message_metadata_is_persisted(self):
        project_id = self.db.projects.create("Agent Context")
        provider = self.db.providers.get_first_by_type("ollama")
        profile = self.db.profiles.get_default()
        model_id = self.db.models.create(
            name="agent-model",
            display_name="Agent Model",
            provider_config_id=provider["id"],
        )
        agent_id = self.db.project_models.create(
            project_id,
            model_id,
            profile["id"],
            "default",
            system_prompt="Use the project agent instructions.",
            is_default=True,
        )
        conversation_id = self.db.conversations.create(
            title="Project chat",
            project_id=project_id,
            project_model_id=agent_id,
            profile_id=profile["id"],
            model_config_id=model_id,
            provider="ollama",
            model="agent-model",
        )
        captured = {}

        def fake_chat(provider_name, messages, model_name, settings):
            captured["messages"] = messages
            return {
                "provider": provider_name,
                "model": model_name,
                "message": {
                    "role": "assistant",
                    "content": "Agent response",
                },
                "message_id": "agent-response",
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Use the agent"}],
            },
            headers=self.auth_headers,
        )
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Active project agent: default", captured["messages"][0]["content"])
        self.assertIn("Use the project agent instructions.", captured["messages"][0]["content"])
        self.assertEqual(response.get_json()["response"]["message"]["project_model_id"], agent_id)
        self.assertEqual(response.get_json()["response"]["message"]["project_model_name"], "default")
        self.assertEqual(stored_messages[1]["project_model_id"], agent_id)
        self.assertEqual(stored_messages[1]["project_model_name"], "default")

    def test_chat_endpoint_uses_context_messages_without_changing_persisted_message(self):
        conversation_id = self.db.conversations.create(
            title="Agent routing",
            provider="openai",
            model="gpt-4.1",
        )
        captured = {}

        def fake_chat(provider_name, messages, model_name, settings):
            captured["messages"] = messages
            return {
                "provider": provider_name,
                "model": model_name,
                "message": {
                    "role": "assistant",
                    "content": "Review only.",
                },
                "message_id": "agent-routing-response",
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "@Reviewer review this. @Yapper tell a joke.",
                    },
                ],
                "context_messages": [
                    {"role": "user", "content": "review this."},
                ],
            },
            headers=self.auth_headers,
        )
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["messages"][-1]["content"], "review this.")
        self.assertEqual(stored_messages[0]["content"], "@Reviewer review this. @Yapper tell a joke.")
        self.assertEqual(stored_messages[1]["content"], "Review only.")

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

    def test_chat_endpoint_reconstructs_active_history_from_sqlite(self):
        profile_id = self.db.profiles.create(
            name="Historian",
            system_prompt="Use prior facts from this chat only.",
            is_default=True,
        )
        conversation_id = self.db.conversations.create(
            title="Server history",
            profile_id=profile_id,
            provider="openai",
            model="gpt-4.1",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="The launch codename is Aurora.",
            position=0,
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="I will remember Aurora for this chat.",
            position=1,
            profile_id=profile_id,
            profile_name="Historian",
        )

        captured = {}

        def fake_chat(provider, messages, model, settings):
            captured["messages"] = messages
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Aurora is the codename.",
                },
                "message_id": "resp-history-1",
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "What is the codename?"}],
            },
            headers=self.auth_headers,
        )
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("[CONVERSATION HISTORY - READ ONLY]", captured["messages"][0]["content"])
        self.assertIn("The launch codename is Aurora.", captured["messages"][0]["content"])
        self.assertIn("I will remember Aurora for this chat.", captured["messages"][0]["content"])
        self.assertEqual(captured["messages"][1]["content"], "What is the codename?")
        self.assertEqual(len(stored_messages), 4)
        self.assertEqual(stored_messages[2]["content"], "What is the codename?")

    def test_project_chats_share_project_context_but_not_sibling_chat_memory(self):
        project_id = self.db.projects.create(
            "Client Alpha",
            "Workspace for Alpha.",
            "Use Alpha project instructions.",
        )
        first_conversation_id = self.db.conversations.create(
            title="First chat",
            project_id=project_id,
            provider="openai",
            model="gpt-4.1",
        )
        second_conversation_id = self.db.conversations.create(
            title="Second chat",
            project_id=project_id,
            provider="openai",
            model="gpt-4.1",
        )
        self.db.messages.create(
            conversation_id=first_conversation_id,
            role="user",
            content="Sibling-only secret is Blue Harbor.",
            position=0,
        )
        self.db.messages.create(
            conversation_id=first_conversation_id,
            role="assistant",
            content="Noted Blue Harbor.",
            position=1,
        )

        captured = {}

        def fake_chat(provider, messages, model, settings):
            captured["messages"] = messages
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "I only have this chat and project context.",
                },
                "message_id": "resp-project-memory-1",
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": second_conversation_id,
                "messages": [{"role": "user", "content": "What do you know here?"}],
            },
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Active project: Client Alpha", captured["messages"][0]["content"])
        self.assertIn("Use Alpha project instructions.", captured["messages"][0]["content"])
        self.assertNotIn("Sibling-only secret", captured["messages"][0]["content"])
        self.assertNotIn("Blue Harbor", captured["messages"][0]["content"])

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
        self.assertEqual(payload["messages"][1]["generation"]["available_tools"][0]["id"], tool_id)
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
            "export_lookup",
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
        stored_chunks = self.db.project_document_chunks.for_document(first_document_id)

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
        self.assertEqual(list_response.get_json()["folders"], [])
        self.assertEqual(len(listed_documents), 2)
        self.assertEqual(listed_documents[0]["filename"], "brief.txt")
        self.assertIn("Project summary", stored_document["text_content"])
        self.assertEqual(len(stored_chunks), 1)
        self.assertIn("Project summary", stored_chunks[0]["text_content"])
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(len(list_after_delete.get_json()["documents"]), 1)

    def test_project_delete_detaches_conversations_and_removes_documents(self):
        project_id = self.db.projects.create("Project to delete", "Keep chats")
        conversation_id = self.db.conversations.create(
            title="Keep me",
            project_id=project_id,
            provider="openai",
            model="gpt-4.1",
        )
        document_id = self.db.project_documents.create(
            project_id=project_id,
            filename="notes.txt",
            content_type="text/plain",
            size_bytes=12,
            text_content="Delete me too",
        )
        self.db.project_document_chunks.replace_for_document(
            document_id=document_id,
            project_id=project_id,
            chunks=[{"chunk_index": 0, "text_content": "Delete me too"}],
        )

        response = self.client.delete(
            f"/api/projects?id={project_id}",
            headers=self.auth_headers,
        )
        payload = response.get_json()
        detached_conversation = self.db.conversations.get(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["deleted"])
        self.assertEqual(payload["conversation_retention"], "detached")
        self.assertEqual(payload["orphaned_conversation_count"], 1)
        self.assertIsNone(detached_conversation["project_id"])
        self.assertIsNone(self.db.project_documents.get(document_id))
        self.assertEqual(self.db.project_document_chunks.for_document(document_id), [])

    def test_project_document_folders_support_upload_and_move_flow(self):
        project_id = self.db.projects.create("Docs", "Tree")

        create_specs_response = self.client.post(
            "/api/projects/document-folders",
            json={
                "project_id": project_id,
                "name": "Specs",
            },
            headers=self.auth_headers,
        )
        specs_folder = create_specs_response.get_json()["folder"]

        create_archived_response = self.client.post(
            "/api/projects/document-folders",
            json={
                "project_id": project_id,
                "name": "Archived",
                "parent_folder_id": specs_folder["id"],
            },
            headers=self.auth_headers,
        )
        archived_folder = create_archived_response.get_json()["folder"]

        upload_response = self.client.post(
            "/api/projects/documents",
            data={
                "project_id": str(project_id),
                "folder_id": str(specs_folder["id"]),
                "files": [
                    (io.BytesIO(b"v1 spec"), "spec-v1.txt"),
                ],
            },
            headers=self.auth_headers,
            content_type="multipart/form-data",
        )
        uploaded_document = upload_response.get_json()["documents"][0]

        move_response = self.client.patch(
            "/api/projects/documents",
            json={
                "id": uploaded_document["id"],
                "folder_id": archived_folder["id"],
            },
            headers=self.auth_headers,
        )
        list_response = self.client.get(
            f"/api/projects/documents?project_id={project_id}",
            headers=self.auth_headers,
        )
        payload = list_response.get_json()
        moved_document = move_response.get_json()["document"]

        self.assertEqual(create_specs_response.status_code, 201)
        self.assertEqual(create_archived_response.status_code, 201)
        self.assertEqual(upload_response.status_code, 201)
        self.assertEqual(uploaded_document["folder_id"], specs_folder["id"])
        self.assertEqual(uploaded_document["path"], "Specs/spec-v1.txt")
        self.assertEqual(move_response.status_code, 200)
        self.assertEqual(moved_document["folder_id"], archived_folder["id"])
        self.assertEqual(moved_document["path"], "Specs/Archived/spec-v1.txt")
        self.assertEqual(
            {folder["path"] for folder in payload["folders"]},
            {"Specs", "Specs/Archived"},
        )
        self.assertEqual(payload["documents"][0]["path"], "Specs/Archived/spec-v1.txt")

    def test_project_document_folder_can_be_deleted_without_losing_documents(self):
        project_id = self.db.projects.create("Docs", "Delete tree")
        specs_folder_id = self.db.project_document_folders.create(project_id, "Specs")
        nested_folder_id = self.db.project_document_folders.create(
            project_id,
            "Archived",
            parent_folder_id=specs_folder_id,
        )
        document_id = self.db.project_documents.create(
            project_id=project_id,
            filename="brief.txt",
            content_type="text/plain",
            size_bytes=5,
            text_content="brief",
            folder_id=nested_folder_id,
        )

        delete_response = self.client.delete(
            f"/api/projects/document-folders?id={specs_folder_id}",
            headers=self.auth_headers,
        )
        list_response = self.client.get(
            f"/api/projects/documents?project_id={project_id}",
            headers=self.auth_headers,
        )
        payload = list_response.get_json()

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.get_json()["folder_id"], specs_folder_id)
        self.assertEqual(payload["folders"], [])
        self.assertEqual(payload["documents"][0]["id"], document_id)
        self.assertIsNone(payload["documents"][0]["folder_id"])
        self.assertEqual(payload["documents"][0]["path"], "brief.txt")

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
        self.assertIn("not a supported text format", response.get_json()["error"]["message"])

    def test_chat_endpoint_assigns_generated_title_after_first_response(self):
        conversation_id = self.db.conversations.create(
            title="New conversation",
            provider="openai",
            model="gpt-4.1",
        )
        calls = []

        def fake_generate_title(provider, model, title_context, settings=None):
            calls.append(
                (
                    "title",
                    provider,
                    model,
                    [(message["role"], message["content"]) for message in title_context],
                )
            )
            return "Quantum computing basics"

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
        self.assertEqual(
            calls,
            [
                ("chat", "openai", "gpt-4.1", "Explain quantum computing to me"),
                (
                    "title",
                    "openai",
                    "gpt-4.1",
                    [
                        ("user", "Explain quantum computing to me"),
                        ("assistant", "Quantum computing uses qubits"),
                    ],
                ),
            ],
        )
        self.assertEqual(conversation["title"], "Quantum computing basics")
        self.assertEqual(payload["conversation"]["title"], "Quantum computing basics")

    def test_chat_endpoint_uses_provisional_title_when_model_title_generation_fails(self):
        conversation_id = self.db.conversations.create(
            title="New conversation",
            provider="mlx",
            model="gemma-3",
        )

        def failing_generate_title(provider, model, title_context, settings=None):
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
        self.assertEqual(conversation["title"], "Hello")

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

    def test_chat_endpoint_appends_after_non_contiguous_message_positions(self):
        conversation_id = self.db.conversations.create(
            title="Sparse positions",
            provider="openai",
            model="gpt-4.1",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="First saved message.",
            position=0,
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="First saved response.",
            position=2,
        )

        def fake_chat(provider, messages, model, settings):
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Fresh response.",
                },
                "message_id": None,
                "usage": {},
                "finish_reason": "stop",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Fresh question."}],
            },
            headers=self.auth_headers,
        )
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(message["role"], message["content"], message["position"]) for message in stored_messages],
            [
                ("user", "First saved message.", 0),
                ("assistant", "First saved response.", 2),
                ("user", "Fresh question.", 3),
                ("assistant", "Fresh response.", 4),
            ],
        )

    def test_chat_endpoint_rejects_unsupported_message_role(self):
        conversation_id = self.db.conversations.create(
            title="Invalid role",
            provider="openai",
            model="gpt-4.1",
        )

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "developer", "content": "Hidden instruction"}],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"]["code"], "bad_request")
        self.assertIn("role is not supported", payload["error"]["message"])

    def test_chat_endpoint_rejects_oversized_message_content(self):
        conversation_id = self.db.conversations.create(
            title="Oversized",
            provider="openai",
            model="gpt-4.1",
        )
        max_chars = self.api_manager.services.chat_service.MAX_MESSAGE_CONTENT_CHARS

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "x" * (max_chars + 1)}],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertIn("content must be at most", payload["error"]["message"])

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

    def test_chat_endpoint_splits_large_stream_delta_for_visible_progress(self):
        conversation_id = self.db.conversations.create(
            title="Streaming large delta",
            provider="openai",
            model="gpt-4.1",
        )
        content = (
            "This answer arrived from the provider as one large chunk, "
            "but the client should still receive visible progress."
        )

        def fake_stream_chat(provider, messages, model, settings, should_stop=None):
            yield {"type": "delta", "delta": content}
            yield {
                "type": "response",
                "response": {
                    "provider": provider,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "message_id": "resp-stream-large-delta",
                    "usage": {},
                    "finish_reason": "stop",
                    "raw": {"streamed": True},
                },
            }

        self.model_manager.stream_chat = fake_stream_chat
        self.api_manager.services.chat_stream_service.display_delta_delay_seconds = 0

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Say it slowly"}],
                "stream": True,
            },
            headers=self.auth_headers,
            buffered=True,
        )

        payload = response.get_data(as_text=True)
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertGreater(payload.count("event: delta"), 1)
        self.assertIn('"delta": "This answer arrived "', payload)
        self.assertEqual(stored_messages[1]["content"], content)

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

        model_calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            model_calls["count"] += 1
            if model_calls["count"] == 1:
                return {
                    "provider": provider,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"web_search","arguments":{"query":"breaking news","max_results":5},"reason":"The user asks for current web information."}}',
                    },
                    "message_id": None,
                    "usage": {},
                    "finish_reason": None,
                    "raw": {},
                }

            return {
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

        self.model_manager.chat = fake_chat

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
        self.assertIn("Streaming failed unexpectedly.", payload)
        self.assertNotIn("Tokenizer template exploded", payload)

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

    def test_settings_endpoint_masks_api_key(self):
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
        setting = read_response.get_json()["setting"]
        self.assertEqual(setting["value"], "")
        self.assertTrue(setting["has_value"])
        self.assertEqual(self.db.settings.get("openai_api_key")["value"], "sk-test")

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
        self.assertIn("maximum of 10", response.get_json()["error"]["message"])

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
        self.assertIn("last profile", response.get_json()["error"]["message"])

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
        self.assertEqual(response.get_json()["error"]["code"], "unauthorized")
        self.assertEqual(response.get_json()["error"]["message"], "Unauthorized")
