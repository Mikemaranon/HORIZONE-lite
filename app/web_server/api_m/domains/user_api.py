# api_m/domains/users_api.py

from flask import request
from api_m.domains.base_api import BaseAPI

class UserAPI(BaseAPI):

    def register(self):
        self.app.add_url_rule("/api/users/register", view_func=self.register_user, methods=["POST"])
        self.app.add_url_rule("/api/users/me", view_func=self.get_current_user, methods=["GET"])
        self.app.add_url_rule("/api/users/me", view_func=self.update_current_user, methods=["PATCH"])
        self.app.add_url_rule("/api/users/get", view_func=self.get_user, methods=["POST"])
        self.app.add_url_rule("/api/users/all", view_func=self.get_all_users, methods=["GET"])
        self.app.add_url_rule("/api/users/delete", view_func=self.delete_user, methods=["DELETE"])

    # ============================================================
    #                       ENDPOINTS
    # ============================================================

    def register_user(self):
        runtime = getattr(self.config_manager, "runtime", None)
        if not getattr(runtime, "allow_public_registration", False):
            return self.error("Public registration is disabled", 403)
        
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return self.error("Missing username or password", 400)

        # Create user through UserManager
        created = self.user_manager.create_user(username, password)

        if not created:
            return self.error("User already exists", 400)

        return self.ok({"message": "User created successfully"}, 201)

    def get_current_user(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        token = self.user_manager.get_token_from_cookie(request)
        if not token:
            token = self.user_manager.get_request_token(request)

        user = self.user_manager.get_user(token)
        if not user:
            return self.error("User not found", 404)

        user.pop("password", None)
        return self.ok({"user": user})

    def update_current_user(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        token = self.user_manager.get_token_from_cookie(request)
        if not token:
            token = self.user_manager.get_request_token(request)

        data = self.get_request_json(request)
        current_password = data.get("current_password", "")
        username = data.get("username")
        password = data.get("password")

        if username is None and password is None:
            return self.error("Nothing to update", 400)

        try:
            user, refreshed_token = self.user_manager.update_user_credentials(
                token=token,
                current_password=current_password,
                new_username=username,
                new_password=password,
            )
        except ValueError as error:
            message = str(error)
            status_code = 401 if message == "Unauthorized" else 400
            return self.error(message, status_code)

        payload = {
            "message": "Session profile updated.",
            "user": user,
        }
        runtime = getattr(self.config_manager, "runtime", None)
        if getattr(runtime, "return_token_in_login_response", False):
            payload["token"] = refreshed_token

        response, status_code = self.ok(payload)
        response.set_cookie(
            "token",
            refreshed_token,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            max_age=60 * 60,
        )
        return response, status_code

    def get_user(self):

        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = request.get_json()
        username = data.get("username")

        if not username:
            return self.error("Missing username", 400)

        user = self.db.users.get(username)
        if not user:
            return self.error("User not found", 404)

        user.pop("password", None)
        return self.ok(user)


    def get_all_users(self):
 
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        users = self.db.users.all()

        for u in users:
            u.pop("password", None)

        return self.ok({"users": users})


    def delete_user(self):
 
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = request.get_json()
        username = data.get("username")

        if not username:
            return self.error("Missing username", 400)

        deleted = self.db.users.delete(username)
        if not deleted:
            return self.error("User not found", 404)

        return self.ok({"message": "User deleted successfully"})
