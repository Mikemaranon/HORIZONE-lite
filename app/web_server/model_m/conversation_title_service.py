class ConversationTitleService:
    TITLE_GENERATION_PROMPT = (
        "Generate a short title for a conversation based on the user's first message. "
        "Reply only with the title, without quotes or final punctuation, using between 2 and 6 words "
        "and in the dominant language of the message."
    )

    def generate_title(self, provider, model, first_user_message, settings=None):
        title_settings = {
            "temperature": 0.2,
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
                    "content": (first_user_message or "").strip(),
                },
            ],
            model,
            title_settings,
        )
        raw_title = (response.get("message") or {}).get("content", "")
        return self._sanitize_generated_title(raw_title)

    def _sanitize_generated_title(self, raw_title):
        normalized = str(raw_title or "").strip()
        if not normalized:
            return ""

        normalized = normalized.replace("\r", " ").replace("\n", " ")
        normalized = " ".join(normalized.split())
        normalized = normalized.strip(" \"'`#*_-:.")

        if len(normalized) > 80:
            normalized = normalized[:80].rstrip()

        return normalized
