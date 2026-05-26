import json
import re
from dataclasses import dataclass


class ToolCallParseError(ValueError):
    pass


@dataclass(frozen=True)
class ToolCallRequest:
    name: str
    arguments: dict
    reason: str = ""

    def to_payload(self):
        payload = {
            "name": self.name,
            "arguments": self.arguments,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class ToolDecision:
    needs_tool: bool
    tool_call: ToolCallRequest | None = None
    reason: str = ""


class ToolCallParser:
    def parse_response(self, response):
        content = str((response.get("message") or {}).get("content", "")).strip()
        return self.parse_text(content)

    def parse_text(self, content):
        normalized_content = self._strip_markdown_fences(str(content or "").strip())
        if not normalized_content:
            return None

        payload = self._extract_json_payload(normalized_content)
        if not isinstance(payload, dict) or "tool_call" not in payload:
            return None

        tool_call = payload.get("tool_call")
        if not isinstance(tool_call, dict):
            raise ToolCallParseError("tool_call must be an object.")

        name = str(tool_call.get("name") or "").strip()
        if not name:
            raise ToolCallParseError("tool_call.name is required.")

        arguments = tool_call.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ToolCallParseError("tool_call.arguments must be an object.")

        reason = str(tool_call.get("reason") or "").strip()
        return ToolCallRequest(name=name, arguments=arguments, reason=reason)

    def parse_decision_response(self, response):
        content = str((response.get("message") or {}).get("content", "")).strip()
        return self.parse_decision_text(content)

    def parse_decision_text(self, content):
        normalized_content = self._strip_markdown_fences(str(content or "").strip())
        if not normalized_content:
            return None

        payload = self._extract_json_payload(normalized_content)
        if not isinstance(payload, dict):
            return None

        if "tool_call" in payload:
            tool_call = self.parse_text(normalized_content)
            return ToolDecision(
                needs_tool=True,
                tool_call=tool_call,
                reason=tool_call.reason if tool_call else "",
            )

        tool_decision = payload.get("tool_decision")
        if not isinstance(tool_decision, dict):
            return None

        needs_tool = bool(tool_decision.get("needs_tool"))
        reason = str(tool_decision.get("reason") or "").strip()
        if not needs_tool:
            return ToolDecision(needs_tool=False, reason=reason)

        raise ToolCallParseError(
            "tool_decision.needs_tool=true must be represented as a top-level tool_call."
        )

    def _strip_markdown_fences(self, content):
        if not content.startswith("```"):
            return content

        lines = content.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()

        return content

    def _extract_json_payload(self, content):
        try:
            payload = json.loads(content)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for index, character in enumerate(content):
            if character != "{":
                continue

            try:
                payload, _ = decoder.raw_decode(content[index:])
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                return payload

        return self._extract_wrapped_tool_call(content)

    def _extract_wrapped_tool_call(self, content):
        match = re.search(r'"tool_call"\s*:\s*(\{.*\})', content, flags=re.DOTALL)
        if not match:
            return None

        wrapped = "{" + match.group(0).strip() + "}"
        try:
            payload = json.loads(wrapped)
        except json.JSONDecodeError:
            return None

        return payload if isinstance(payload, dict) else None
