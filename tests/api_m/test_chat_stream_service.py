from api_m.services import ChatStreamService
from api_m.services.reasoning_content_filter import ReasoningStreamFilter, strip_reasoning_content
from data_m import DBManager
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


class FakeModelManager:
    def __init__(self):
        self.cancelled_providers = []

    def cancel_stream(self, provider):
        self.cancelled_providers.append(provider)
        return True


class ChatStreamServiceTests(IsolatedDatabaseTestCase):
    def test_strip_reasoning_content_removes_complete_and_unopened_think_prefixes(self):
        self.assertEqual(
            strip_reasoning_content("<think>\nprivate notes\n</think>\n\nVisible answer"),
            "Visible answer",
        )
        self.assertEqual(
            strip_reasoning_content("private notes\n</think>\n\nVisible answer"),
            "Visible answer",
        )
        self.assertEqual(
            strip_reasoning_content("<thinking>private</thinking>Visible"),
            "Visible",
        )
        self.assertEqual(
            strip_reasoning_content("[thinking]private[/thinking]Visible"),
            "Visible",
        )

    def test_reasoning_stream_filter_handles_chunked_bracket_thinking_markers(self):
        reasoning_filter = ReasoningStreamFilter()

        self.assertEqual(reasoning_filter.feed("[thin"), "")
        self.assertEqual(reasoning_filter.feed("king]private[/thinking]Visible"), "Visible")
        self.assertEqual(reasoning_filter.reasoning_content, "private")
        self.assertEqual(
            [event["type"] for event in reasoning_filter.pop_events()],
            ["start", "end"],
        )

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

    def test_iter_stream_events_hides_reasoning_deltas_and_sanitizes_final_response(self):
        persistence = FakePersistenceService()
        raw_content = "<think>\nprivate notes\n</think>\n\nVisible answer"
        service = ChatStreamService(
            db_manager=None,
            model_manager=None,
            persistence_service=persistence,
            executor=FakeStreamExecutor(
                [
                    {"type": "delta", "delta": "<thi"},
                    {"type": "delta", "delta": "nk>\nprivate notes\n"},
                    {"type": "delta", "delta": "</think>\n\nVisible answer"},
                    {
                        "type": "response",
                        "response": {
                            "provider": "llama_cpp",
                            "model": "qwen-reasoning",
                            "message": {"role": "assistant", "content": raw_content},
                            "usage": {},
                            "finish_reason": "stop",
                            "raw": {},
                        },
                    },
                ]
            ),
            display_delta_delay_seconds=0,
        )

        events = list(
            service.iter_stream_events(
                conversation_id=None,
                provider="llama_cpp",
                input_messages=[{"role": "user", "content": "Hi"}],
                model="qwen-reasoning",
                generation_settings={},
                request_id="stream-think",
                assistant_message_meta={},
            )
        )

        self.assertEqual(
            [event["event"] for event in events],
            ["start", "reasoning_start", "reasoning_end", "delta", "end"],
        )
        self.assertEqual(events[3]["data"], {"delta": "Visible answer"})
        self.assertEqual(events[-1]["data"]["response"]["message"]["content"], "Visible answer")
        self.assertEqual(
            events[-1]["data"]["response"]["message"]["reasoning_content"],
            "private notes",
        )
        self.assertTrue(events[-1]["data"]["response"]["raw"]["reasoning_content_hidden"])

    def test_iter_stream_events_forwards_structured_runtime_reasoning_to_existing_ui_events(self):
        service = ChatStreamService(
            db_manager=None,
            model_manager=None,
            persistence_service=FakePersistenceService(),
            executor=FakeStreamExecutor(
                [
                    {"type": "reasoning_start"},
                    {"type": "reasoning_delta", "delta": "Private plan"},
                    {"type": "reasoning_end"},
                    {"type": "delta", "delta": "Visible answer"},
                    {
                        "type": "response",
                        "response": {
                            "provider": "llama_cpp",
                            "model": "gemma-thinking",
                            "message": {
                                "role": "assistant",
                                "content": "Visible answer",
                                "reasoning_content": "Private plan",
                            },
                            "usage": {},
                            "finish_reason": "stop",
                            "raw": {},
                        },
                    },
                ]
            ),
            display_delta_delay_seconds=0,
        )

        events = list(
            service.iter_stream_events(
                conversation_id=None,
                provider="llama_cpp",
                input_messages=[{"role": "user", "content": "Hi"}],
                model="gemma-thinking",
                generation_settings={"_reasoning_mode": "on"},
                request_id="stream-structured-reasoning",
                assistant_message_meta={},
            )
        )

        self.assertEqual(
            [event["event"] for event in events],
            ["start", "reasoning_start", "reasoning_end", "delta", "end"],
        )
        self.assertTrue(events[0]["data"]["reasoning_enabled"])
        self.assertEqual(events[0]["data"]["reasoning_mode"], "on")
        self.assertEqual(events[1]["data"], {"reasoning_active": True})
        self.assertEqual(events[2]["data"], {"reasoning_active": False})
        self.assertEqual(
            events[-1]["data"]["response"]["message"]["reasoning_content"],
            "Private plan",
        )

    def test_iter_stream_events_hides_unopened_reasoning_prefix(self):
        service = ChatStreamService(
            db_manager=None,
            model_manager=None,
            persistence_service=FakePersistenceService(),
            executor=FakeStreamExecutor(
                [
                    {"type": "delta", "delta": "private notes\n"},
                    {"type": "delta", "delta": "</think>\n\nVisible answer"},
                    {
                        "type": "response",
                        "response": {
                            "provider": "llama_cpp",
                            "model": "qwen-reasoning",
                            "message": {
                                "role": "assistant",
                                "content": "private notes\n</think>\n\nVisible answer",
                            },
                            "usage": {},
                            "finish_reason": "stop",
                            "raw": {},
                        },
                    },
                ]
            ),
            display_delta_delay_seconds=0,
        )

        events = list(
            service.iter_stream_events(
                conversation_id=None,
                provider="llama_cpp",
                input_messages=[{"role": "user", "content": "Hi"}],
                model="qwen-reasoning",
                generation_settings={},
                request_id="stream-unopened-think",
                assistant_message_meta={},
            )
        )

        self.assertEqual(
            [event["event"] for event in events],
            ["start", "reasoning_start", "reasoning_end", "delta", "end"],
        )
        self.assertEqual(events[3]["data"], {"delta": "Visible answer"})
        self.assertEqual(
            events[-1]["data"]["response"]["message"]["reasoning_content"],
            "private notes",
        )

    def test_iter_stream_events_keeps_unmarked_qwen_content_visible(self):
        service = ChatStreamService(
            db_manager=None,
            model_manager=None,
            persistence_service=FakePersistenceService(),
            executor=FakeStreamExecutor(
                [
                    {"type": "delta", "delta": "Visible answer"},
                    {
                        "type": "response",
                        "response": {
                            "provider": "llama_cpp",
                            "model": "qwen-reasoning",
                            "message": {
                                "role": "assistant",
                                "content": "Visible answer",
                            },
                            "usage": {},
                            "finish_reason": "stop",
                            "raw": {},
                        },
                    },
                ]
            ),
            display_delta_delay_seconds=0,
        )

        events = list(
            service.iter_stream_events(
                conversation_id=None,
                provider="llama_cpp",
                input_messages=[{"role": "user", "content": "Hi"}],
                model="qwen-reasoning",
                generation_settings={},
                request_id="stream-unmarked-qwen",
                assistant_message_meta={},
            )
        )

        self.assertEqual([event["event"] for event in events], ["start", "delta", "end"])
        self.assertEqual(events[1]["data"], {"delta": "Visible answer"})
        self.assertEqual(events[-1]["data"]["response"]["message"]["content"], "Visible answer")

    def test_iter_stream_events_persists_sanitized_reasoning_response(self):
        db = DBManager()
        conversation_id = db.conversations.create(
            title="Reasoning",
            provider="llama_cpp",
            model="qwen-reasoning",
        )
        persistence = FakePersistenceService()
        service = ChatStreamService(
            db_manager=db,
            model_manager=None,
            persistence_service=persistence,
            executor=FakeStreamExecutor(
                [
                    {"type": "delta", "delta": "<think>private</think>Visible"},
                    {
                        "type": "response",
                        "response": {
                            "provider": "llama_cpp",
                            "model": "qwen-reasoning",
                            "message": {
                                "role": "assistant",
                                "content": "<think>private</think>Visible",
                            },
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
                conversation_id=conversation_id,
                provider="llama_cpp",
                input_messages=[{"role": "user", "content": "Hi"}],
                model="qwen-reasoning",
                generation_settings={},
                request_id="stream-persist-think",
                assistant_message_meta={},
            )
        )

        finalized_response = persistence.finalized[0][1]
        self.assertEqual(events[-1]["data"]["response"]["message"]["content"], "Visible")
        self.assertEqual(events[-1]["data"]["response"]["message"]["reasoning_content"], "private")
        self.assertEqual(finalized_response["message"]["content"], "Visible")
        self.assertEqual(finalized_response["message"]["reasoning_content"], "private")

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

    def test_cancel_notifies_active_provider(self):
        model_manager = FakeModelManager()
        service = ChatStreamService(
            db_manager=None,
            model_manager=model_manager,
            persistence_service=FakePersistenceService(),
            executor=FakeStreamExecutor([]),
        )
        events = service.iter_stream_events(
            conversation_id=None,
            provider="llama_cpp",
            input_messages=[{"role": "user", "content": "Hi"}],
            model="runtime-model",
            generation_settings={},
            request_id="stream-provider-cancel",
            assistant_message_meta={},
        )

        self.assertEqual(next(events)["event"], "start")
        self.assertTrue(service.cancel("stream-provider-cancel"))

        list(events)

        self.assertEqual(model_manager.cancelled_providers, ["llama_cpp"])
        self.assertNotIn("stream-provider-cancel", service._active_streams)

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
