from flask import request

from api_m.domains.base_api import BaseAPI

ALLOWED_MODEL_ICON_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


class ModelsAPI(BaseAPI):
    def register(self):
        self.app.add_url_rule("/api/models", view_func=self.get_models, methods=["GET"])
        self.app.add_url_rule("/api/models", view_func=self.create_model, methods=["POST"])
        self.app.add_url_rule("/api/models", view_func=self.update_model, methods=["PATCH"])
        self.app.add_url_rule("/api/models", view_func=self.delete_model, methods=["DELETE"])

    def get_models(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        model_id = request.args.get("id")
        if model_id:
            try:
                model = self.db.models.get(self.parse_int(model_id, "id"))
            except ValueError as error:
                return self.error(str(error), 400)

            if not model:
                return self.error("Model not found", 404)
            return self.ok({"model": model})

        return self.ok({"models": self.db.models.all()})

    def create_model(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            model_data = self._parse_model_payload(data)
        except ValueError as error:
            return self.error(str(error), 400)

        model_id = self.db.models.create(**model_data)
        return self.ok({"model": self.db.models.get(model_id)}, 201)

    def update_model(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            self.require_fields(data, "id")
            model_id = self.parse_int(data.get("id"), "id")
            model_data = self._parse_model_payload(data)
        except ValueError as error:
            return self.error(str(error), 400)

        current_model = self.db.models.get(model_id)
        if not current_model:
            return self.error("Model not found", 404)

        if current_model.get("is_builtin"):
            model_data["is_builtin"] = True

        with self.db.transaction():
            self.db.models.update(model_id=model_id, **model_data)
            updated_model = self.db.models.get(model_id)
            self._sync_conversations_for_model(updated_model)
        return self.ok({"model": updated_model})

    def delete_model(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            model_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": model_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        if not self.db.models.get(model_id):
            return self.error("Model not found", 404)

        if self.db.models.count() <= 1:
            return self.error("The last model cannot be deleted.", 400)

        self.db.models.delete(model_id)
        return self.ok({"deleted": True, "model_id": model_id})

    def _parse_model_payload(self, data):
        self.require_fields(data, "name", "provider_id")
        name = str(data.get("name", "")).strip()
        display_name = str(data.get("display_name", "")).strip()
        provider_config_id = self.parse_int(data.get("provider_id"), "provider_id")

        if not name:
            raise ValueError("Missing name")
        if not provider_config_id:
            raise ValueError("Missing provider_id")
        if not self.db.providers.get(provider_config_id):
            raise ValueError("Provider not found")

        is_builtin = bool(data.get("is_builtin", False))

        return {
            "name": name,
            "display_name": display_name or name,
            "provider_config_id": provider_config_id,
            "icon_image": self._parse_icon_image(data.get("icon_image")),
            "is_default": bool(data.get("is_default", False)),
            "is_builtin": is_builtin,
        }

    def _sync_conversations_for_model(self, model):
        self.db.execute(
            """
            UPDATE conversations
            SET provider = ?,
                model = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE model_config_id = ?
            """,
            (model["provider"], model["name"], model["id"]),
        )
        self.db.execute(
            """
            UPDATE messages
            SET model_name = ?
            WHERE model_config_id = ?
            """,
            (model["display_name"] or model["name"], model["id"]),
        )

    def _parse_icon_image(self, raw_value):
        icon_image = str(raw_value or "").strip()
        if not icon_image:
            return ""

        prefix, separator, payload = icon_image.partition(",")
        if separator != "," or not prefix.startswith("data:") or ";base64" not in prefix:
            raise ValueError("icon_image must be a base64 data URL")

        mime_type = prefix[5:].split(";", 1)[0].strip().lower()
        if mime_type not in ALLOWED_MODEL_ICON_MIME_TYPES:
            raise ValueError("icon_image must be PNG, JPEG, WEBP, or GIF")

        if not payload:
            raise ValueError("icon_image payload is empty")

        if len(icon_image) > 700_000:
            raise ValueError("icon_image is too large")

        return icon_image
