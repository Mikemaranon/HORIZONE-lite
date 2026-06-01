from .service_errors import ConflictError, RequestError, ResourceNotFoundError


class ProviderConfigService:
    SUPPORTED_PROVIDER_TYPES = {"mlx", "ollama", "cloud"}

    def __init__(self, db_manager, model_manager):
        self.db = db_manager
        self.model_manager = model_manager

    def list_providers(self):
        return [self.serialize_public_provider(provider) for provider in self.db.providers.all()]

    def get_provider(self, provider_id):
        parsed_id = self._parse_required_id(provider_id, "id")
        provider = self.db.providers.get(parsed_id)
        if not provider:
            raise ResourceNotFoundError("Provider not found")
        return self.serialize_public_provider(provider)

    def create_provider(self, data):
        provider_data = self._parse_provider_payload(data)
        provider_id = self.db.providers.create(**provider_data)
        return self.serialize_public_provider(self.db.providers.get(provider_id))

    def update_provider(self, data):
        provider_id = self._parse_required_id(data.get("id"), "id")
        current_provider = self.db.providers.get(provider_id)
        if not current_provider:
            raise ResourceNotFoundError("Provider not found")

        provider_data = self._parse_provider_payload(
            data,
            existing_api_key=current_provider.get("api_key"),
        )
        if current_provider.get("is_builtin"):
            provider_data["is_builtin"] = True
            provider_data["builtin_key"] = current_provider["builtin_key"]

        self.db.providers.update(provider_id=provider_id, **provider_data)
        self.db.models.sync_provider_snapshot(provider_id)
        return self.serialize_public_provider(self.db.providers.get(provider_id))

    def delete_provider(self, provider_id):
        parsed_id = self._parse_required_id(provider_id, "id")
        provider = self.db.providers.get(parsed_id)
        if not provider:
            raise ResourceNotFoundError("Provider not found")
        if provider.get("is_builtin"):
            raise ConflictError("Built-in providers cannot be deleted.")
        if self.db.providers.models_count(parsed_id) > 0:
            raise ConflictError("A provider with assigned models cannot be deleted.")

        self.db.providers.delete(parsed_id)
        return {"deleted": True, "provider_id": parsed_id}

    def restore_provider(self, data):
        provider_id = self._parse_required_id(data.get("id"), "id")
        provider = self.db.providers.restore(provider_id)
        if not provider:
            raise ResourceNotFoundError("Provider not found or not restorable")

        self.db.models.sync_provider_snapshot(provider_id)
        return self.serialize_public_provider(provider)

    def test_provider_connection(self, data):
        provider_type = str(data.get("provider_type", "")).strip().lower()
        endpoint = str(data.get("endpoint", "")).strip()
        api_key = str(data.get("api_key", "")).strip()
        if data.get("id") and not api_key:
            provider = self.db.providers.get(self._parse_required_id(data.get("id"), "id"))
            if provider:
                api_key = provider.get("api_key", "")
                provider_type = provider_type or provider.get("provider_type", "")
                endpoint = endpoint or provider.get("endpoint", "")

        try:
            resolved = self.model_manager.resolve_provider_configuration(
                provider_type,
                endpoint,
                api_key,
                allow_probe=True,
            )
        except ValueError as error:
            raise RequestError(str(error)) from error

        return {"ok": True, **resolved}

    def serialize_public_provider(self, provider):
        if not provider:
            return None
        return {
            "id": provider["id"],
            "name": provider["name"],
            "provider_type": provider["provider_type"],
            "endpoint": provider["endpoint"],
            "has_api_key": bool(provider.get("api_key")),
            "is_builtin": provider["is_builtin"],
            "builtin_key": provider["builtin_key"],
            "created_at": provider["created_at"],
            "updated_at": provider["updated_at"],
        }

    def _parse_provider_payload(self, data, existing_api_key=None):
        self._require_fields(data, "name", "provider_type")
        name = str(data.get("name", "")).strip()
        provider_type = str(data.get("provider_type", "")).strip().lower()
        endpoint = str(data.get("endpoint", "")).strip()
        api_key = str(data.get("api_key", "")).strip()
        if not api_key and existing_api_key:
            api_key = existing_api_key

        if not name:
            raise RequestError("Missing name")
        if provider_type not in self.SUPPORTED_PROVIDER_TYPES:
            raise RequestError("Provider type must be one of: mlx, ollama, cloud")
        if provider_type in {"ollama", "cloud"} and not endpoint:
            raise RequestError("Missing endpoint")

        resolved = self.model_manager.resolve_provider_configuration(
            provider_type,
            endpoint,
            api_key,
            allow_probe=False,
        )
        return {
            "name": name,
            "provider_type": provider_type,
            "endpoint": endpoint,
            "api_key": api_key,
            "resolved_adapter": resolved["resolved_adapter"],
            "resolved_metadata": resolved["resolved_metadata"],
            "is_builtin": bool(data.get("is_builtin", False)),
            "builtin_key": str(data.get("builtin_key", "")).strip().lower() or None,
        }

    def _parse_required_id(self, value, field_name):
        if value is None or value == "":
            raise RequestError(f"Missing {field_name}")
        try:
            return int(value)
        except (TypeError, ValueError):
            raise RequestError(f"Invalid {field_name}")

    def _require_fields(self, data, *field_names):
        for field_name in field_names:
            if data.get(field_name) is None or data.get(field_name) == "":
                raise RequestError(f"Missing {field_name}")
