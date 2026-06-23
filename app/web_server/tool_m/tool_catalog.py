import json


class ToolCatalog:
    def __init__(self, tools=None):
        self._tools = {
            str(tool.get("name") or "").strip(): self._normalize_tool(tool)
            for tool in (tools or [])
            if str(tool.get("name") or "").strip()
        }

    def __bool__(self):
        return bool(self._tools)

    def __iter__(self):
        return iter(self.tools)

    @property
    def tools(self):
        return list(self._tools.values())

    def names(self):
        return set(self._tools.keys())

    def get(self, tool_name):
        return self._tools.get(str(tool_name or "").strip())

    def build_messages(self, messages):
        tool_instructions = self.to_system_prompt()
        if not tool_instructions:
            return [*list(messages or [])]

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
            *list(messages or []),
        ]

    def build_planning_messages(self, messages):
        tool_instructions = self.to_planning_system_prompt()
        if not tool_instructions:
            return [*list(messages or [])]

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
            *list(messages or []),
        ]

    def build_answer_messages(self, messages):
        tool_instructions = self.to_answer_system_prompt()
        if not tool_instructions:
            return [*list(messages or [])]

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
            *list(messages or []),
        ]

    def build_forced_planning_messages(self, messages, tool_name, instruction=""):
        runtime_tool = self.get(tool_name)
        if not runtime_tool:
            return [*list(messages or [])]

        tool_payload = json.dumps(
            self._to_model_payload(runtime_tool),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        command_instruction = str(instruction or "").strip() or "No extra instruction was provided."
        argument_example = self._build_argument_example(runtime_tool.get("parameters") or {})
        response_example = json.dumps(
            {
                "tool_call": {
                    "name": tool_name,
                    "arguments": argument_example,
                    "reason": "brief reason",
                }
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        prompt = "\n".join(
            [
                f"The user explicitly invoked /{tool_name}.",
                "Tool selection is complete. Prepare arguments for this tool only.",
                "Do not choose another tool and do not answer the user's request yet.",
                "Use earlier tool results in the conversation when they help prepare these arguments.",
                "Replace every placeholder with a concrete value inferred from the command instruction.",
                f"Reply with only: {response_example}",
                f"Command instruction: {command_instruction}",
                "Selected tool:",
                tool_payload,
            ]
        )
        if messages and messages[0].get("role") == "system":
            merged = {
                **messages[0],
                "content": f"{messages[0].get('content', '').strip()}\n\n{prompt}".strip(),
            }
            return [merged, *list(messages[1:])]
        return [{"role": "system", "content": prompt}, *list(messages or [])]

    def _build_argument_example(self, parameters):
        example = {}
        for name, schema in parameters.items():
            if not isinstance(schema, dict):
                continue
            if "default" in schema:
                example[name] = schema["default"]
                continue
            if not schema.get("required"):
                continue
            parameter_type = str(schema.get("type") or "value").strip()
            example[name] = f"<required {parameter_type}>"
        return example

    def to_system_prompt(self):
        if not self._tools:
            return ""

        return "\n".join(
            [
                "You have access to tools for this turn.",
                "",
                "Use a tool when the user's task needs external information, current state, local workspace evidence, or a verifiable action.",
                "Do not invent tool results. If a tool is needed, reply with only one JSON object and no markdown.",
                'Use this shape: {"tool_call":{"name":"tool_name","arguments":{},"reason":"brief reason"}}',
                "Populate every required argument from the selected tool schema. Use an empty arguments object only when that tool has no parameters.",
                "If no tool is needed, answer normally in the user's language.",
                "After a tool result is provided, use it to continue. Request another tool only if the result shows another action is necessary.",
                "",
                "Available tools:",
                self.to_model_json(),
            ]
        )

    def to_answer_system_prompt(self):
        if not self._tools:
            return ""

        return "\n".join(
            [
                "Tool planning is complete for this step.",
                "Answer the user normally in their language.",
                "Do not emit tool_call JSON in this answer.",
                "Use tool results only if they already appear in the conversation context.",
                "Do not claim that a tool was used unless a tool result is present.",
                "If the latest tool result has ok false, report that failure and do not make factual claims that depend on the failed tool.",
                "",
                "Tools considered during planning:",
                self.to_model_json(),
            ]
        )

    def to_planning_system_prompt(self):
        if not self._tools:
            return ""

        return "\n".join(
            [
                "You have access to tools for this turn.",
                "",
                "First decide whether the user's task needs a tool. This is a planning step only.",
                "Planning does not execute tools, change files, call external services, or perform the user request.",
                "Reply with only one JSON object and no markdown.",
                "",
                "When a tool is needed, use this exact shape:",
                '{"tool_call":{"name":"tool_name","arguments":{},"reason":"brief reason"}}',
                "Populate every required argument from the selected tool schema. Use an empty arguments object only when that tool has no parameters.",
                "",
                "When no tool is needed, use this exact shape:",
                '{"tool_decision":{"needs_tool":false,"reason":"brief reason"}}',
                "",
                "Decision rules:",
                "- Use a tool when the task needs external information, current state, local workspace evidence, or a verifiable action.",
                "- Returning a tool_call for a tool with risk_level writes_workspace only proposes the action; the app will require explicit user confirmation before execution.",
                "- Do not refuse benign local workspace file requests during planning merely because they create, replace, append, or update files. Choose the appropriate available tool when the user's intent and required arguments are clear.",
                "- If a requested tool action is ambiguous or missing required arguments, use tool_decision with needs_tool false and a brief reason.",
                "- Do not answer the user's actual request during this planning step.",
                "- Do not invent tool results.",
                "- Only request one tool at a time.",
                "",
                "Available tools:",
                self.to_model_json(),
            ]
        )

    def to_model_json(self):
        return json.dumps(
            [self._to_model_payload(tool) for tool in self.tools],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _normalize_tool(self, tool):
        normalized_tool = dict(tool)
        normalized_tool["name"] = str(normalized_tool.get("name") or "").strip()
        normalized_tool["display_name"] = (
            str(normalized_tool.get("display_name") or normalized_tool["name"])
            .strip()
        )
        normalized_tool["description"] = str(normalized_tool.get("description") or "").strip()
        normalized_tool["parameters"] = (
            normalized_tool.get("parameters")
            if isinstance(normalized_tool.get("parameters"), dict)
            else {}
        )
        normalized_tool["capabilities"] = self._normalize_string_list(
            normalized_tool.get("capabilities")
        )
        normalized_tool["use_when"] = self._normalize_string_list(
            normalized_tool.get("use_when")
        )
        normalized_tool["risk_level"] = (
            str(normalized_tool.get("risk_level") or "read_only").strip()
            or "read_only"
        )
        return normalized_tool

    def _to_model_payload(self, tool):
        return {
            "name": tool["name"],
            "display_name": tool["display_name"],
            "description": tool["description"],
            "capabilities": tool["capabilities"],
            "use_when": tool["use_when"],
            "risk_level": tool["risk_level"],
            "parameters": tool["parameters"],
        }

    def _normalize_string_list(self, raw_value):
        if not isinstance(raw_value, (list, tuple)):
            return []

        return [
            str(item).strip()
            for item in raw_value
            if str(item).strip()
        ]
