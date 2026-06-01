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
