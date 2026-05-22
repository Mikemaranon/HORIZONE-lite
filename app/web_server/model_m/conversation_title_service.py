class ConversationTitleService:
    TITLE_GENERATION_PROMPT = (
        "Genera un titulo corto para una conversacion a partir del primer mensaje del usuario. "
        "Responde solo con el titulo, sin comillas ni puntuacion final, usando entre 2 y 6 palabras "
        "y en el idioma dominante del mensaje."
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
