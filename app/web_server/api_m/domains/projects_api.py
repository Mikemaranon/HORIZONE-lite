from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import (
    DocumentIngestionError,
    ProjectDocumentRequestError,
    ProjectDocumentService,
    ProjectRequestError,
    ProjectResourceNotFoundError,
    ProjectService,
)


class ProjectsAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        if self.services:
            self.project_service = self.services.project_service
            self.project_document_service = self.services.project_document_service
        else:
            self.project_service = ProjectService(self.db)
            self.project_document_service = ProjectDocumentService(self.db)

    def register(self):
        self.app.add_url_rule("/api/projects", view_func=self.handle_projects_get, methods=["GET"])
        self.app.add_url_rule("/api/projects", view_func=self.handle_projects_post, methods=["POST"])
        self.app.add_url_rule("/api/projects", view_func=self.handle_projects_patch, methods=["PATCH"])
        self.app.add_url_rule("/api/projects", view_func=self.handle_projects_delete, methods=["DELETE"])
        self.app.add_url_rule(
            "/api/projects/documents",
            view_func=self.handle_project_documents_get,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/projects/documents",
            view_func=self.handle_project_documents_post,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/projects/documents",
            view_func=self.handle_project_documents_delete,
            methods=["DELETE"],
        )
        self.app.add_url_rule(
            "/api/projects/documents",
            view_func=self.handle_project_documents_patch,
            methods=["PATCH"],
        )
        self.app.add_url_rule(
            "/api/projects/document-folders",
            view_func=self.handle_project_document_folders_post,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/projects/document-folders",
            view_func=self.handle_project_document_folders_delete,
            methods=["DELETE"],
        )
        self.app.add_url_rule(
            "/api/projects/models",
            view_func=self.handle_project_models_get,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/projects/models",
            view_func=self.handle_project_models_patch,
            methods=["PATCH"],
        )
        self.app.add_url_rule(
            "/api/projects/models",
            view_func=self.handle_project_models_post,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/projects/models",
            view_func=self.handle_project_models_delete,
            methods=["DELETE"],
        )

    def handle_projects_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        project_id = request.args.get("id")
        if project_id:
            try:
                project = self.project_service.get_project(
                    self.parse_int(project_id, "id")
                )
            except ProjectResourceNotFoundError as error:
                return self.error(str(error), 404)
            except ValueError as error:
                return self.error(str(error), 400)

            return self.ok({"project": project})

        return self.ok({"projects": self.project_service.list_projects()})

    def handle_projects_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            project = self.project_service.create_project(data)
        except ProjectRequestError as error:
            return self.error(str(error), 400)

        return self.ok({"project": project}, 201)

    def handle_projects_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)

        try:
            project_id = self.parse_int(data.get("id"), "id")
            self.require_fields({"id": project_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            project = self.project_service.update_project(project_id, data)
        except ProjectResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok({"project": project})

    def handle_projects_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            project_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": project_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            payload = self.project_service.delete_project(project_id)
        except ProjectResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok(payload)

    def handle_project_documents_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            project_id = self.parse_int(request.args.get("project_id"), "project_id")
            self.require_fields({"project_id": project_id}, "project_id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            payload = self.project_document_service.list_documents(project_id)
        except LookupError as error:
            return self.error(str(error), 404)

        return self.ok(payload)

    def handle_project_documents_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            project_id = self.parse_int(request.form.get("project_id"), "project_id")
            self.require_fields({"project_id": project_id}, "project_id")
            folder_id = self.parse_int(request.form.get("folder_id"), "folder_id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            created_documents = self.project_document_service.create_documents(
                project_id,
                request.files.getlist("files"),
                folder_id=folder_id,
            )
        except DocumentIngestionError as error:
            return self.error(str(error), 400)
        except ProjectDocumentRequestError as error:
            return self.error(str(error), 400)
        except LookupError as error:
            return self.error(str(error), 404)

        return self.ok({"documents": created_documents}, 201)

    def handle_project_documents_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            document_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": document_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            payload = self.project_document_service.delete_document(document_id)
        except LookupError as error:
            return self.error(str(error), 404)

        return self.ok(payload)

    def handle_project_documents_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)

        try:
            document_id = self.parse_int(data.get("id"), "id")
            folder_id = self.parse_int(data.get("folder_id"), "folder_id")
            self.require_fields({"id": document_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            document = self.project_document_service.move_document(
                document_id,
                folder_id=folder_id,
            )
        except ProjectDocumentRequestError as error:
            return self.error(str(error), 400)
        except LookupError as error:
            return self.error(str(error), 404)

        return self.ok({"document": document})

    def handle_project_document_folders_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)

        try:
            project_id = self.parse_int(data.get("project_id"), "project_id")
            parent_folder_id = self.parse_int(data.get("parent_folder_id"), "parent_folder_id")
            self.require_fields({"project_id": project_id}, "project_id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            folder = self.project_document_service.create_folder(
                project_id=project_id,
                name=data.get("name"),
                parent_folder_id=parent_folder_id,
            )
        except ProjectDocumentRequestError as error:
            return self.error(str(error), 400)
        except LookupError as error:
            return self.error(str(error), 404)

        return self.ok({"folder": folder}, 201)

    def handle_project_document_folders_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            folder_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": folder_id}, "id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            payload = self.project_document_service.delete_folder(folder_id)
        except LookupError as error:
            return self.error(str(error), 404)

        return self.ok(payload)

    def handle_project_models_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            project_id = self.parse_int(request.args.get("project_id"), "project_id")
            self.require_fields({"project_id": project_id}, "project_id")
        except ValueError as error:
            return self.error(str(error), 400)

        try:
            payload = self.project_service.list_project_models(project_id)
        except ProjectResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok(payload)

    def handle_project_models_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            project_model_id = self.parse_int(data.get("id"), "id")
            self.require_fields({"id": project_model_id}, "id")
            project_model = self.project_service.update_project_model(project_model_id, data)
        except ProjectResourceNotFoundError as error:
            return self.error(str(error), 404)
        except (ProjectRequestError, ValueError) as error:
            return self.error(str(error), 400)

        return self.ok({"model": project_model})

    def handle_project_models_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            project_id = self.parse_int(data.get("project_id"), "project_id")
            self.require_fields({"project_id": project_id}, "project_id")
            project_model = self.project_service.create_project_model(project_id, data)
        except ProjectResourceNotFoundError as error:
            return self.error(str(error), 404)
        except (ProjectRequestError, ValueError) as error:
            return self.error(str(error), 400)

        return self.ok({"model": project_model}, 201)

    def handle_project_models_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            project_model_id = self.parse_int(request.args.get("id"), "id")
            self.require_fields({"id": project_model_id}, "id")
            payload = self.project_service.delete_project_model(project_model_id)
        except ProjectResourceNotFoundError as error:
            return self.error(str(error), 404)
        except (ProjectRequestError, ValueError) as error:
            return self.error(str(error), 400)

        return self.ok(payload)
