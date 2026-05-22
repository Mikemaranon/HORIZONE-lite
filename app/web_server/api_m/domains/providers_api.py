from flask import request

from api_m.domains.base_api import BaseAPI


class ProvidersAPI(BaseAPI):
    SUPPORTED_PROVIDER_TYPES = {"mlx", "ollama", "cloud"}

    def register(self):
        self.app.add_url_rule("/api/providers", view_func=self.handle_providers_get, methods=["GET"])
        self.app.add_url_rule("/api/providers", view_func=self.handle_providers_post, methods=["POST"])
        self.app.add_url_rule("/api/providers", view_func=self.handle_providers_patch, methods=["PATCH"])
        self.app.add_url_rule("/api/providers", view_func=self.handle_providers_delete, methods=["DELETE"])
        self.app.add_url_rule("/api/providers/restore", view_func=self.handle_providers_restore, methods=["POST"])

    def handle_providers_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        provider_id = request.args.get("id")
        if provider_id:
            try:
                provider = self.db.providers.get(self.parse_int(provider_id, "id"))
            except ValueError as error:
                return self.error(str(error), 400)

            if not provider:
                return self.error("Provider not found", 404)
            return self.ok({"provider": self._serialize_public_provider(provider)})

        return self.ok({"providers": [self._serialize_public_provider(provider) for provider in self.db.providers.all()]})

    def handle_providers_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            provider_data = self._parse_provider_payload(data)
        except ValueError as error:
            return self.error(str(error), 400)

        provider_id = self.db.providers.create(**provider_data)
        return self.ok({"provider": self._serialize_public_provider(self.db.providers.get(provider_id))}, 201)

    def handle_providers_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            self.require_fields(data, "id")
            provider_id = self.parse_int(data.get("id"), "id")
            provider_data = self._parse_provider_payload(data)
        except ValueError as error:
            return self.error(str(error), 400)

        current_provider = self.db.providers.get(provider_id)
        if not current_provider:
            return self.error("Provider not found", 404)

        if current_provider.get("is_builtin"):
            provider_data["is_builtin"] = True
            provider_data["builtin_key"] = current_provider["builtin_key"]

        self.db.providers.update(provider_id=provider_id, **provider_data)
        self.db.models.sync_provider_snapshot(provider_id)
        return self.ok({"provider": self._serialize_public_provider(self.db.providers.get(provider_id))})

    def handle_providers_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            provider_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": provider_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        provider = self.db.providers.get(provider_id)
        if not provider:
            return self.error("Provider not found", 404)
        if provider.get("is_builtin"):
            return self.error("Los proveedores integrados no se pueden borrar.", 400)
        if self.db.providers.models_count(provider_id) > 0:
            return self.error("No se puede borrar un proveedor que todavía tiene modelos asignados.", 400)

        self.db.providers.delete(provider_id)
        return self.ok({"deleted": True, "provider_id": provider_id})

    def handle_providers_restore(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            self.require_fields(data, "id")
            provider_id = self.parse_int(data.get("id"), "id")
        except ValueError as error:
            return self.error(str(error), 400)

        provider = self.db.providers.restore(provider_id)
        if not provider:
            return self.error("Provider not found or not restorable", 404)

        self.db.models.sync_provider_snapshot(provider_id)
        return self.ok({"provider": self._serialize_public_provider(provider)})

    def _parse_provider_payload(self, data):
        self.require_fields(data, "name", "provider_type")
        name = str(data.get("name", "")).strip()
        provider_type = str(data.get("provider_type", "")).strip().lower()
        endpoint = str(data.get("endpoint", "")).strip()
        api_key = str(data.get("api_key", "")).strip()

        if not name:
            raise ValueError("Missing name")
        if provider_type not in self.SUPPORTED_PROVIDER_TYPES:
            raise ValueError("Provider type must be one of: mlx, ollama, cloud")
        if provider_type in {"ollama", "cloud"} and not endpoint:
            raise ValueError("Missing endpoint")

        resolved = self.model_manager.resolve_provider_configuration(
            provider_type,
            endpoint,
            api_key,
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

    def _serialize_public_provider(self, provider):
        if not provider:
            return None

        return {
            "id": provider["id"],
            "name": provider["name"],
            "provider_type": provider["provider_type"],
            "endpoint": provider["endpoint"],
            "api_key": provider["api_key"],
            "is_builtin": provider["is_builtin"],
            "builtin_key": provider["builtin_key"],
            "created_at": provider["created_at"],
            "updated_at": provider["updated_at"],
        }
