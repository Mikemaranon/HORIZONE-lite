from api_m.services import ChatPersistenceService
from data_m import DBManager
from tests.test_support import IsolatedDatabaseTestCase


class FailingTitleModelManager:
    def generate_conversation_title(self, *args, **kwargs):
        raise AssertionError("title generation should be disabled")


class ChatPersistenceServiceTests(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.db = DBManager()

    def test_finalize_response_can_disable_title_generation(self):
        conversation_id = self.db.conversations.create(
            title="New conversation",
            provider="openai",
            model="gpt-4.1",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="Name this later",
        )
        service = ChatPersistenceService(
            self.db,
            FailingTitleModelManager(),
            generate_titles=False,
        )

        service.finalize_response(
            conversation_id,
            {
                "provider": "openai",
                "model": "gpt-4.1",
                "message": {
                    "role": "assistant",
                    "content": "The title generator should not run.",
                },
                "raw": {},
            },
        )

        conversation = self.db.conversations.get(conversation_id)
        messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(conversation["title"], "New conversation")
        self.assertEqual(messages[-1]["content"], "The title generator should not run.")
