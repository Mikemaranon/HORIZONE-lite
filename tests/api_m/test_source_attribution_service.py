from tests.test_support import IsolatedDatabaseTestCase

from api_m.services import SourceAttributionService
from data_m import DBManager


class SourceAttributionServiceTests(IsolatedDatabaseTestCase):
    def test_returns_none_when_latest_user_message_is_not_source_follow_up(self):
        service = SourceAttributionService(DBManager())

        response = service.build_follow_up_response(
            conversation_id=None,
            request_messages=[{"role": "user", "content": "Summarize this"}],
            provider="mlx",
            model="gemma-3",
        )

        self.assertIsNone(response)

    def test_returns_no_sources_response_without_conversation(self):
        service = SourceAttributionService(DBManager())

        response = service.build_follow_up_response(
            conversation_id=None,
            request_messages=[{"role": "user", "content": "tell me the sources"}],
            provider="mlx",
            model="gemma-3",
        )

        self.assertIsNotNone(response)
        self.assertTrue(response["raw"]["source_attribution"])
        self.assertEqual(response["raw"]["tool_events"], [])
        self.assertIn("not consulted external sources", response["message"]["content"])

    def test_returns_sources_from_previous_assistant_tool_events(self):
        db = DBManager()
        service = SourceAttributionService(db)
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
            content="Answer with sources",
            tool_events=[
                {
                    "tool_name": "web_search",
                    "ok": True,
                    "result": {
                        "results": [
                            {"title": "Schedule", "url": "https://example.com/match"},
                            {"title": "Duplicate", "url": "https://example.com/match"},
                        ]
                    },
                }
            ],
        )

        response = service.build_follow_up_response(
            conversation_id=conversation_id,
            request_messages=[{"role": "user", "content": "tell me the sources consulted"}],
            provider="mlx",
            model="gemma-3",
        )

        content = response["message"]["content"]
        self.assertIn("The sources consulted in the previous response are:", content)
        self.assertIn("Schedule", content)
        self.assertIn("example.com", content)
        self.assertNotIn("Duplicate", content)
