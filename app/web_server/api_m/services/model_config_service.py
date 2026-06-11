from pathlib import Path

from .service_errors import RequestError, ResourceNotFoundError


class ModelConfigService:
    def __init__(self, db_manager, runtime_config=None):
        self.db = db_manager
        self.runtime_config = runtime_config

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

        if current_model.get("provider") == "llama_cpp":
            model_data = self._parse_runtime_model_update_payload(data, current_model)
        else:
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
        model = self.db.models.get(parsed_id)
        if not model:
            raise ResourceNotFoundError("Model not found")
        if self.db.models.count() <= 1:
            raise RequestError("The last model cannot be deleted.")

        runtime_downloads = []
        if model.get("provider") == "llama_cpp":
            runtime_downloads = self.db.runtime_model_downloads.for_model(parsed_id)

        with self.db.transaction():
            if runtime_downloads:
                self.db.runtime_model_downloads.delete_for_model(parsed_id)
            self.db.models.delete(parsed_id)

        self._delete_runtime_model_files(runtime_downloads)
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
        provider = self.db.providers.get(provider_config_id)
        if provider.get("is_system_managed"):
            raise RequestError("System-managed providers install models through the runtime catalog.")

        return {
            "name": name,
            "display_name": display_name or name,
            "provider_config_id": provider_config_id,
            "icon_image": self._parse_icon_image(data.get("icon_image")),
            "is_default": bool(data.get("is_default", False)),
            "is_builtin": bool(data.get("is_builtin", False)),
        }

    def _parse_runtime_model_update_payload(self, data, current_model):
        display_name = str(data.get("display_name", "")).strip()

        return {
            "name": current_model["name"],
            "display_name": display_name or current_model["name"],
            "provider_config_id": current_model["provider_id"],
            "icon_image": self._parse_icon_image(data.get("icon_image")),
            "is_default": bool(data.get("is_default", False)),
            "is_builtin": True,
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
        if not mime_type.startswith("image/"):
            raise RequestError("icon_image must be an image")
        if not payload:
            raise RequestError("icon_image payload is empty")
        if len(icon_image) > 14_500_000:
            raise RequestError("icon_image is too large")
        return icon_image

    def _delete_runtime_model_files(self, downloads):
        if not downloads or not self.runtime_config:
            return

        runtime_root = Path(self.runtime_config.runtime_models_dir).expanduser().resolve()
        for download in downloads:
            local_path = str(download.get("local_path") or "").strip()
            if not local_path:
                continue

            path = Path(local_path).expanduser()
            try:
                resolved_path = path.resolve()
            except OSError:
                continue

            if not resolved_path.is_file() or not self._is_relative_to(resolved_path, runtime_root):
                continue

            try:
                resolved_path.unlink()
            except OSError:
                continue

    def _is_relative_to(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

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
