from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import ProfileService, RequestError, ResourceNotFoundError


class ProfilesAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        self.profile_service = (
            self.services.profile_service
            if self.services
            else ProfileService(self.db)
        )

    def register(self):
        self.app.add_url_rule("/api/profiles", view_func=self.handle_profiles_get, methods=["GET"])
        self.app.add_url_rule("/api/profiles", view_func=self.handle_profiles_post, methods=["POST"])
        self.app.add_url_rule("/api/profiles", view_func=self.handle_profiles_patch, methods=["PATCH"])
        self.app.add_url_rule("/api/profiles", view_func=self.handle_profiles_delete, methods=["DELETE"])

    def handle_profiles_get(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            if request.args.get("id"):
                return self.ok({"profile": self.profile_service.get_profile(request.args.get("id"))})
            return self.ok({"profiles": self.profile_service.list_profiles()})
        except RequestError as error:
            return self.error(str(error), 400)
        except ResourceNotFoundError as error:
            return self.error(str(error), 404)

    def handle_profiles_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            profile = self.profile_service.create_profile(self.get_request_json(request))
        except RequestError as error:
            return self.error(str(error), 400)

        return self.ok({"profile": profile}, 201)

    def handle_profiles_patch(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            profile = self.profile_service.update_profile(self.get_request_json(request))
        except RequestError as error:
            return self.error(str(error), 400)
        except ResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok({"profile": profile})

    def handle_profiles_delete(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        try:
            payload = self.profile_service.delete_profile(request.args.get("id"))
        except RequestError as error:
            return self.error(str(error), 400)
        except ResourceNotFoundError as error:
            return self.error(str(error), 404)

        return self.ok(payload)
