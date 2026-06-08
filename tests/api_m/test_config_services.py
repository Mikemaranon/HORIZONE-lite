from pathlib import Path

from config_m import ConfigManager
from tests.test_support import IsolatedDatabaseTestCase

from api_m.services import (
    ConflictError,
    ModelConfigService,
    ProfileService,
    ProviderConfigService,
    RequestError,
    ResourceNotFoundError,
)
from data_m import DBManager


class FakeModelManager:
    def __init__(self):
        self.resolve_calls = []

    def resolve_provider_configuration(self, provider_type, endpoint="", api_key="", *, allow_probe=True):
        self.resolve_calls.append(
            {
                "provider_type": provider_type,
                "endpoint": endpoint,
                "api_key": api_key,
                "allow_probe": allow_probe,
            }
        )
        return {
            "resolved_adapter": "openai_compatible" if provider_type == "cloud" else "",
            "resolved_metadata": {"endpoint": endpoint} if provider_type == "cloud" else {},
        }


class ModelConfigServiceTests(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.db = DBManager()
        self.service = ModelConfigService(self.db)

    def test_update_model_syncs_conversations_and_message_labels(self):
        profile = self.db.profiles.get_default()
        provider = self.db.providers.get_first_by_type("ollama")
        model_id = self.db.models.create(
            name="old-model",
            display_name="Old Model",
            provider_config_id=provider["id"],
        )
        conversation_id = self.db.conversations.create(
            title="Uses model",
            profile_id=profile["id"],
            model_config_id=model_id,
            provider="ollama",
            model="old-model",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="Hi",
            model_config_id=model_id,
            model_name="Old Model",
        )

        updated = self.service.update_model(
            {
                "id": model_id,
                "name": "new-model",
                "display_name": "New Model",
                "provider_id": provider["id"],
            }
        )

        conversation = self.db.conversations.get(conversation_id)
        message = self.db.messages.for_conversation(conversation_id)[0]
        self.assertEqual(updated["name"], "new-model")
        self.assertEqual(conversation["model"], "new-model")
        self.assertEqual(message["model_name"], "New Model")

    def test_invalid_icon_image_is_rejected(self):
        provider = self.db.providers.get_first_by_type("ollama")

        with self.assertRaises(RequestError):
            self.service.create_model(
                {
                    "name": "broken",
                    "provider_id": provider["id"],
                    "icon_image": "data:text/plain;base64,SGk=",
                }
            )

    def test_delete_missing_model_raises_not_found(self):
        with self.assertRaises(ResourceNotFoundError):
            self.service.delete_model(999)

    def test_manual_model_creation_rejects_system_managed_provider(self):
        provider = self.db.providers.get_by_builtin_key("horizone_runtime")

        with self.assertRaises(RequestError):
            self.service.create_model(
                {
                    "name": "manual-runtime-model",
                    "provider_id": provider["id"],
                }
            )

    def test_runtime_model_update_preserves_technical_name_and_provider(self):
        runtime_provider = self.db.providers.get_by_builtin_key("horizone_runtime")
        ollama_provider = self.db.providers.get_by_builtin_key("ollama")
        model_id = self.db.models.create(
            name="tiny-runtime",
            display_name="Tiny Runtime",
            provider_config_id=runtime_provider["id"],
            is_builtin=True,
        )

        updated = self.service.update_model(
            {
                "id": model_id,
                "name": "tampered-name",
                "display_name": "Personal Tiny",
                "provider_id": ollama_provider["id"],
                "icon_image": "",
            }
        )

        self.assertEqual(updated["name"], "tiny-runtime")
        self.assertEqual(updated["display_name"], "Personal Tiny")
        self.assertEqual(updated["provider"], "llama_cpp")
        self.assertEqual(updated["provider_id"], runtime_provider["id"])

    def test_runtime_model_delete_removes_download_record_and_file(self):
        runtime_provider = self.db.providers.get_by_builtin_key("horizone_runtime")
        model_path = Path(self.temp_dir.name) / "tiny.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        config = ConfigManager()
        runtime_config = config.runtime.__class__(
            **{
                **config.runtime.__dict__,
                "runtime_models_dir": self.temp_dir.name,
            }
        )
        service = ModelConfigService(self.db, runtime_config=runtime_config)
        model_id = self.db.models.create(
            name="tiny-runtime",
            display_name="Tiny Runtime",
            provider_config_id=runtime_provider["id"],
            is_builtin=True,
        )
        self.db.runtime_model_downloads.create(
            catalog_key="tiny-runtime",
            status="ready",
            source_url="https://example.test/tiny.gguf",
            filename="tiny.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )

        payload = service.delete_model(model_id)

        self.assertTrue(payload["deleted"])
        self.assertFalse(model_path.exists())
        self.assertEqual(self.db.runtime_model_downloads.for_model(model_id), [])


class ProviderConfigServiceTests(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.db = DBManager()
        self.model_manager = FakeModelManager()
        self.service = ProviderConfigService(self.db, self.model_manager)

    def test_public_provider_never_serializes_api_key(self):
        provider = self.service.create_provider(
            {
                "name": "Cloud",
                "provider_type": "cloud",
                "endpoint": "https://api.openai.com/v1",
                "api_key": "sk-secret",
            }
        )

        self.assertNotIn("api_key", provider)
        self.assertTrue(provider["has_api_key"])
        self.assertEqual(self.model_manager.resolve_calls[-1]["api_key"], "sk-secret")
        self.assertFalse(self.model_manager.resolve_calls[-1]["allow_probe"])

    def test_update_without_api_key_preserves_existing_secret(self):
        provider_id = self.db.providers.create(
            name="Cloud",
            provider_type="cloud",
            endpoint="https://api.openai.com/v1",
            api_key="sk-existing",
        )

        self.service.update_provider(
            {
                "id": provider_id,
                "name": "Cloud renamed",
                "provider_type": "cloud",
                "endpoint": "https://api.openai.com/v1",
            }
        )

        self.assertEqual(self.db.providers.get(provider_id)["api_key"], "sk-existing")
        self.assertEqual(self.model_manager.resolve_calls[-1]["api_key"], "sk-existing")
        self.assertFalse(self.model_manager.resolve_calls[-1]["allow_probe"])

    def test_connection_uses_explicit_probe_path(self):
        payload = self.service.test_provider_connection(
            {
                "name": "Cloud",
                "provider_type": "cloud",
                "endpoint": "https://custom.example/v1",
                "api_key": "sk-secret",
            }
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(self.model_manager.resolve_calls[-1]["allow_probe"])

    def test_builtin_provider_delete_raises_conflict(self):
        provider = self.db.providers.get_by_builtin_key("ollama")

        with self.assertRaises(ConflictError):
            self.service.delete_provider(provider["id"])

    def test_builtin_provider_restore_keeps_working_for_user_editable_builtins(self):
        provider = self.db.providers.get_by_builtin_key("ollama")
        self.service.update_provider(
            {
                "id": provider["id"],
                "name": "Local Ollama",
                "provider_type": "ollama",
                "endpoint": "http://127.0.0.1:9999/api",
            }
        )

        restored = self.service.restore_provider({"id": provider["id"]})

        self.assertEqual(restored["name"], "Ollama")
        self.assertEqual(restored["endpoint"], "http://localhost:11434/api")

    def test_llama_cpp_provider_cannot_be_created_manually(self):
        with self.assertRaises(RequestError):
            self.service.create_provider(
                {
                    "name": "Manual runtime",
                    "provider_type": "llama_cpp",
                }
            )

    def test_system_managed_provider_cannot_be_edited_deleted_or_restored(self):
        provider = self.db.providers.get_by_builtin_key("horizone_runtime")

        with self.assertRaises(ConflictError):
            self.service.update_provider(
                {
                    "id": provider["id"],
                    "name": "Runtime renamed",
                    "provider_type": "llama_cpp",
                }
            )
        with self.assertRaises(ConflictError):
            self.service.delete_provider(provider["id"])
        with self.assertRaises(ConflictError):
            self.service.restore_provider({"id": provider["id"]})

    def test_public_provider_serializes_system_managed_flag(self):
        provider = self.db.providers.get_by_builtin_key("horizone_runtime")
        payload = self.service.get_provider(provider["id"])

        self.assertTrue(payload["is_system_managed"])
        self.assertEqual(payload["provider_type"], "llama_cpp")


class ProfileServiceTests(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.db = DBManager()
        self.service = ProfileService(self.db)

    def test_tags_are_unique_case_insensitive(self):
        profile = self.service.create_profile(
            {
                "name": "Tagged",
                "tags": ["Code", "code", " review ", ""],
            }
        )

        self.assertEqual(profile["tags"], ["Code", "review"])

    def test_rejects_more_than_ten_tags(self):
        with self.assertRaises(RequestError):
            self.service.create_profile(
                {
                    "name": "Too many",
                    "tags": [str(index) for index in range(11)],
                }
            )

    def test_last_profile_cannot_be_deleted(self):
        profile = self.db.profiles.get_default()

        with self.assertRaises(RequestError):
            self.service.delete_profile(profile["id"])
