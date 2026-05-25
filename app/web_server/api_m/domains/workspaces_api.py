from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import (
    WorkspaceRequestError,
    WorkspaceResourceNotFoundError,
    WorkspaceService,
)


class WorkspacesAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        if self.services:
            self.workspace_service = self.services.workspace_service
        else:
            self.workspace_service = WorkspaceService(self.db)

    def register(self):
        self.app.add_url_rule(
            "/api/projects/workspace",
            view_func=self.handle_project_workspace_get,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/projects/workspace",
            view_func=self.handle_project_workspace_post,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/projects/workspace",
            view_func=self.handle_project_workspace_delete,
            methods=["DELETE"],
        )
        self.app.add_url_rule(
            "/api/workspaces/index",
            view_func=self.handle_workspace_index_post,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/workspaces/files",
            view_func=self.handle_workspace_files_get,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/workspaces/file",
            view_func=self.handle_workspace_file_get,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/workspaces/file",
            view_func=self.handle_workspace_file_post,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/workspaces/search",
            view_func=self.handle_workspace_search_post,
            methods=["POST"],
        )

    def handle_project_workspace_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            project_id = self.parse_int(request.args.get("project_id"), "project_id")
            self.require_fields({"project_id": project_id}, "project_id")
            payload = self.workspace_service.get_project_workspace(project_id)
        except WorkspaceResourceNotFoundError as error:
            return self.error(str(error), 404)
        except (ValueError, WorkspaceRequestError) as error:
            return self.error(str(error), 400)

        return self.ok(payload)

    def handle_project_workspace_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.workspace_service.connect_project_workspace(
                self.get_request_json(request)
            )
        except WorkspaceResourceNotFoundError as error:
            return self.error(str(error), 404)
        except WorkspaceRequestError as error:
            return self.error(str(error), 400)

        return self.ok(payload, 201)

    def handle_project_workspace_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            workspace_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": workspace_id}, "id")
            payload = self.workspace_service.disconnect_workspace(workspace_id)
        except WorkspaceResourceNotFoundError as error:
            return self.error(str(error), 404)
        except (ValueError, WorkspaceRequestError) as error:
            return self.error(str(error), 400)

        return self.ok(payload)

    def handle_workspace_index_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            payload = self.workspace_service.index_workspace(data.get("workspace_id"))
        except WorkspaceResourceNotFoundError as error:
            return self.error(str(error), 404)
        except WorkspaceRequestError as error:
            return self.error(str(error), 400)

        return self.ok(payload)

    def handle_workspace_files_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            workspace_id = self.parse_int(request.args.get("workspace_id"), "workspace_id")
            self.require_fields({"workspace_id": workspace_id}, "workspace_id")
            payload = self.workspace_service.list_files(
                workspace_id,
                query=request.args.get("query"),
                limit=request.args.get("limit", 200),
            )
        except WorkspaceResourceNotFoundError as error:
            return self.error(str(error), 404)
        except (ValueError, WorkspaceRequestError) as error:
            return self.error(str(error), 400)

        return self.ok(payload)

    def handle_workspace_file_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            workspace_id = self.parse_int(request.args.get("workspace_id"), "workspace_id")
            self.require_fields({"workspace_id": workspace_id}, "workspace_id")
            payload = self.workspace_service.read_file(workspace_id, request.args.get("path"))
        except WorkspaceResourceNotFoundError as error:
            return self.error(str(error), 404)
        except (ValueError, WorkspaceRequestError) as error:
            return self.error(str(error), 400)

        return self.ok(payload)

    def handle_workspace_file_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.workspace_service.write_file(self.get_request_json(request))
        except WorkspaceResourceNotFoundError as error:
            return self.error(str(error), 404)
        except WorkspaceRequestError as error:
            return self.error(str(error), 400)

        return self.ok(payload, 201)

    def handle_workspace_search_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.workspace_service.search(self.get_request_json(request))
        except WorkspaceResourceNotFoundError as error:
            return self.error(str(error), 404)
        except WorkspaceRequestError as error:
            return self.error(str(error), 400)

        return self.ok(payload)
