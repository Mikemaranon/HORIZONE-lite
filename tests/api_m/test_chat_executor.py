from api_m.services import ChatExecutor
from tests.test_support import IsolatedDatabaseTestCase


class FakeModelManager:
    def __init__(self):
        self.calls = []

    def chat(self, provider, messages, model, settings):
        self.calls.append(("chat", provider, messages, model, settings))
        return {"message": {"role": "assistant", "content": "model response"}}

    def stream_chat(self, provider, messages, model, settings, should_stop=None):
        self.calls.append(("stream_chat", provider, messages, model, settings, should_stop))
        yield {"type": "delta", "delta": "model"}


class FakeToolManager:
    def __init__(self):
        self.calls = []

    def chat(self, provider, messages, model, settings, tool_context=None):
        self.calls.append(("chat", provider, messages, model, settings, tool_context))
        return {"message": {"role": "assistant", "content": "tool response"}}

    def stream_chat(self, provider, messages, model, settings, should_stop=None, tool_context=None):
        self.calls.append(("stream_chat", provider, messages, model, settings, should_stop, tool_context))
        yield {"type": "delta", "delta": "tool"}


class ChatExecutorTests(IsolatedDatabaseTestCase):
    def test_chat_uses_model_manager_without_tool_manager(self):
        model_manager = FakeModelManager()
        executor = ChatExecutor(model_manager)

        response = executor.chat(
            "openai",
            [{"role": "user", "content": "Hello"}],
            "gpt-4.1",
            {"temperature": 0.1},
            tool_context={"ignored": True},
        )

        self.assertEqual(response["message"]["content"], "model response")
        self.assertEqual(model_manager.calls[0][0], "chat")

    def test_chat_and_stream_route_through_tool_manager_when_available(self):
        model_manager = FakeModelManager()
        tool_manager = FakeToolManager()
        executor = ChatExecutor(model_manager, tool_manager=tool_manager)
        tool_context = {"conversation_id": 1}

        response = executor.chat(
            "ollama",
            [{"role": "user", "content": "Search"}],
            "qwen3",
            {},
            tool_context=tool_context,
        )
        events = list(
            executor.stream_chat(
                "ollama",
                [{"role": "user", "content": "Search"}],
                "qwen3",
                {},
                should_stop=lambda: False,
                tool_context=tool_context,
            )
        )

        self.assertEqual(response["message"]["content"], "tool response")
        self.assertEqual(events, [{"type": "delta", "delta": "tool"}])
        self.assertEqual(model_manager.calls, [])
        self.assertEqual(tool_manager.calls[0][-1], tool_context)
        self.assertEqual(tool_manager.calls[1][-1], tool_context)
