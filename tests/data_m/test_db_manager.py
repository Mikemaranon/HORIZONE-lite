from unittest.mock import patch

from tests.test_support import IsolatedDatabaseTestCase

from config_m import ConfigManager
from data_m import DBManager
from user_m import UserManager


class DBManagerTests(IsolatedDatabaseTestCase):
    def test_clean_boot_creates_database_file_and_default_records(self):
        self.assertFalse(self.db_path.exists())

        db = DBManager()
        config_manager = ConfigManager()
        user_manager = UserManager(
            db_manager=db,
            secret_key=config_manager.runtime.secret_key,
        )

        self.assertTrue(self.db_path.exists())
        self.assertIsNotNone(db.profiles.get_default())
        self.assertIsNotNone(db.users.get("admin"))
        self.assertIs(user_manager.db, db)

    def test_creates_default_profile_on_first_boot(self):
        db = DBManager()

        default_profile = db.profiles.get_default()

        self.assertIsNotNone(default_profile)
        self.assertEqual(default_profile["name"], "Default Assistant")
        self.assertTrue(default_profile["is_default"])

    def test_seeds_builtin_providers_on_first_boot(self):
        db = DBManager()

        providers = db.providers.all()
        provider_types = {provider["provider_type"] for provider in providers}

        self.assertIn("mlx", provider_types)
        self.assertIn("ollama", provider_types)

    def test_projects_conversations_and_messages_roundtrip(self):
        db = DBManager()
        profile = db.profiles.get_default()
        default_model = db.models.get_default()
        project_id = db.projects.create("Workspace", "Primary project")
        conversation_id = db.conversations.create(
            title="Kickoff",
            project_id=project_id,
            profile_id=profile["id"],
            provider="mlx",
            model="gemma-3",
        )

        first_message_id = db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="Hola",
        )
        second_message_id = db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Que tal",
            model_config_id=default_model["id"] if default_model else None,
            model_name=default_model["name"] if default_model else "gemma-3",
            profile_id=profile["id"],
            profile_name=profile["name"],
        )

        project = db.projects.get(project_id)
        conversation = db.conversations.get(conversation_id)
        messages = db.messages.for_conversation(conversation_id)

        self.assertEqual(project["name"], "Workspace")
        self.assertEqual(conversation["provider"], "mlx")
        self.assertEqual(conversation["profile_id"], profile["id"])
        self.assertEqual([message["id"] for message in messages], [first_message_id, second_message_id])
        self.assertEqual([message["position"] for message in messages], [0, 1])
        self.assertEqual(messages[1]["profile_name"], profile["name"])
        self.assertEqual(
            messages[1]["model_name"],
            default_model["display_name"] if default_model else "gemma-3",
        )
        self.assertEqual(messages[1]["tool_events"], [])

        db.conversations.rename(conversation_id, "Workspace kickoff")
        renamed_conversation = db.conversations.get(conversation_id)
        self.assertEqual(renamed_conversation["title"], "Workspace kickoff")

    def test_messages_persist_tool_events(self):
        db = DBManager()
        profile = db.profiles.get_default()
        conversation_id = db.conversations.create(
            title="Sources",
            profile_id=profile["id"],
            provider="mlx",
            model="gemma-3",
        )

        db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Respuesta con fuentes",
            tool_events=[
                {
                    "tool_name": "web_search",
                    "arguments": {"query": "lol followers"},
                    "ok": True,
                    "result": {
                        "results": [
                            {"title": "Fuente", "url": "https://example.com"}
                        ]
                    },
                }
            ],
        )

        message = db.messages.for_conversation(conversation_id)[0]

        self.assertEqual(message["tool_events"][0]["tool_name"], "web_search")
        self.assertEqual(
            message["tool_events"][0]["result"]["results"][0]["url"],
            "https://example.com",
        )

    def test_settings_and_model_cache_support_upsert(self):
        db = DBManager()

        db.settings.set("openai_api_key", "secret")
        db.models_cache.upsert(
            provider="ollama",
            model_id="llama3.2",
            display_name="Llama 3.2",
            source="local",
        )
        db.models_cache.upsert(
            provider="ollama",
            model_id="llama3.2",
            display_name="Llama 3.2 Updated",
            source="local",
        )

        setting = db.settings.get("openai_api_key")
        cached_models = db.models_cache.list_models("ollama")

        self.assertEqual(setting["value"], "secret")
        self.assertEqual(len(cached_models), 1)
        self.assertEqual(cached_models[0]["display_name"], "Llama 3.2 Updated")

    def test_profiles_support_personality_tags_and_default_reassignment(self):
        db = DBManager()
        original_default = db.profiles.get_default()

        profile_id = db.profiles.create(
            name="Research",
            personality="Preciso y sereno",
            tags=["analysis", "docs"],
            system_prompt="Trabaja con estructura.",
        )
        profile = db.profiles.get(profile_id)

        self.assertEqual(profile["personality"], "Preciso y sereno")
        self.assertEqual(profile["tags"], ["analysis", "docs"])

        db.profiles.delete(original_default["id"])
        replacement_default = db.profiles.get_default()

        self.assertIsNotNone(replacement_default)
        self.assertEqual(replacement_default["id"], profile_id)
        self.assertTrue(replacement_default["is_default"])

    def test_profiles_store_up_to_ten_unique_tags(self):
        db = DBManager()
        profile_id = db.profiles.create(
            name="Tag heavy",
            tags=[
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
                "python",
                "extra",
            ],
        )

        profile = db.profiles.get(profile_id)

        self.assertEqual(
            profile["tags"],
            [
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
        )

    def test_models_reference_provider_records(self):
        db = DBManager()
        ollama_provider = db.providers.get_first_by_type("ollama")

        model_id = db.models.create(
            name="qwen3",
            provider_config_id=ollama_provider["id"],
            display_name="Qwen 3",
        )

        model = db.models.get(model_id)

        self.assertEqual(model["provider_id"], ollama_provider["id"])
        self.assertEqual(model["provider_name"], ollama_provider["name"])
        self.assertEqual(model["provider_type"], "ollama")
        self.assertEqual(model["icon_image"], "")
        self.assertEqual(model["display_name"], "Qwen 3")

    def test_legacy_cloud_provider_types_are_migrated_to_cloud(self):
        db = DBManager()
        profile = db.profiles.get_default()
        legacy_provider_id = db.providers.create(
            name="Legacy OpenAI",
            provider_type="openai",
            endpoint="https://api.openai.com/v1",
        )
        model_id = db.models.create(
            name="gpt-4.1",
            provider_config_id=legacy_provider_id,
            display_name="GPT-4.1",
        )
        conversation_id = db.conversations.create(
            title="Legacy cloud",
            profile_id=profile["id"],
            model_config_id=model_id,
            provider="openai",
            model="gpt-4.1",
        )

        db.providers.ensure_seed_providers()

        provider = db.providers.get(legacy_provider_id)
        model = db.models.get(model_id)
        conversation = db.conversations.get(conversation_id)

        self.assertEqual(provider["provider_type"], "cloud")
        self.assertEqual(provider["resolved_adapter"], "openai_compatible")
        self.assertEqual(model["provider"], "cloud")
        self.assertEqual(conversation["provider"], "cloud")

    def test_seeded_mlx_model_uses_canonical_repo_id_on_apple(self):
        with patch("data_m.db_methods.t_models.platform.system", return_value="Darwin"):
            db = DBManager()

        default_model = db.models.get_default()

        self.assertIsNotNone(default_model)
        self.assertEqual(default_model["provider"], "mlx")
        self.assertEqual(default_model["name"], "mlx-community/gemma-3-4b-it-4bit")
        self.assertEqual(default_model["display_name"], "gemma-3")

    def test_existing_mlx_short_name_is_upgraded_on_boot(self):
        db = DBManager()
        mlx_provider = db.providers.get_first_by_type("mlx")
        profile = db.profiles.get_default()
        model_id = db.models.create(
            name="gemma-3-4b-it-4bit",
            provider_config_id=mlx_provider["id"],
        )
        conversation_id = db.conversations.create(
            title="Upgrade me",
            profile_id=profile["id"],
            model_config_id=model_id,
            provider="mlx",
            model="gemma-3-4b-it-4bit",
        )
        db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Hola",
            model_config_id=model_id,
            model_name="gemma-3-4b-it-4bit",
            profile_id=profile["id"],
            profile_name=profile["name"],
        )

        db.models.ensure_seed_models()

        model = db.models.get_by_provider_and_name(
            "mlx",
            "mlx-community/gemma-3-4b-it-4bit",
        )
        conversation = db.conversations.get(conversation_id)
        messages = db.messages.for_conversation(conversation_id)

        self.assertIsNotNone(model)
        self.assertEqual(model["name"], "mlx-community/gemma-3-4b-it-4bit")
        self.assertEqual(model["display_name"], "gemma-3")
        self.assertEqual(conversation["model_config_id"], model["id"])
        self.assertEqual(conversation["model"], "mlx-community/gemma-3-4b-it-4bit")
        self.assertEqual(messages[0]["model_name"], "gemma-3")
        self.assertEqual(messages[0]["model_config_id"], model["id"])

    def test_models_default_display_name_to_technical_name(self):
        db = DBManager()
        ollama_provider = db.providers.get_first_by_type("ollama")

        model_id = db.models.create(
            name="llama3.2:latest",
            provider_config_id=ollama_provider["id"],
        )

        model = db.models.get(model_id)

        self.assertEqual(model["name"], "llama3.2:latest")
        self.assertEqual(model["display_name"], "llama3.2:latest")
