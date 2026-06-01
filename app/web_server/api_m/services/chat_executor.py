class ChatExecutor:
    def __init__(self, model_manager, tool_manager=None):
        self.model_manager = model_manager
        self.tool_manager = tool_manager

    def chat(self, provider, messages, model, settings, tool_context=None):
        if self.tool_manager:
            return self.tool_manager.chat(
                provider,
                messages,
                model,
                settings,
                tool_context=tool_context,
            )

        return self.model_manager.chat(
            provider,
            messages,
            model,
            settings,
        )

    def stream_chat(self, provider, messages, model, settings, should_stop=None, tool_context=None):
        if self.tool_manager:
            return self.tool_manager.stream_chat(
                provider,
                messages,
                model,
                settings,
                should_stop=should_stop,
                tool_context=tool_context,
            )

        return self.model_manager.stream_chat(
            provider,
            messages,
            model,
            settings,
            should_stop=should_stop,
        )
