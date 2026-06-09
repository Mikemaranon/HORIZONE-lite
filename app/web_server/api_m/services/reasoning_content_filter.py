import re


THINK_OPEN_TAG_PREFIX = "<think"
THINK_CLOSE_TAG = "</think>"


def extract_reasoning_content(content):
    text = str(content or "")
    if not text:
        return "", ""

    reasoning_parts = []

    def replace_complete_match(match):
        reasoning_parts.append(match.group(1))
        return ""

    sanitized = re.sub(
        r"(?is)<think\b[^>]*>(.*?)</think>\s*",
        replace_complete_match,
        text,
    )

    def replace_unopened_prefix(match):
        reasoning_parts.append(match.group(1))
        return ""

    sanitized = re.sub(
        r"(?is)^\s*((?:(?!<think\b).)*?)</think>\s*",
        replace_unopened_prefix,
        sanitized,
        count=1,
    )

    def replace_unclosed_match(match):
        reasoning_parts.append(match.group(1))
        return ""

    sanitized = re.sub(
        r"(?is)<think\b[^>]*>(.*)$",
        replace_unclosed_match,
        sanitized,
    )
    sanitized = re.sub(r"(?is)</think>\s*", "", sanitized)

    if reasoning_parts:
        return sanitized.lstrip(), "\n\n".join(part.strip() for part in reasoning_parts if part.strip())

    return text, ""


def strip_reasoning_content(content):
    sanitized, _reasoning_content = extract_reasoning_content(content)
    return sanitized


def sanitize_chat_response(response):
    if not isinstance(response, dict):
        return response

    message = response.get("message")
    if not isinstance(message, dict):
        return response

    content = message.get("content")
    sanitized_content, extracted_reasoning_content = extract_reasoning_content(content)
    existing_reasoning_content = str(message.get("reasoning_content") or "").strip()
    reasoning_content = existing_reasoning_content or extracted_reasoning_content
    if sanitized_content == content and not reasoning_content:
        return response

    sanitized_response = dict(response)
    sanitized_response["message"] = {
        **message,
        "content": sanitized_content,
    }
    if reasoning_content:
        sanitized_response["message"]["reasoning_content"] = reasoning_content

    raw_response = sanitized_response.get("raw")
    if isinstance(raw_response, dict):
        sanitized_response["raw"] = {
            **raw_response,
            "reasoning_content_hidden": bool(reasoning_content or sanitized_content != content),
        }

    return sanitized_response


class ReasoningStreamFilter:
    def __init__(self, hide_unopened_reasoning_prefix=False):
        self.pending = ""
        self.inside_reasoning = False
        self.emitted_visible_content = False
        self.hidden_reasoning = False
        self.hide_unopened_reasoning_prefix = bool(hide_unopened_reasoning_prefix)
        self.reasoning_parts = []
        self._events = []

    def feed(self, delta):
        self.pending += str(delta or "")
        return self._drain(final=False)

    def flush(self):
        return self._drain(final=True)

    def _drain(self, final):
        output_parts = []

        while self.pending:
            if self.inside_reasoning:
                if not self._capture_until_think_close(final):
                    break
                continue

            marker = self._find_next_marker()
            if not marker:
                self._emit_safe_pending(output_parts, final)
                break

            marker_name, marker_index = marker
            if marker_name == "close":
                self._capture_unopened_reasoning_prefix(marker_index)
                continue

            before_marker = self.pending[:marker_index]
            self._append_visible(output_parts, before_marker)

            tag_end = self.pending.find(">", marker_index)
            if tag_end == -1:
                if final:
                    self.pending = ""
                else:
                    self.pending = self.pending[marker_index:]
                break

            self.pending = self.pending[tag_end + 1:]
            self.inside_reasoning = True
            self.hidden_reasoning = True
            self._events.append({"type": "start"})

        return "".join(output_parts)

    def _capture_until_think_close(self, final):
        close_index = self.pending.lower().find(THINK_CLOSE_TAG)
        if close_index == -1:
            if final:
                self._append_reasoning(self.pending)
                self.pending = ""
                self.inside_reasoning = False
                self._events.append({"type": "end"})
                return True

            tail_length = min(len(self.pending), len(THINK_CLOSE_TAG) - 1)
            capture_length = max(len(self.pending) - tail_length, 0)
            self._append_reasoning(self.pending[:capture_length])
            self.pending = self.pending[capture_length:]
            return False

        self._append_reasoning(self.pending[:close_index])
        self.pending = self.pending[close_index + len(THINK_CLOSE_TAG):]
        self.inside_reasoning = False
        self.hidden_reasoning = True
        self._events.append({"type": "end"})
        if not self.emitted_visible_content:
            self.pending = self.pending.lstrip()
        return True

    def _find_next_marker(self):
        lower_pending = self.pending.lower()
        open_index = lower_pending.find("<think")
        close_index = lower_pending.find(THINK_CLOSE_TAG)

        markers = []
        if open_index != -1:
            markers.append(("open", open_index))
        if close_index != -1 and not self.emitted_visible_content:
            markers.append(("close", close_index))

        if not markers:
            return None

        return min(markers, key=lambda marker: marker[1])

    def _capture_unopened_reasoning_prefix(self, close_index):
        self._events.append({"type": "start"})
        self._append_reasoning(self.pending[:close_index])
        self.pending = self.pending[close_index + len(THINK_CLOSE_TAG):].lstrip()
        self.hidden_reasoning = True
        self._events.append({"type": "end"})

    def _emit_safe_pending(self, output_parts, final):
        if final:
            visible = self.pending
            self.pending = ""
            self._append_visible(output_parts, visible)
            return

        if self.hide_unopened_reasoning_prefix and not self.emitted_visible_content:
            return

        tail_length = self._partial_marker_tail_length()
        safe_length = max(len(self.pending) - tail_length, 0)
        if safe_length <= 0:
            return

        visible = self.pending[:safe_length]
        self.pending = self.pending[safe_length:]
        self._append_visible(output_parts, visible)

    def _partial_marker_tail_length(self):
        lower_pending = self.pending.lower()
        max_tail_length = min(
            len(lower_pending),
            max(len(THINK_OPEN_TAG_PREFIX), len(THINK_CLOSE_TAG)) - 1,
        )

        for tail_length in range(max_tail_length, 0, -1):
            tail = lower_pending[-tail_length:]
            if THINK_OPEN_TAG_PREFIX.startswith(tail) or THINK_CLOSE_TAG.startswith(tail):
                return tail_length

        return 0

    def _append_visible(self, output_parts, content):
        if not content:
            return

        output_parts.append(content)
        if content.strip():
            self.emitted_visible_content = True

    def _append_reasoning(self, content):
        if content:
            self.reasoning_parts.append(content)

    @property
    def reasoning_content(self):
        return "\n\n".join(part.strip() for part in self.reasoning_parts if part.strip())

    def pop_events(self):
        events = self._events
        self._events = []
        return events
