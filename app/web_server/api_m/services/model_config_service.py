from .service_errors import RequestError, ResourceNotFoundError


ALLOWED_MODEL_ICON_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


class ModelConfigService:
    def __init__(self, db_manager):
        self.db = db_manager

    def list_models(self):
        return self.db.models.all()

    def get_model(self, model_id):
        parsed_id = self._parse_required_id(model_id, "id")
        model = self.db.models.get(parsed_id)
        if not model:
            raise ResourceNotFoundError("Model not found")
        return model

    def create_model(self, data):
        model_data = self._parse_model_payload(data)
        model_id = self.db.models.create(**model_data)
        return self.db.models.get(model_id)

    def update_model(self, data):
        model_id = self._parse_required_id(data.get("id"), "id")
        current_model = self.db.models.get(model_id)
        if not current_model:
            raise ResourceNotFoundError("Model not found")

        model_data = self._parse_model_payload(data)
        if current_model.get("is_builtin"):
            model_data["is_builtin"] = True

        with self.db.transaction():
            self.db.models.update(model_id=model_id, **model_data)
            updated_model = self.db.models.get(model_id)
            self._sync_conversations_for_model(updated_model)
        return updated_model

    def delete_model(self, model_id):
        parsed_id = self._parse_required_id(model_id, "id")
        if not self.db.models.get(parsed_id):
            raise ResourceNotFoundError("Model not found")
        if self.db.models.count() <= 1:
            raise RequestError("The last model cannot be deleted.")

        self.db.models.delete(parsed_id)
        return {"deleted": True, "model_id": parsed_id}

    def _parse_model_payload(self, data):
        self._require_fields(data, "name", "provider_id")
        name = str(data.get("name", "")).strip()
        display_name = str(data.get("display_name", "")).strip()
        provider_config_id = self._parse_optional_int(data.get("provider_id"), "provider_id")

        if not name:
            raise RequestError("Missing name")
        if not provider_config_id:
            raise RequestError("Missing provider_id")
        if not self.db.providers.get(provider_config_id):
            raise RequestError("Provider not found")

        return {
            "name": name,
            "display_name": display_name or name,
            "provider_config_id": provider_config_id,
            "icon_image": self._parse_icon_image(data.get("icon_image")),
            "is_default": bool(data.get("is_default", False)),
            "is_builtin": bool(data.get("is_builtin", False)),
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
            raise RequestError("icon_image must be a base64 data URL")

        mime_type = prefix[5:].split(";", 1)[0].strip().lower()
        if mime_type not in ALLOWED_MODEL_ICON_MIME_TYPES:
            raise RequestError("icon_image must be PNG, JPEG, WEBP, or GIF")
        if not payload:
            raise RequestError("icon_image payload is empty")
        if len(icon_image) > 700_000:
            raise RequestError("icon_image is too large")
        return icon_image

    def _parse_required_id(self, value, field_name):
        parsed_id = self._parse_optional_int(value, field_name)
        if parsed_id is None:
            raise RequestError(f"Missing {field_name}")
        return parsed_id

    def _parse_optional_int(self, value, field_name):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise RequestError(f"Invalid {field_name}")

    def _require_fields(self, data, *field_names):
        for field_name in field_names:
            if data.get(field_name) is None or data.get(field_name) == "":
                raise RequestError(f"Missing {field_name}")
