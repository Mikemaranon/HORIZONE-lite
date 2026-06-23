import re


TOOL_COMMAND_PATTERN = re.compile(r"/([a-z][a-z0-9_]*)", re.IGNORECASE)
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ToolCommandParser:
    def parse(self, content):
        text = str(content or "")
        matches = []
        for match in TOOL_COMMAND_PATTERN.finditer(text):
            start = match.start()
            previous_character = text[start - 1] if start > 0 else ""
            following_character = text[match.end()] if match.end() < len(text) else ""
            if previous_character and not self._is_start_boundary(previous_character):
                continue
            if following_character and not self._is_end_boundary(following_character):
                continue
            matches.append(
                {
                    "tool_name": match.group(1).lower(),
                    "start": start,
                    "command_end": match.end(),
                }
            )

        directives = []
        for index, match in enumerate(matches):
            end = matches[index + 1]["start"] if index + 1 < len(matches) else len(text)
            directives.append(
                {
                    "tool_name": match["tool_name"],
                    "instruction": text[match["command_end"]:end].strip(),
                    "start": match["start"],
                    "end": end,
                }
            )
        return directives

    def _is_start_boundary(self, character):
        return character.isspace() or character in "([{"

    def _is_end_boundary(self, character):
        return character.isspace() or character in ",.;:!?)"
