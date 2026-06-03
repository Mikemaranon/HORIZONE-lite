from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import ModelConfigService, RequestError, ResourceNotFoundError


class ModelsAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        self.model_config_service = (
            self.services.model_config_service
            if self.services
            else ModelConfigService(self.db)
        )

    def register(self):
        self.app.add_url_rule("/api/models", view_func=self.get_models, methods=["GET"])
        self.app.add_url_rule("/api/models", view_func=self.create_model, methods=["POST"])
        self.app.add_url_rule("/api/models", view_func=self.update_model, methods=["PATCH"])
        self.app.add_url_rule("/api/models", view_func=self.delete_model, methods=["DELETE"])

    def get_models(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            if request.args.get("id"):
                return self.ok({"model": self.model_config_service.get_model(request.args.get("id"))})
            return self.ok({"models": self.model_config_service.list_models()})
        except (RequestError, ResourceNotFoundError) as error:
            return self.error_from_exception(error)

    def create_model(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            model = self.model_config_service.create_model(self.get_request_json(request))
        except RequestError as error:
            return self.error_from_exception(error)

        return self.ok({"model": model}, 201)

    def update_model(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            model = self.model_config_service.update_model(self.get_request_json(request))
        except (RequestError, ResourceNotFoundError) as error:
            return self.error_from_exception(error)

        return self.ok({"model": model})

    def delete_model(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.model_config_service.delete_model(request.args.get("id"))
        except (RequestError, ResourceNotFoundError) as error:
            return self.error_from_exception(error)

        return self.ok(payload)
