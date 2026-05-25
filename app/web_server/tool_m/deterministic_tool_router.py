import re


class DeterministicToolRouter:
    EXPLICIT_SEARCH_PATTERNS = [
        r"^(por favor\s+)?busca(?:me|r)?\s+",
        r"^(por favor\s+)?buscar\s+",
        r"^(por favor\s+)?encuentra\s+",
        r"^(por favor\s+)?investiga\s+",
        r"^(please\s+)?search\s+",
        r"^(please\s+)?look up\s+",
        r"^(please\s+)?find\s+",
    ]
    DATE_TIME_TRIGGERS = [
        "que fecha es",
        "qué fecha es",
        "fecha actual",
        "fecha de hoy",
        "dia de hoy",
        "día de hoy",
        "que dia es hoy",
        "qué día es hoy",
        "que hora es",
        "qué hora es",
        "hora actual",
        "what is the date",
        "what's the date",
        "what date is it",
        "what is today's date",
        "what's today's date",
        "what day is it",
        "what time is it",
        "today's date",
        "current date",
        "current time",
    ]
    DATE_TIME_REGEX_PATTERNS = [
        r"\b(?:what(?:'s| is)?\s+)?today'?s\s+date\b",
        r"\bwhat(?:'s| is)?\s+the\s+(?:current\s+)?date\b",
        r"\bwhat(?:'s| is)?\s+the\s+(?:current\s+)?time\b",
        r"\bwhat(?:'s| is)?\s+the\s+time\s+today\b",
        r"\b(?:qué|que)\s+fecha\s+es(?:\s+hoy)?\b",
        r"\bfecha\s+actual\b",
        r"\bfecha\s+de\s+hoy\b",
        r"\b(?:qué|que)\s+(?:día|dia)\s+es(?:\s+hoy)?\b",
        r"\b(?:qué|que)\s+hora\s+es(?:\s+ahora|\s+hoy)?\b",
        r"\bhora\s+actual\b",
    ]
    FRESHNESS_HINTS = [
        "latest",
        "current",
        "today",
        "recent",
        "recently",
        "currently",
        "breaking",
        "news",
        "actual",
        "actualidad",
        "último",
        "ultima",
        "última",
        "reciente",
        "recientemente",
        "hoy",
        "ahora",
        "now",
        "last time",
        "last played",
        "played last",
        "when did",
        "when was",
        "cuándo",
        "cuando",
        "cuándo fue",
        "cuando fue",
        "cuándo jugó",
        "cuando jugó",
        "when did they play",
    ]
    CORRECTION_HINTS = [
        "incorrect",
        "wrong",
        "you didnt look it up",
        "you didn't look it up",
        "you did not look it up",
        "not looked up",
        "check again",
        "verify",
        "verify it",
        "fact check",
        "fact-check",
        "use internet",
        "use the internet",
        "use web",
        "search it",
        "look it up",
        "míralo",
        "miralo",
        "compruébalo",
        "compruebalo",
        "verificalo",
        "verifícalo",
        "búscalo",
        "buscalo",
        "usa internet",
        "usa la web",
    ]
    MONTH_NAMES = (
        "january february march april may june july august september october november december "
        "enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre"
    ).split()
    WEEKDAY_NAMES = (
        "monday tuesday wednesday thursday friday saturday sunday "
        "lunes martes miércoles miercoles jueves viernes sábado sabado domingo"
    ).split()
    WORKSPACE_CREATE_FILE_PATTERNS = [
        r"\bcrea(?:r)?\s+(?:un\s+)?archivo\b",
        r"\bcrear\s+(?:un\s+)?archivo\b",
        r"\bgenera(?:r)?\s+(?:un\s+)?archivo\b",
        r"\bguarda(?:r)?\s+(?:un\s+)?archivo\b",
        r"\bcreate\s+(?:a\s+)?file\b",
        r"\bwrite\s+(?:a\s+)?file\b",
        r"\bsave\s+(?:a\s+)?file\b",
    ]
    FILE_PATH_PATTERN = re.compile(
        r"(?P<path>(?:[\w.-]+/)*[\w.-]+\.[A-Za-z0-9_+-]{1,12})"
    )

    def resolve(self, messages, active_tools):
        active_tool_names = {
            str(tool.get("name") or "").strip()
            for tool in (active_tools or [])
            if tool.get("name")
        }
        last_user_message = self._get_last_user_message(messages)
        previous_user_message = self._extract_previous_user_message(messages)
        if not last_user_message:
            return None

        if "workspace_write_file" in active_tool_names:
            workspace_write_call = self._resolve_workspace_write_file(last_user_message)
            if workspace_write_call:
                return workspace_write_call

        if "current_date" in active_tool_names and self._should_force_current_date(last_user_message):
            return {
                "name": "current_date",
                "arguments": {},
            }

        if "web_search" in active_tool_names:
            query = self._extract_forced_web_search_query(last_user_message)
            if query:
                return {
                    "name": "web_search",
                    "arguments": {
                        "query": query,
                        "max_results": 5,
                    },
                }

            query = self._resolve_correction_search_query(
                last_user_message,
                previous_user_message,
            )
            if query:
                return {
                    "name": "web_search",
                    "arguments": {
                        "query": query,
                        "max_results": 5,
                    },
                }

            if self._should_force_web_search(last_user_message):
                return {
                    "name": "web_search",
                    "arguments": {
                        "query": self._normalize_search_query(last_user_message),
                        "max_results": 5,
                    },
                }

        return None

    def _resolve_workspace_write_file(self, content):
        normalized = str(content or "").strip()
        lowered = normalized.lower()
        if not normalized:
            return None

        if not any(re.search(pattern, lowered) for pattern in self.WORKSPACE_CREATE_FILE_PATTERNS):
            return None

        path = self._extract_file_path(normalized)
        if not path:
            return None

        return {
            "name": "workspace_write_file",
            "arguments": {
                "path": path,
                "content": self._resolve_workspace_file_content(path, normalized),
                "overwrite": False,
                "create_dirs": "/" in path,
            },
        }

    def _extract_file_path(self, content):
        match = self.FILE_PATH_PATTERN.search(content)
        if not match:
            return ""

        path = match.group("path").strip().strip("`'\".,:;!?")
        return path.lstrip("/")

    def _resolve_workspace_file_content(self, path, content):
        explicit_content = self._extract_explicit_file_content(content)
        if explicit_content:
            return explicit_content

        filename = path.rsplit("/", 1)[-1].lower()
        if filename in {"helloworld.sh", "hello-world.sh"}:
            return "#!/usr/bin/env bash\necho \"Hello, world!\"\n"

        if path.lower().endswith(".sh"):
            return "#!/usr/bin/env bash\n"

        return ""

    def _extract_explicit_file_content(self, content):
        fenced_match = re.search(r"```(?:[A-Za-z0-9_+-]+)?\n(.*?)```", content, flags=re.DOTALL)
        if fenced_match:
            return fenced_match.group(1)

        quoted_match = re.search(
            r"(?:contenido|content)\s*(?:necesario)?\s*(?:es|:|=)\s*['\"](?P<content>.*?)['\"]",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if quoted_match:
            return quoted_match.group("content")

        return ""

    def _get_last_user_message(self, messages):
        for message in reversed(messages or []):
            if message.get("role") == "user":
                return str(message.get("content") or "").strip()
        return ""

    def _extract_forced_web_search_query(self, content):
        normalized = str(content or "").strip()
        if not normalized:
            return ""

        lowered = normalized.lower()
        if not any(re.match(pattern, lowered) for pattern in self.EXPLICIT_SEARCH_PATTERNS):
            return ""

        query = re.sub(
            r"^(por favor\s+)?(busca(?:me|r)?|buscar|encuentra|investiga|search|look up|find)\s+",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        query = re.sub(
            r"^(en internet|por internet|en la web|online|on the web)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        )
        return query.strip(" .,:;!?")

    def _should_force_current_date(self, content):
        lowered = str(content or "").strip().lower()
        if not lowered:
            return False

        if any(trigger in lowered for trigger in self.DATE_TIME_TRIGGERS):
            return True

        return any(
            re.search(pattern, lowered)
            for pattern in self.DATE_TIME_REGEX_PATTERNS
        )

    def _resolve_correction_search_query(self, current_user_message, previous_user_message):
        if not self._contains_correction_hint(current_user_message):
            return ""

        previous_query = self._normalize_search_query(previous_user_message)
        if previous_query:
            return previous_query

        current_query = self._normalize_search_query(current_user_message)
        return current_query

    def _contains_correction_hint(self, content):
        lowered = str(content or "").strip().lower()
        if not lowered:
            return False

        return any(hint in lowered for hint in self.CORRECTION_HINTS)

    def _should_force_web_search(self, content):
        lowered = str(content or "").strip().lower()
        if not lowered:
            return False

        if any(hint in lowered for hint in self.FRESHNESS_HINTS):
            return True

        if re.search(r"\b(19|20)\d{2}\b", lowered):
            return True

        if re.search(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", lowered):
            return True

        if any(month in lowered for month in self.MONTH_NAMES):
            return True

        if any(day in lowered for day in self.WEEKDAY_NAMES):
            return True

        return False

    def _normalize_search_query(self, content):
        normalized = str(content or "").strip()
        if not normalized:
            return ""

        query = re.sub(
            r"^(por favor\s+)?(use internet|use the internet|use web|search it|look it up|"
            r"incorrect|wrong|check again|verify( it)?|fact[- ]check|"
            r"usa internet|usa la web|búscalo|buscalo|míralo|miralo|"
            r"compruébalo|compruebalo|verificalo|verifícalo)\b[\s,:-]*",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        return query.strip(" .,:;!?")

    def _extract_previous_user_message(self, messages):
        system_message = self._get_system_message(messages)
        if not system_message:
            return ""

        matches = re.findall(
            r"\[Previous user message\]\nContent:\n(.*?)(?=\n\n\[Previous |\n\nTool provenance rule:|\Z)",
            system_message,
            flags=re.DOTALL,
        )
        if not matches:
            return ""

        return str(matches[-1]).strip()

    def _get_system_message(self, messages):
        for message in messages or []:
            if message.get("role") == "system":
                return str(message.get("content") or "")
        return ""
