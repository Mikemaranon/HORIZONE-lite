from workspace_m import PathGuardError, WorkspaceManager


class WorkspaceRequestError(ValueError):
    pass


class WorkspaceResourceNotFoundError(LookupError):
    pass


class WorkspaceService:
    def __init__(self, db_manager, workspace_manager=None):
        self.db = db_manager
        self.workspace_manager = workspace_manager or WorkspaceManager()

    def get_project_workspace(self, project_id):
        self._require_project(project_id)
        workspace = self.db.project_workspaces.get_by_project(project_id)
        if not workspace:
            return {
                "workspace": None,
                "file_count": 0,
                "recent_events": [],
            }

        return self._workspace_payload(workspace)

    def connect_project_workspace(self, data):
        project_id = self._require_int(data.get("project_id"), "project_id")
        self._require_project(project_id)

        try:
            root_path = self.workspace_manager.normalize_root(data.get("root_path"))
        except PathGuardError as error:
            raise WorkspaceRequestError(str(error))

        display_name = (data.get("display_name") or "").strip() or root_path.rsplit("/", 1)[-1]
        workspace_id = self.db.project_workspaces.upsert(project_id, root_path, display_name)
        workspace = self.db.project_workspaces.get(workspace_id)
        self._record_event(workspace, "workspace_connected", "Workspace connected.", {"root_path": root_path})
        index_payload = self.index_workspace(workspace_id)
        return index_payload

    def disconnect_workspace(self, workspace_id):
        workspace = self._get_workspace(workspace_id)
        self._record_event(workspace, "workspace_disconnected", "Workspace disconnected.")
        self.db.project_workspaces.delete(workspace_id)
        return {"deleted": True, "workspace_id": workspace_id}

    def index_workspace(self, workspace_id):
        workspace = self._get_workspace(workspace_id)
        try:
            files = self.workspace_manager.scan(workspace["root_path"])
        except PathGuardError as error:
            self.db.project_workspaces.update_status(workspace_id, "error")
            raise WorkspaceRequestError(str(error))

        self.db.workspace_file_index.replace_for_workspace(workspace_id, files)
        self.db.project_workspaces.update_indexed_at(workspace_id)
        workspace = self.db.project_workspaces.get(workspace_id)
        self._record_event(
            workspace,
            "workspace_indexed",
            f"Indexed {len(files)} workspace files.",
            {"file_count": len(files)},
        )
        return self._workspace_payload(workspace)

    def list_files(self, workspace_id, query=None, limit=200):
        workspace = self._get_workspace(workspace_id)
        files = self.db.workspace_file_index.list_for_workspace(
            workspace_id,
            query=(query or "").strip() or None,
            limit=min(max(self._coerce_limit(limit), 1), 500),
        )
        return {
            "workspace": workspace,
            "files": files,
            "file_count": self.db.workspace_file_index.count_for_workspace(workspace_id),
        }

    def read_file(self, workspace_id, relative_path):
        workspace = self._get_workspace(workspace_id)
        if not relative_path:
            raise WorkspaceRequestError("Missing path")

        try:
            file_payload = self.workspace_manager.read_file(workspace["root_path"], relative_path)
        except (FileNotFoundError, PathGuardError, ValueError) as error:
            raise WorkspaceRequestError(str(error))

        self._record_event(
            workspace,
            "workspace_file_read",
            f"Read {file_payload['path']}.",
            {"path": file_payload["path"], "size_bytes": file_payload["size_bytes"]},
        )
        return {"workspace": workspace, "file": file_payload}

    def write_file(self, data, *, conversation_id=None, message_id=None):
        workspace_id = self._require_int(data.get("workspace_id"), "workspace_id")
        workspace = self._get_workspace(workspace_id)
        relative_path = (data.get("path") or "").strip()
        if not relative_path:
            raise WorkspaceRequestError("Missing path")

        try:
            file_payload = self.workspace_manager.write_file(
                workspace["root_path"],
                relative_path,
                data.get("content", ""),
                overwrite=bool(data.get("overwrite")),
                create_dirs=bool(data.get("create_dirs")),
            )
        except (OSError, PathGuardError, ValueError) as error:
            raise WorkspaceRequestError(str(error))

        indexed_files = self.workspace_manager.scan(workspace["root_path"])
        with self.db.transaction():
            self.db.workspace_file_index.replace_for_workspace(workspace_id, indexed_files)
            self.db.project_workspaces.update_indexed_at(workspace_id)
            refreshed_workspace = self.db.project_workspaces.get(workspace_id)
            action = "Created" if file_payload.get("created") else "Updated"
            self._record_event(
                refreshed_workspace,
                "workspace_file_written",
                f"{action} {file_payload['path']}.",
                {"path": file_payload["path"], "size_bytes": file_payload["size_bytes"], "created": file_payload["created"]},
                conversation_id=conversation_id,
                message_id=message_id,
            )
        return {
            "workspace": refreshed_workspace,
            "file": file_payload,
            "file_count": len(indexed_files),
        }

    def append_file(self, data, *, conversation_id=None, message_id=None):
        workspace_id = self._require_int(data.get("workspace_id"), "workspace_id")
        workspace = self._get_workspace(workspace_id)
        relative_path = (data.get("path") or "").strip()
        if not relative_path:
            raise WorkspaceRequestError("Missing path")

        try:
            file_payload = self.workspace_manager.append_file(
                workspace["root_path"],
                relative_path,
                data.get("content", ""),
                ensure_newline_before=self._coerce_bool(
                    data.get("ensure_newline_before"),
                    default=True,
                ),
                ensure_newline_after=self._coerce_bool(
                    data.get("ensure_newline_after"),
                    default=False,
                ),
            )
        except (OSError, PathGuardError, ValueError, UnicodeError) as error:
            raise WorkspaceRequestError(str(error))

        indexed_files = self.workspace_manager.scan(workspace["root_path"])
        with self.db.transaction():
            self.db.workspace_file_index.replace_for_workspace(workspace_id, indexed_files)
            self.db.project_workspaces.update_indexed_at(workspace_id)
            refreshed_workspace = self.db.project_workspaces.get(workspace_id)
            self._record_event(
                refreshed_workspace,
                "workspace_file_appended",
                f"Appended to {file_payload['path']}.",
                {
                    "path": file_payload["path"],
                    "size_bytes": file_payload["size_bytes"],
                    "appended_bytes": file_payload["appended_bytes"],
                },
                conversation_id=conversation_id,
                message_id=message_id,
            )
        return {
            "workspace": refreshed_workspace,
            "file": file_payload,
            "file_count": len(indexed_files),
        }

    def search(self, data):
        workspace_id = self._require_int(data.get("workspace_id"), "workspace_id")
        workspace = self._get_workspace(workspace_id)
        query = (data.get("query") or "").strip()
        limit = min(max(self._coerce_limit(data.get("limit", 50)), 1), 100)

        indexed_files = self.db.workspace_file_index.list_for_workspace(workspace_id, limit=5000)
        try:
            matches = self.workspace_manager.search(workspace["root_path"], indexed_files, query, limit=limit)
        except ValueError as error:
            raise WorkspaceRequestError(str(error))

        self._record_event(
            workspace,
            "workspace_searched",
            f"Searched workspace for {query}.",
            {"query": query, "match_count": len(matches)},
        )
        return {"workspace": workspace, "matches": matches}

    def _workspace_payload(self, workspace):
        return {
            "workspace": workspace,
            "file_count": self.db.workspace_file_index.count_for_workspace(workspace["id"]),
            "recent_events": self.db.workspace_events.recent_for_workspace(workspace["id"], limit=10),
        }

    def _get_workspace(self, workspace_id):
        workspace = self.db.project_workspaces.get(self._require_int(workspace_id, "workspace_id"))
        if not workspace:
            raise WorkspaceResourceNotFoundError("Workspace not found")
        return workspace

    def _require_project(self, project_id):
        if not self.db.projects.get(self._require_int(project_id, "project_id")):
            raise WorkspaceResourceNotFoundError("Project not found")

    def _record_event(
        self,
        workspace,
        event_type,
        summary,
        payload=None,
        conversation_id=None,
        message_id=None,
    ):
        self.db.workspace_events.create(
            workspace_id=workspace["id"],
            project_id=workspace["project_id"],
            event_type=event_type,
            summary=summary,
            payload=payload,
            conversation_id=conversation_id,
            message_id=message_id,
        )

    def _require_int(self, value, field_name):
        if value is None or value == "":
            raise WorkspaceRequestError(f"Missing {field_name}")
        try:
            return int(value)
        except (TypeError, ValueError):
            raise WorkspaceRequestError(f"Invalid {field_name}")

    def _coerce_limit(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 50

    def _coerce_bool(self, value, *, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default
