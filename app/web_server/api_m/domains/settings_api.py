from flask import request

from api_m.domains.base_api import BaseAPI


class SettingsAPI(BaseAPI):
    SECRET_KEYWORDS = ("api_key", "token", "password", "secret", "authorization")

    def register(self):
        self.app.add_url_rule("/api/settings", view_func=self.handle_settings_get, methods=["GET"])
        self.app.add_url_rule("/api/settings", view_func=self.handle_settings_post, methods=["POST"])

    def handle_settings_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        key = request.args.get("key")
        if key:
            setting = self.db.settings.get(key)
            if not setting:
                return self.error("Setting not found", 404)
            return self.ok({"setting": self._serialize_setting(setting)})

        return self.ok({"settings": [self._serialize_setting(setting) for setting in self.db.settings.all()]})

    def handle_settings_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            self.require_fields(data, "key", "value")
        except ValueError as error:
            return self.error(str(error), 400)

        self.db.settings.set(data["key"], data["value"])
        return self.ok({"setting": self._serialize_setting(self.db.settings.get(data["key"]))}, 201)

    def _serialize_setting(self, setting):
        if not setting:
            return None

        serialized = dict(setting)
        if self._is_secret_key(serialized.get("key")):
            serialized["value"] = ""
            serialized["has_value"] = bool(setting.get("value"))
        return serialized

    def _is_secret_key(self, key):
        normalized = str(key or "").lower()
        return any(keyword in normalized for keyword in self.SECRET_KEYWORDS)
