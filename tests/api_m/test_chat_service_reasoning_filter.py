from types import SimpleNamespace
import unittest

from api_m.services import ChatService


class FakeRequestPreparer:
    def prepare(self, data, default_profile, default_provider):
        return SimpleNamespace(
            conversation=None,
            conversation_id=None,
            provider="llama_cpp",
            input_messages=[{"role": "user", "content": "Hola"}],
            request_messages=[{"role": "user", "content": "Hola"}],
            model="qwen-reasoning",
            generation_settings={},
            stream_requested=False,
            request_id="chat-reasoning",
            assistant_message_meta={},
            project=None,
            tool_confirmation=None,
        )


class FakeSourceAttributionService:
    def build_follow_up_response(self, **kwargs):
        return None


class FakeExecutor:
    def chat(self, provider, messages, model, settings, tool_context=None):
        return {
            "provider": provider,
            "model": model,
            "message": {
                "role": "assistant",
                "content": "<think>private notes</think>\n\nRespuesta visible",
            },
            "usage": {},
            "finish_reason": "stop",
            "raw": {},
        }


class ChatServiceReasoningFilterTests(unittest.TestCase):
    def test_handle_request_sanitizes_non_streaming_reasoning_response(self):
        service = ChatService(
            db_manager=None,
            model_manager=None,
            context_builder=None,
            persistence_service=None,
            stream_service=SimpleNamespace(resolve_request_id=lambda value: value),
            source_attribution_service=FakeSourceAttributionService(),
            request_preparer=FakeRequestPreparer(),
            executor=FakeExecutor(),
        )

        payload = service.handle_request({}, default_profile=None, default_provider="llama_cpp")

        self.assertEqual(
            payload["response"]["message"]["content"],
            "Respuesta visible",
        )
        self.assertEqual(
            payload["response"]["message"]["reasoning_content"],
            "private notes",
        )
        self.assertTrue(payload["response"]["raw"]["reasoning_content_hidden"])
