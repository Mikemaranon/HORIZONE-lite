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

    def test_persist_assistant_message_confirms_matching_workspace_write_request(self):
        conversation_id = self.db.conversations.create(
            title="Approval flow",
            provider="ollama",
            model="qwen3",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="I need approval before writing the file.",
            tool_events=[
                {
                    "ok": False,
                    "tool_name": "workspace_write_file",
                    "arguments": {"path": "hello.java", "content": "hello"},
                    "error": "This tool requires explicit confirmation before execution.",
                    "policy": {
                        "status": "confirmation_required",
                        "risk_level": "workspace_write",
                    },
                },
            ],
        )
        service = ChatPersistenceService(
            self.db,
            FailingTitleModelManager(),
            generate_titles=False,
        )

        service.persist_assistant_message(
            conversation_id,
            {
                "provider": "ollama",
                "model": "qwen3",
                "message": {
                    "role": "assistant",
                    "content": "The file has been created.",
                },
                "raw": {
                    "tool_events": [
                        {
                            "ok": True,
                            "tool_name": "workspace_write_file",
                            "arguments": {"content": "hello", "path": "hello.java"},
                            "result": {"file": {"path": "hello.java", "created": True}},
                            "policy": {"status": "confirmed"},
                        },
                    ],
                },
            },
        )

        messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(
            messages[0]["tool_events"][0]["policy"]["status"],
            "confirmed",
        )
