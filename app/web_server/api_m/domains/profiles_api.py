from flask import request

from api_m.domains.base_api import BaseAPI


class ProfilesAPI(BaseAPI):
    MAX_TAGS = 10

    def register(self):
        self.app.add_url_rule("/api/profiles", view_func=self.handle_profiles_get, methods=["GET"])
        self.app.add_url_rule("/api/profiles", view_func=self.handle_profiles_post, methods=["POST"])
        self.app.add_url_rule("/api/profiles", view_func=self.handle_profiles_patch, methods=["PATCH"])
        self.app.add_url_rule("/api/profiles", view_func=self.handle_profiles_delete, methods=["DELETE"])

    def handle_profiles_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        profile_id = request.args.get("id")
        if profile_id:
            try:
                profile = self.db.profiles.get(self.parse_int(profile_id, "id"))
            except ValueError as error:
                return self.error(str(error), 400)

            if not profile:
                return self.error("Profile not found", 404)
            return self.ok({"profile": profile})

        return self.ok({"profiles": self.db.profiles.all()})

    def handle_profiles_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            profile_data = self._parse_profile_payload(data)
        except ValueError as error:
            return self.error(str(error), 400)

        profile_id = self.db.profiles.create(
            **profile_data
        )
        return self.ok({"profile": self.db.profiles.get(profile_id)}, 201)

    def handle_profiles_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)

        try:
            self.require_fields(data, "id")
            profile_id = self.parse_int(data.get("id"), "id")
            profile_data = self._parse_profile_payload(data)
        except ValueError as error:
            return self.error(str(error), 400)

        if not self.db.profiles.get(profile_id):
            return self.error("Profile not found", 404)

        self.db.profiles.update(profile_id=profile_id, **profile_data)
        return self.ok({"profile": self.db.profiles.get(profile_id)})

    def handle_profiles_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            profile_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": profile_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        if not self.db.profiles.get(profile_id):
            return self.error("Profile not found", 404)

        if self.db.profiles.count() <= 1:
            return self.error("The last profile cannot be deleted.", 400)

        self.db.profiles.delete(profile_id)
        return self.ok({"deleted": True, "profile_id": profile_id})

    def _parse_profile_payload(self, data):
        self.require_fields(data, "name")
        name = data["name"].strip()

        if not name:
            raise ValueError("Missing name")

        tags = self._parse_tags(data.get("tags"))

        return {
            "name": name,
            "personality": str(data.get("personality", "")).strip(),
            "tags": tags,
            "system_prompt": data.get("system_prompt", ""),
            "temperature": float(data.get("temperature", 0.7)),
            "top_p": float(data.get("top_p", 1.0)),
            "max_tokens": int(data.get("max_tokens", 2048)),
            "is_default": bool(data.get("is_default", False)),
        }

    def _parse_tags(self, value):
        if value is None:
            return []

        if isinstance(value, str):
            raw_tags = value.split(",")
        elif isinstance(value, list):
            raw_tags = value
        else:
            raise ValueError("tags must be a list or comma-separated string")

        normalized_tags = []
        seen = set()

        for tag in raw_tags:
            normalized = str(tag).strip()
            normalized_key = normalized.lower()

            if not normalized or normalized_key in seen:
                continue

            normalized_tags.append(normalized)
            seen.add(normalized_key)

        if len(normalized_tags) > self.MAX_TAGS:
            raise ValueError(f"tags supports a maximum of {self.MAX_TAGS} items")

        return normalized_tags
