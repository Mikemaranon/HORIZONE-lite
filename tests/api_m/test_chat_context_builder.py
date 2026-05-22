from api_m.services.chat_context_builder import ChatContextBuilder
from data_m import DBManager
from tests.test_support import IsolatedDatabaseTestCase


class ChatContextBuilderTests(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.db = DBManager()
        self.builder = ChatContextBuilder(self.db)

    def test_build_input_messages_uses_read_only_context_and_last_user_message(self):
        project_id = self.db.projects.create(
            "Launch Pad",
            "Coordinate the release plan.",
            "Keep attention on risks and milestones.",
        )
        self.db.project_documents.create(
            project_id=project_id,
            filename="brief.md",
            content_type="text/markdown",
            size_bytes=64,
            text_content="Release date is June 5 and QA sign-off is still pending.",
        )

        project = self.db.projects.get(project_id)
        profile = {
            "name": "Souless",
            "system_prompt": "Be terse. Do not use emojis.",
        }
        messages = [
            {"role": "user", "content": "Version 1 shipped yesterday."},
            {
                "role": "assistant",
                "content": "Amazing work! 🚀 We should celebrate first.",
                "profile_name": "Coleague",
            },
            {"role": "user", "content": "What should happen next?"},
        ]

        built_messages = self.builder.build_input_messages(project, profile, messages)

        self.assertEqual(
            [message["role"] for message in built_messages],
            ["system", "user"],
        )
        self.assertIn("Active profile: Souless", built_messages[0]["content"])
        self.assertIn("Be terse. Do not use emojis.", built_messages[0]["content"])
        self.assertIn("[PROJECT CONTEXT - READ ONLY]", built_messages[0]["content"])
        self.assertIn("Active project: Launch Pad", built_messages[0]["content"])
        self.assertIn("brief.md", built_messages[0]["content"])
        self.assertIn(
            "[CONVERSATION HISTORY - READ ONLY]",
            built_messages[0]["content"],
        )
        self.assertIn(
            "[Previous assistant message]",
            built_messages[0]["content"],
        )
        self.assertIn("Profile: Coleague", built_messages[0]["content"])
        self.assertIn(
            "Content:\nAmazing work! 🚀 We should celebrate first.",
            built_messages[0]["content"],
        )
        self.assertIn("[Previous user message]", built_messages[0]["content"])
        self.assertNotIn("assistant (Coleague):", built_messages[0]["content"])
        self.assertFalse(
            any(line.startswith("assistant (") for line in built_messages[0]["content"].splitlines())
        )
        self.assertFalse(
            any(line.startswith("user:") for line in built_messages[0]["content"].splitlines())
        )
        self.assertNotIn("What should happen next?", built_messages[0]["content"])
        self.assertIn(self.builder.FINAL_PROFILE_REMINDER, built_messages[0]["content"])
        self.assertIn(
            "Speaker labels and profile labels are metadata only.",
            built_messages[0]["content"],
        )
        self.assertIn(
            "The final answer must start directly with the response content.",
            built_messages[0]["content"],
        )
        self.assertEqual(
            built_messages[1],
            {"role": "user", "content": "What should happen next?"},
        )

    def test_get_last_user_message_returns_only_latest_user_turn(self):
        last_user_message = self.builder._get_last_user_message(
            [
                {"role": "user", "content": "First"},
                {"role": "assistant", "content": "Reply"},
                {
                    "role": "user",
                    "content": [
                        {"text": "Second"},
                        {"text": "question"},
                    ],
                },
            ]
        )

        self.assertEqual(
            last_user_message,
            {"role": "user", "content": "Second\nquestion"},
        )

    def test_history_context_includes_previous_tool_usage(self):
        built_messages = self.builder.build_input_messages(
            None,
            {
                "name": "Research",
                "system_prompt": "Be precise.",
            },
            [
                {"role": "user", "content": "Busca el dato."},
                {
                    "role": "assistant",
                    "content": "He encontrado la respuesta.",
                    "tool_events": [
                        {
                            "tool_name": "web_search",
                            "arguments": {"query": "league followers"},
                            "ok": True,
                            "result": {
                                "results": [
                                    {"title": "Fuente 1", "url": "https://example.com/1"},
                                ]
                            },
                        }
                    ],
                },
                {"role": "user", "content": "Dame las fuentes consultadas."},
            ],
        )

        self.assertIn("[Previous tool usage]", built_messages[0]["content"])
        self.assertIn("web_search", built_messages[0]["content"])
        self.assertIn("https://example.com/1", built_messages[0]["content"])
