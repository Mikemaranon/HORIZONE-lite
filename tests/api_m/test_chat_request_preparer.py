from api_m.services import ChatContextBuilder, ChatRequestError, ChatRequestPreparer
from data_m import DBManager
from tests.test_support import IsolatedDatabaseTestCase


class ChatRequestPreparerTests(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.db = DBManager()
        self.context_builder = ChatContextBuilder(self.db)
        self.preparer = ChatRequestPreparer(
            self.db,
            self.context_builder,
            request_id_resolver=lambda raw: str(raw or "generated-request-id"),
        )

    def test_prepare_validates_int_fields_without_flask_parser(self):
        with self.assertRaises(ChatRequestError):
            self.preparer.prepare(
                {
                    "conversation_id": "not-an-id",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "provider": "openai",
                    "model": "gpt-4.1",
                },
                default_profile=self.db.profiles.get_default(),
                default_provider="mlx",
            )

    def test_prepare_resolves_runtime_context_and_request_id(self):
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Prepared",
            profile_id=profile["id"],
            provider="openai",
            model="gpt-4.1",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="Remember Aurora.",
        )

        prepared = self.preparer.prepare(
            {
                "conversation_id": str(conversation_id),
                "messages": [
                    {"role": "user", "content": "Remember Aurora."},
                    {"role": "user", "content": "What should you remember?"},
                ],
                "request_id": "client-request-1",
                "stream": "true",
            },
            default_profile=profile,
            default_provider="mlx",
        )

        self.assertEqual(prepared.conversation_id, conversation_id)
        self.assertEqual(prepared.provider, "openai")
        self.assertEqual(prepared.model, "gpt-4.1")
        self.assertEqual(prepared.request_id, "client-request-1")
        self.assertTrue(prepared.stream_requested)
        self.assertEqual(
            [message["content"] for message in prepared.request_messages],
            ["Remember Aurora.", "What should you remember?"],
        )
        self.assertEqual(prepared.input_messages[-1]["content"], "What should you remember?")

    def test_prepare_uses_context_messages_for_model_input_only(self):
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Prepared",
            profile_id=profile["id"],
            provider="openai",
            model="gpt-4.1",
        )

        prepared = self.preparer.prepare(
            {
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
            default_profile=profile,
            default_provider="mlx",
        )

        self.assertEqual(
            prepared.request_messages[-1]["content"],
            "@Reviewer review this. @Yapper tell a joke.",
        )
        self.assertEqual(prepared.input_messages[-1]["content"], "review this.")

    def test_prepare_accepts_structured_tool_confirmation(self):
        profile = self.db.profiles.get_default()

        prepared = self.preparer.prepare(
            {
                "messages": [{"role": "user", "content": "Continue"}],
                "provider": "ollama",
                "model": "qwen3",
                "tool_confirmation": {
                    "name": "workspace_write_file",
                    "arguments": {
                        "path": "notes.txt",
                        "content": "hello",
                    },
                    "reason": "User approved the write.",
                },
            },
            default_profile=profile,
            default_provider="mlx",
        )

        self.assertEqual(
            prepared.tool_confirmation,
            {
                "name": "workspace_write_file",
                "arguments": {
                    "path": "notes.txt",
                    "content": "hello",
                },
                "reason": "User approved the write.",
            },
        )
