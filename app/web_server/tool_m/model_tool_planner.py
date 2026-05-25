import json


class ModelToolPlanner:
    TOOL_CALL_SYSTEM_PROMPT = """You may use external tools when they are available.

If a tool is needed, reply with ONLY a JSON object using this exact shape:
{"tool_call":{"name":"tool_name","arguments":{"key":"value"}}}

Rules:
- Do not wrap the JSON in markdown fences.
- Do not include explanation before or after the JSON object.
- Only request one tool at a time.
- If no tool is needed, answer the user normally.
"""

    GENERIC_PLANNER_HINTS = [
        "search",
        "find",
        "look up",
        "investiga",
        "busca",
        "encuentra",
        "web",
        "internet",
        "online",
        "date",
        "day",
        "time",
        "today",
        "fecha",
        "dia",
        "día",
        "hora",
        "incorrect",
        "wrong",
        "check again",
        "verify",
        "fact check",
        "fact-check",
        "latest",
        "current",
        "recent",
        "when did",
        "when was",
        "last time",
        "cuándo",
        "cuando",
        "latest",
        "news",
        "source",
        "sources",
        "tool",
        "tools",
    ]

    def should_plan(self, messages, active_tools):
        last_user_message = self._get_last_user_message(messages).lower()
        if not last_user_message or not active_tools:
            return False

        if any(hint in last_user_message for hint in self.GENERIC_PLANNER_HINTS):
            return True

        if self._contains_temporal_marker(last_user_message):
            return True

        for tool in active_tools:
            name = str(tool.get("name") or "").replace("_", " ").strip().lower()
            display_name = str(tool.get("display_name") or "").strip().lower()
            if (name and name in last_user_message) or (display_name and display_name in last_user_message):
                return True

        return False

    def build_messages(self, messages, active_tools):
        tools_context = "\n".join(
            [
                self._build_tool_catalog_line(tool)
                for tool in active_tools
            ]
        )
        tool_instructions = (
            f"{self.TOOL_CALL_SYSTEM_PROMPT}\nAvailable tools:\n{tools_context}"
        )

        if messages and messages[0].get("role") == "system":
            merged_system_message = {
                **messages[0],
                "content": (
                    f"{messages[0].get('content', '').strip()}\n\n{tool_instructions}"
                ).strip(),
            }
            return [merged_system_message, *messages[1:]]

        return [
            {
                "role": "system",
                "content": tool_instructions,
            },
            *messages,
        ]

    def _build_tool_catalog_line(self, tool):
        parameters = tool.get("parameters") or {}
        parameter_names = [
            str(name).strip()
            for name in parameters.keys()
            if str(name).strip()
        ]
        parameter_label = ", ".join(parameter_names) if parameter_names else "none"
        description = str(tool.get("description") or "").strip()
        compact_description = " ".join(description.split())

        payload = {
            "name": str(tool.get("name") or "").strip(),
            "description": compact_description,
            "parameters": parameter_label,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _get_last_user_message(self, messages):
        for message in reversed(messages or []):
            if message.get("role") == "user":
                return str(message.get("content") or "").strip()
        return ""

    def _contains_temporal_marker(self, content):
        if not content:
            return False

        import re

        if re.search(r"\b(19|20)\d{2}\b", content):
            return True

        if re.search(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", content):
            return True

        return False
