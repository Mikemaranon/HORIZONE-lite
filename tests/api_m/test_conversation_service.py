from tests.test_support import IsolatedDatabaseTestCase

from api_m.services import (
    ConversationRequestError,
    ConversationResourceNotFoundError,
    ConversationService,
)
from config_m import ConfigManager
from data_m import DBManager


class ConversationServiceTests(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.config_manager = ConfigManager()
        self.db = DBManager()
        self.service = ConversationService(self.db, self.config_manager)

    def test_create_with_project_agent_uses_agent_project_profile_and_model(self):
        project_id = self.db.projects.create("Research", "")
        profile = self.db.profiles.get_default()
        model = self.db.models.get_default()
        project_model_id = self.db.project_models.create(
            project_id=project_id,
            model_id=model["id"],
            profile_id=profile["id"],
            nickname="Writer",
        )

        conversation = self.service.create_conversation(
            {
                "title": "Agent chat",
                "project_model_id": project_model_id,
                "provider": "ignored",
                "model": "ignored",
            }
        )

        self.assertEqual(conversation["project_id"], project_id)
        self.assertEqual(conversation["project_model_id"], project_model_id)
        self.assertEqual(conversation["profile_id"], profile["id"])
        self.assertEqual(conversation["model_config_id"], model["id"])
        self.assertEqual(conversation["provider"], model["provider"])
        self.assertEqual(conversation["model"], model["name"])

    def test_quick_project_agents_are_unique_and_must_belong_to_project(self):
        project_id = self.db.projects.create("Main", "")
        other_project_id = self.db.projects.create("Other", "")
        profile = self.db.profiles.get_default()
        model = self.db.models.get_default()
        first_agent_id = self.db.project_models.create(project_id, model["id"], profile["id"], "First")
        second_agent_id = self.db.project_models.create(project_id, model["id"], profile["id"], "Second")
        other_agent_id = self.db.project_models.create(other_project_id, model["id"], profile["id"], "Other")

        conversation = self.service.create_conversation(
            {
                "project_id": project_id,
                "quick_project_model_ids": [first_agent_id, second_agent_id, first_agent_id],
            }
        )

        self.assertEqual(
            conversation["quick_project_model_ids"],
            [first_agent_id, second_agent_id],
        )
        with self.assertRaises(ConversationRequestError):
            self.service.create_conversation(
                {
                    "project_id": project_id,
                    "quick_project_model_ids": [other_agent_id],
                }
            )

    def test_quick_project_agents_require_project_chat(self):
        with self.assertRaises(ConversationRequestError):
            self.service.create_conversation({"quick_project_model_ids": [1]})

    def test_update_missing_conversation_raises_not_found(self):
        with self.assertRaises(ConversationResourceNotFoundError):
            self.service.update_conversation({"id": 999, "title": "Missing"})

    def test_get_conversation_can_include_messages(self):
        profile = self.db.profiles.get_default()
        model = self.db.models.get_default()
        conversation_id = self.db.conversations.create(
            title="History",
            profile_id=profile["id"],
            model_config_id=model["id"],
            provider=model["provider"],
            model=model["name"],
        )
        self.db.messages.create(conversation_id, "user", "Hello")

        payload = self.service.get_conversation(conversation_id, include_messages=True)

        self.assertEqual(payload["conversation"]["id"], conversation_id)
        self.assertEqual(payload["messages"][0]["content"], "Hello")
