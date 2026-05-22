import json


class ProviderSettingsResolver:
    def __init__(self, db_manager=None):
        self.db_manager = db_manager

    def get_setting(self, key, default=None):
        if not self.db_manager:
            return default

        setting = self.db_manager.settings.get(key)
        if not setting:
            return default

        return setting.get("value", default)

    def get_model_config(self, model_config_id):
        if not self.db_manager or not model_config_id:
            return None

        return self.db_manager.models.get(model_config_id)

    def get_provider_config(self, provider_name=None, model_config_id=None):
        if not self.db_manager:
            return None

        if model_config_id:
            model_config = self.get_model_config(model_config_id)
            if not model_config:
                return None
            return self.db_manager.providers.get(model_config.get("provider_id"))

        if provider_name:
            return self.db_manager.providers.get_first_by_type(provider_name)

        return None

    def get_cloud_api_key(self, provider_name, fallback_key=None, model_config_id=None):
        provider_config = self.get_provider_config(
            provider_name=provider_name,
            model_config_id=model_config_id,
        )
        if provider_config and provider_config.get("api_key"):
            return provider_config["api_key"]

        parsed_keys = self._parse_cloud_api_keys(self.get_setting("openai_api_key"))

        if isinstance(parsed_keys, dict):
            for alias in self._cloud_provider_aliases(provider_name):
                provider_key = parsed_keys.get(alias)
                if provider_key:
                    return provider_key
            return fallback_key

        if parsed_keys:
            return parsed_keys

        return fallback_key

    def get_provider_endpoint(self, provider_name, fallback_endpoint=None, model_config_id=None):
        provider_config = self.get_provider_config(
            provider_name=provider_name,
            model_config_id=model_config_id,
        )
        if provider_config and provider_config.get("endpoint"):
            return str(provider_config["endpoint"]).rstrip("/")

        return fallback_endpoint

    def _parse_cloud_api_keys(self, raw_value):
        if raw_value is None:
            return {}

        if isinstance(raw_value, dict):
            return raw_value

        if not isinstance(raw_value, str):
            return {}

        normalized = raw_value.strip()
        if not normalized:
            return {}

        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            return normalized

        return parsed if isinstance(parsed, dict) else normalized

    def _cloud_provider_aliases(self, provider_name):
        normalized = str(provider_name or "").strip().lower()
        aliases = [normalized]
        if normalized == "openai_compatible":
            aliases.extend(["openai", "cloud"])
        elif normalized == "microsoft_foundry":
            aliases.extend(["microsoft_foundry", "openai_compatible", "openai", "cloud"])
        elif normalized in {"anthropic", "google"}:
            aliases.append("cloud")

        seen = set()
        ordered = []
        for alias in aliases:
            if not alias or alias in seen:
                continue
            seen.add(alias)
            ordered.append(alias)
        return ordered
