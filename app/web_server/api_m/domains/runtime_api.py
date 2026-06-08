from flask import request

from api_m.domains.base_api import BaseAPI
from runtime_m import RuntimeConflictError, RuntimeRequestError, RuntimeResourceNotFoundError


class RuntimeAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        self.catalog_service = self.services.runtime_model_catalog_service
        self.download_service = self.services.runtime_model_download_service

    def register(self):
        self.app.add_url_rule(
            "/api/runtime/models/catalog",
            view_func=self.get_runtime_model_catalog,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/runtime/models/catalog/search",
            view_func=self.search_runtime_model_catalog,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/runtime/models/downloads",
            view_func=self.get_runtime_model_downloads,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/runtime/models/downloads",
            view_func=self.create_runtime_model_download,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/runtime/models/downloads/cancel",
            view_func=self.cancel_runtime_model_download,
            methods=["POST"],
        )

    def get_runtime_model_catalog(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            return self.ok({"catalog": self.catalog_service.list_catalog()})
        except (RuntimeRequestError, RuntimeResourceNotFoundError, RuntimeConflictError, ValueError) as error:
            return self.error_from_exception(error)

    def search_runtime_model_catalog(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            return self.ok(
                {
                    "catalog": self.catalog_service.search_huggingface_catalog(
                        request.args.get("query"),
                    )
                }
            )
        except (RuntimeRequestError, RuntimeResourceNotFoundError, RuntimeConflictError, ValueError) as error:
            return self.error_from_exception(error)

    def get_runtime_model_downloads(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            if request.args.get("id"):
                return self.ok(
                    {
                        "download": self.download_service.get_download(
                            request.args.get("id"),
                        )
                    }
                )
            return self.ok({"downloads": self.download_service.list_downloads()})
        except (RuntimeRequestError, RuntimeResourceNotFoundError, RuntimeConflictError) as error:
            return self.error_from_exception(error)

    def create_runtime_model_download(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.download_service.start_download(
                self.get_request_json(request).get("catalog_key"),
            )
        except (RuntimeRequestError, RuntimeResourceNotFoundError, RuntimeConflictError) as error:
            return self.error_from_exception(error)

        return self.ok(payload, 202)

    def cancel_runtime_model_download(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.download_service.cancel_download(
                self.get_request_json(request).get("id"),
            )
        except (RuntimeRequestError, RuntimeResourceNotFoundError, RuntimeConflictError) as error:
            return self.error_from_exception(error)

        return self.ok({"download": payload})
