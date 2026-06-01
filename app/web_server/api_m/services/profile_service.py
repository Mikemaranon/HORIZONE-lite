from .service_errors import RequestError, ResourceNotFoundError


class ProfileService:
    MAX_TAGS = 10

    def __init__(self, db_manager):
        self.db = db_manager

    def list_profiles(self):
        return self.db.profiles.all()

    def get_profile(self, profile_id):
        parsed_id = self._parse_required_id(profile_id, "id")
        profile = self.db.profiles.get(parsed_id)
        if not profile:
            raise ResourceNotFoundError("Profile not found")
        return profile

    def create_profile(self, data):
        profile_data = self._parse_profile_payload(data)
        profile_id = self.db.profiles.create(**profile_data)
        return self.db.profiles.get(profile_id)

    def update_profile(self, data):
        profile_id = self._parse_required_id(data.get("id"), "id")
        if not self.db.profiles.get(profile_id):
            raise ResourceNotFoundError("Profile not found")

        self.db.profiles.update(
            profile_id=profile_id,
            **self._parse_profile_payload(data),
        )
        return self.db.profiles.get(profile_id)

    def delete_profile(self, profile_id):
        parsed_id = self._parse_required_id(profile_id, "id")
        if not self.db.profiles.get(parsed_id):
            raise ResourceNotFoundError("Profile not found")
        if self.db.profiles.count() <= 1:
            raise RequestError("The last profile cannot be deleted.")

        self.db.profiles.delete(parsed_id)
        return {"deleted": True, "profile_id": parsed_id}

    def _parse_profile_payload(self, data):
        self._require_fields(data, "name")
        name = str(data.get("name", "")).strip()
        if not name:
            raise RequestError("Missing name")

        try:
            temperature = float(data.get("temperature", 0.7))
            top_p = float(data.get("top_p", 1.0))
            max_tokens = int(data.get("max_tokens", 2048))
        except (TypeError, ValueError) as error:
            raise RequestError("Invalid profile generation settings") from error

        return {
            "name": name,
            "personality": str(data.get("personality", "")).strip(),
            "tags": self._parse_tags(data.get("tags")),
            "system_prompt": data.get("system_prompt", ""),
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
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
            raise RequestError("tags must be a list or comma-separated string")

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
            raise RequestError(f"tags supports a maximum of {self.MAX_TAGS} items")
        return normalized_tags

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
