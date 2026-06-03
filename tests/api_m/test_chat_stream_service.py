from api_m.services import ChatStreamService
from model_m import ProviderUnavailableError
from tests.test_support import IsolatedDatabaseTestCase


class FakePersistenceService:
    def __init__(self):
        self.finalized = []

    def finalize_response(self, conversation_id, response, assistant_message_meta=None):
        self.finalized.append((conversation_id, response, assistant_message_meta))


class FakeStreamExecutor:
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error

    def stream_chat(self, provider, messages, model, settings, should_stop=None, tool_context=None):
        if self.error:
            raise self.error

        for event in self.events:
            if should_stop and should_stop():
                return
            yield event


class ChatStreamServiceTests(IsolatedDatabaseTestCase):
    def test_iter_stream_events_yields_domain_events_without_flask_response(self):
        persistence = FakePersistenceService()
        service = ChatStreamService(
            db_manager=None,
            model_manager=None,
            persistence_service=persistence,
            executor=FakeStreamExecutor(
                [
                    {"type": "delta", "delta": "Hello"},
                    {
                        "type": "response",
                        "response": {
                            "provider": "openai",
                            "model": "gpt-4.1",
                            "message": {"role": "assistant", "content": "Hello"},
                            "usage": {},
                            "finish_reason": "stop",
                            "raw": {},
                        },
                    },
                ]
            ),
        )

        events = list(
            service.iter_stream_events(
                conversation_id=None,
                provider="openai",
                input_messages=[{"role": "user", "content": "Hi"}],
                model="gpt-4.1",
                generation_settings={},
                request_id="stream-direct",
                assistant_message_meta={},
            )
        )

        self.assertEqual([event["event"] for event in events], ["start", "delta", "end"])
        self.assertEqual(events[1]["data"], {"delta": "Hello"})
        self.assertEqual(events[-1]["data"]["response"]["message"]["content"], "Hello")
        self.assertEqual(persistence.finalized, [])
        self.assertNotIn("stream-direct", service._active_streams)

    def test_iter_stream_events_releases_cancelled_stream_and_reconstructs_partial_response(self):
        persistence = FakePersistenceService()
        service = ChatStreamService(
            db_manager=None,
            model_manager=None,
            persistence_service=persistence,
            executor=FakeStreamExecutor(
                [
                    {"type": "delta", "delta": "partial"},
                    {"type": "delta", "delta": " ignored"},
                ]
            ),
        )
        events = service.iter_stream_events(
            conversation_id=None,
            provider="openai",
            input_messages=[{"role": "user", "content": "Hi"}],
            model="gpt-4.1",
            generation_settings={},
            request_id="stream-cancel",
            assistant_message_meta={},
        )

        first_event = next(events)
        self.assertEqual(first_event["event"], "start")
        self.assertTrue(service.cancel("stream-cancel"))

        remaining_events = list(events)
        end_event = remaining_events[-1]

        self.assertEqual(end_event["event"], "end")
        self.assertTrue(end_event["data"]["cancelled"])
        self.assertEqual(end_event["data"]["response"]["finish_reason"], "cancelled")
        self.assertEqual(end_event["data"]["response"]["message"]["content"], "")
        self.assertNotIn("stream-cancel", service._active_streams)

    def test_iter_stream_events_sanitizes_unexpected_errors_and_releases_stream(self):
        service = ChatStreamService(
            db_manager=None,
            model_manager=None,
            persistence_service=FakePersistenceService(),
            executor=FakeStreamExecutor(error=RuntimeError("local template path leaked")),
        )

        events = list(
            service.iter_stream_events(
                conversation_id=None,
                provider="mlx",
                input_messages=[{"role": "user", "content": "Hi"}],
                model="gemma",
                generation_settings={},
                request_id="stream-error",
                assistant_message_meta={},
            )
        )

        self.assertEqual(events[-1]["event"], "error")
        self.assertEqual(
            events[-1]["data"]["error"],
            {
                "code": "streaming_internal_error",
                "message": "Streaming failed unexpectedly.",
                "request_id": "stream-error",
            },
        )
        self.assertEqual(events[-1]["data"]["request_id"], "stream-error")
        self.assertNotIn("local template path leaked", str(events))
        self.assertNotIn("stream-error", service._active_streams)

    def test_iter_stream_events_keeps_provider_errors_user_visible(self):
        service = ChatStreamService(
            db_manager=None,
            model_manager=None,
            persistence_service=FakePersistenceService(),
            executor=FakeStreamExecutor(
                error=ProviderUnavailableError("MLX offline", provider="mlx")
            ),
        )

        events = list(
            service.iter_stream_events(
                conversation_id=None,
                provider="mlx",
                input_messages=[{"role": "user", "content": "Hi"}],
                model="gemma",
                generation_settings={},
                request_id="stream-provider-error",
                assistant_message_meta={},
            )
        )

        self.assertEqual(events[-1]["event"], "error")
        self.assertIn("MLX offline", events[-1]["data"]["error"]["message"])
        self.assertEqual(events[-1]["data"]["error"]["request_id"], "stream-provider-error")
