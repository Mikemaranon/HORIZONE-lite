import json


class ToolExecutionTrace:
    def build_tool_event(self, tool_call, result_payload, *, runtime_tool=None, policy_decision=None):
        return {
            "tool_name": tool_call.name,
            "tool_display_name": self.resolve_display_name(tool_call.name, runtime_tool),
            "reason": tool_call.reason,
            "arguments": tool_call.arguments,
            "policy": policy_decision or {},
            **result_payload,
        }

    def build_exchange_messages(self, tool_call, tool_event):
        return [
            {
                "role": "assistant",
                "content": json.dumps(
                    {"tool_call": tool_call.to_payload()},
                    ensure_ascii=False,
                ),
            },
            {
                "role": "user",
                "content": self.build_tool_result_message(tool_call.name, tool_event),
            },
        ]

    def build_tool_result_message(self, tool_name, tool_event):
        return (
            f"Tool result for {tool_name}:\n"
            f"{json.dumps(tool_event, ensure_ascii=False, sort_keys=True)}\n"
            "Use this result to continue helping the user. "
            "If you still need another tool, request it using the exact JSON contract."
        )

    def resolve_display_name(self, tool_name, runtime_tool=None):
        if runtime_tool and runtime_tool.get("display_name"):
            return str(runtime_tool["display_name"]).strip()

        return str(tool_name or "tool").replace("_", " ").strip()
