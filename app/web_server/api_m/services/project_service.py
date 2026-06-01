class ProjectRequestError(ValueError):
    pass


class ProjectResourceNotFoundError(LookupError):
    pass


DEFAULT_PROJECT_AGENT_COLOR = "#1c8b59"


class ProjectService:
    def __init__(self, db_manager):
        self.db = db_manager

    def get_project(self, project_id):
        project = self.db.projects.get(project_id)
        if not project:
            raise ProjectResourceNotFoundError("Project not found")

        return project

    def list_projects(self):
        return self.db.projects.all()

    def create_project(self, data):
        name = data.get("name")
        if name is None or name == "":
            raise ProjectRequestError("Missing name")

        project_id = self.db.projects.create(
            name,
            data.get("description"),
            data.get("system_prompt", ""),
        )
        default_model = self.db.models.get_default()
        default_profile = self.db.profiles.get_default()
        if default_model and default_profile:
            self.db.project_models.ensure_default(
                project_id,
                default_model["id"],
                default_profile["id"],
                "default",
            )
        return self.db.projects.get(project_id)

    def update_project(self, project_id, data):
        existing_project = self.db.projects.get(project_id)
        if not existing_project:
            raise ProjectResourceNotFoundError("Project not found")

        self.db.projects.update(
            project_id,
            data.get("name", existing_project["name"]),
            data.get("description", existing_project.get("description")),
            data.get("system_prompt", existing_project.get("system_prompt", "")),
        )
        return self.db.projects.get(project_id)

    def delete_project(self, project_id):
        project = self.db.projects.get(project_id)
        if not project:
            raise ProjectResourceNotFoundError("Project not found")

        conversation_count = len(self.db.conversations.all(project_id))
        self.db.projects.delete(project_id)
        return {
            "deleted": True,
            "project_id": project_id,
            "conversation_retention": "detached",
            "orphaned_conversation_count": conversation_count,
        }

    def list_project_models(self, project_id):
        if not self.db.projects.get(project_id):
            raise ProjectResourceNotFoundError("Project not found")

        models = self.db.project_models.list_models(project_id)
        if models:
            return {
                "models": models,
                "uses_default": False,
            }

        default_model = self.db.models.get_default()
        default_profile = self.db.profiles.get_default()
        if default_model and default_profile:
            project_model_id = self.db.project_models.ensure_default(
                project_id,
                default_model["id"],
                default_profile["id"],
                "default",
            )
            fallback_models = [self.db.project_models.get(project_model_id)]
        else:
            fallback_models = []
        return {
            "models": fallback_models,
            "uses_default": True,
        }

    def create_project_model(self, project_id, data):
        if not self.db.projects.get(project_id):
            raise ProjectResourceNotFoundError("Project not found")

        model_id, profile_id, nickname, system_prompt, is_default, color = self._parse_project_model_payload(
            project_id,
            data,
        )
        project_model_id = self.db.project_models.create(
            project_id=project_id,
            model_id=model_id,
            profile_id=profile_id,
            nickname=nickname,
            system_prompt=system_prompt,
            is_default=is_default,
            color=color,
        )
        return self.db.project_models.get(project_model_id)

    def update_project_model(self, project_model_id, data):
        existing = self.db.project_models.get(project_model_id)
        if not existing:
            raise ProjectResourceNotFoundError("Project model not found")

        model_id, profile_id, nickname, system_prompt, is_default, color = self._parse_project_model_payload(
            existing["project_id"],
            data,
            existing=existing,
        )
        self.db.project_models.update(
            project_model_id,
            model_id,
            profile_id,
            nickname,
            system_prompt,
            is_default=is_default,
            color=color,
        )
        return self.db.project_models.get(project_model_id)

    def delete_project_model(self, project_model_id):
        existing = self.db.project_models.get(project_model_id)
        if not existing:
            raise ProjectResourceNotFoundError("Project model not found")

        self.db.project_models.delete(project_model_id)
        return {
            "deleted": True,
            "project_model_id": project_model_id,
        }

    def _parse_project_model_payload(self, project_id, data, existing=None):
        nickname = str(data.get("nickname", existing.get("nickname") if existing else "") or "").strip()
        if not nickname:
            raise ProjectRequestError("Missing nickname")

        if self.db.project_models.nickname_exists(
            project_id,
            nickname,
            excluded_project_model_id=existing["id"] if existing else None,
        ):
            raise ProjectRequestError("A project model with this nickname already exists")

        model_id = self._parse_positive_int(
            data.get("model_id", existing.get("model_id") if existing else None),
            "model_id",
        )
        profile_id = self._parse_positive_int(
            data.get("profile_id", existing.get("profile_id") if existing else None),
            "profile_id",
        )

        if not self.db.models.get(model_id):
            raise ProjectRequestError("Model not found")
        if not self.db.profiles.get(profile_id):
            raise ProjectRequestError("Profile not found")

        system_prompt = str(
            data.get("system_prompt", existing.get("system_prompt") if existing else "") or ""
        ).strip()

        is_default = self._parse_bool(
            data.get("is_default", existing.get("is_default") if existing else False)
        )

        color = self._parse_color(
            data.get("color", existing.get("color") if existing else DEFAULT_PROJECT_AGENT_COLOR)
        )

        return model_id, profile_id, nickname, system_prompt, is_default, color

    def _parse_positive_int(self, value, field_name):
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            raise ProjectRequestError(f"Missing {field_name}")
        if parsed_value <= 0:
            raise ProjectRequestError(f"Missing {field_name}")
        return parsed_value

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    def _parse_color(self, value):
        color = str(value or DEFAULT_PROJECT_AGENT_COLOR).strip()
        if len(color) != 7 or not color.startswith("#"):
            raise ProjectRequestError("Agent color must be a hex color")

        try:
            int(color[1:], 16)
        except ValueError:
            raise ProjectRequestError("Agent color must be a hex color")

        return color.lower()
