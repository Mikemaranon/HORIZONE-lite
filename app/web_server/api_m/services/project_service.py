class ProjectRequestError(ValueError):
    pass


class ProjectResourceNotFoundError(LookupError):
    pass


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
