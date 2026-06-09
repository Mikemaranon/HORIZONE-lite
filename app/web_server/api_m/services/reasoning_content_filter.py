import re


THINK_OPEN_TAG_PREFIX = "<think"
THINK_CLOSE_TAG = "</think>"


def strip_reasoning_content(content):
    text = str(content or "")
    if not text:
        return ""

    sanitized = re.sub(r"(?is)<think\b[^>]*>.*?</think>\s*", "", text)
    sanitized = re.sub(r"(?is)^\s*(?:(?!<think\b).)*?</think>\s*", "", sanitized, count=1)
    sanitized = re.sub(r"(?is)<think\b[^>]*>.*$", "", sanitized)
    sanitized = re.sub(r"(?is)</think>\s*", "", sanitized)

    if sanitized != text:
        return sanitized.lstrip()

    return text


def sanitize_chat_response(response):
    if not isinstance(response, dict):
        return response

    message = response.get("message")
    if not isinstance(message, dict):
        return response

    content = message.get("content")
    sanitized_content = strip_reasoning_content(content)
    if sanitized_content == content:
        return response

    sanitized_response = dict(response)
    sanitized_response["message"] = {
        **message,
        "content": sanitized_content,
    }

    raw_response = sanitized_response.get("raw")
    if isinstance(raw_response, dict):
        sanitized_response["raw"] = {
            **raw_response,
            "reasoning_content_hidden": True,
        }

    return sanitized_response


class ReasoningStreamFilter:
    def __init__(self, hide_unopened_reasoning_prefix=False):
        self.pending = ""
        self.inside_reasoning = False
        self.emitted_visible_content = False
        self.hidden_reasoning = False
        self.hide_unopened_reasoning_prefix = bool(hide_unopened_reasoning_prefix)

    def feed(self, delta):
        self.pending += str(delta or "")
        return self._drain(final=False)

    def flush(self):
        return self._drain(final=True)

    def _drain(self, final):
        output_parts = []

        while self.pending:
            if self.inside_reasoning:
                if not self._discard_until_think_close(final):
                    break
                continue

            marker = self._find_next_marker()
            if not marker:
                self._emit_safe_pending(output_parts, final)
                break

            marker_name, marker_index = marker
            if marker_name == "close":
                self._discard_unopened_reasoning_prefix(marker_index)
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

        return "".join(output_parts)

    def _discard_until_think_close(self, final):
        close_index = self.pending.lower().find(THINK_CLOSE_TAG)
        if close_index == -1:
            if final:
                self.pending = ""
                self.inside_reasoning = False
                return True

            self.pending = self.pending[-(len(THINK_CLOSE_TAG) - 1):]
            return False

        self.pending = self.pending[close_index + len(THINK_CLOSE_TAG):]
        self.inside_reasoning = False
        self.hidden_reasoning = True
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

    def _discard_unopened_reasoning_prefix(self, close_index):
        self.pending = self.pending[close_index + len(THINK_CLOSE_TAG):].lstrip()
        self.hidden_reasoning = True

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
