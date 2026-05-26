class ConversationTitleService:
    TITLE_GENERATION_PROMPT = (
        "Generate a short, natural title for a chat after reading the first user message "
        "and the assistant's first response. Capture the real topic or outcome, not just "
        "the user's wording. Reply only with the title, without quotes or final punctuation, "
        "using between 2 and 6 words and in the dominant language of the exchange."
    )

    def generate_title(self, provider, model, title_context, settings=None):
        title_settings = {
            "temperature": 0.3,
            "max_tokens": 24,
        }
        if settings:
            title_settings.update(settings)

        response = provider.chat(
            [
                {
                    "role": "system",
                    "content": self.TITLE_GENERATION_PROMPT,
                },
                {
                    "role": "user",
                    "content": self._build_title_context(title_context),
                },
            ],
            model,
            title_settings,
        )
        raw_title = (response.get("message") or {}).get("content", "")
        return self._sanitize_generated_title(raw_title)

    def _build_title_context(self, title_context):
        if isinstance(title_context, list):
            lines = ["First exchange:"]
            for message in title_context:
                if not isinstance(message, dict):
                    continue

                role = str(message.get("role") or "").strip().lower()
                content = " ".join(str(message.get("content") or "").split())
                if not role or not content:
                    continue

                label = "User" if role == "user" else "Assistant"
                lines.append(f"{label}: {content}")

            lines.append("")
            lines.append("Title:")
            return "\n".join(lines).strip()

        content = " ".join(str(title_context or "").split())
        return f"First user message:\n{content}\n\nTitle:".strip()

    def _sanitize_generated_title(self, raw_title):
        normalized = str(raw_title or "").strip()
        if not normalized:
            return ""

        normalized = normalized.replace("\r", " ").replace("\n", " ")
        normalized = " ".join(normalized.split())
        normalized = normalized.strip(" \"'`#*_-:.")
        for prefix in ["title:", "título:", "titulo:"]:
            if normalized.lower().startswith(prefix):
                normalized = normalized[len(prefix):].strip(" \"'`#*_-:.")
                break

        if len(normalized) > 80:
            normalized = normalized[:80].rstrip()

        return normalized
