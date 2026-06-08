from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import (
    ConflictError,
    ProviderConfigService,
    RequestError,
    ResourceNotFoundError,
)


class ProvidersAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        self.provider_config_service = (
            self.services.provider_config_service
            if self.services
            else ProviderConfigService(self.db, self.model_manager)
        )

    def register(self):
        self.app.add_url_rule("/api/providers", view_func=self.handle_providers_get, methods=["GET"])
        self.app.add_url_rule("/api/providers", view_func=self.handle_providers_post, methods=["POST"])
        self.app.add_url_rule("/api/providers", view_func=self.handle_providers_patch, methods=["PATCH"])
        self.app.add_url_rule("/api/providers", view_func=self.handle_providers_delete, methods=["DELETE"])
        self.app.add_url_rule("/api/providers/restore", view_func=self.handle_providers_restore, methods=["POST"])
        self.app.add_url_rule("/api/providers/test", view_func=self.handle_providers_test, methods=["POST"])

    def handle_providers_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            if request.args.get("id"):
                provider = self.provider_config_service.get_provider(request.args.get("id"))
                return self.ok({"provider": provider})
            return self.ok({"providers": self.provider_config_service.list_providers()})
        except (RequestError, ResourceNotFoundError, ConflictError) as error:
            return self.error_from_exception(error)

    def handle_providers_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            provider = self.provider_config_service.create_provider(self.get_request_json(request))
        except RequestError as error:
            return self.error_from_exception(error)

        return self.ok({"provider": provider}, 201)

    def handle_providers_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            provider = self.provider_config_service.update_provider(self.get_request_json(request))
        except (RequestError, ResourceNotFoundError, ConflictError) as error:
            return self.error_from_exception(error)

        return self.ok({"provider": provider})

    def handle_providers_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.provider_config_service.delete_provider(request.args.get("id"))
        except (RequestError, ResourceNotFoundError, ConflictError) as error:
            return self.error_from_exception(error)

        return self.ok(payload)

    def handle_providers_restore(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            provider = self.provider_config_service.restore_provider(self.get_request_json(request))
        except (RequestError, ResourceNotFoundError) as error:
            return self.error_from_exception(error)

        return self.ok({"provider": provider})

    def handle_providers_test(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.provider_config_service.test_provider_connection(
                self.get_request_json(request),
            )
        except RequestError as error:
            return self.error_from_exception(error)

        return self.ok(payload)
