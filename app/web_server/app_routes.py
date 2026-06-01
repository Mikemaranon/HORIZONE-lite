# web_server/app_routes.py

from flask import render_template, redirect, request, url_for, jsonify
from user_m import UserManager
from data_m import DBManager

class AppRoutes:
    def __init__(self, app, user_manager: UserManager, DBManager: DBManager, config_manager=None):
        self.app = app
        self.user_manager = user_manager
        self.DBManager = DBManager
        self.config_manager = config_manager
        self._register_routes()
    
    # ==================================================================================
    #                     REGISTERING ROUTES AND APIs
    #
    #            [_register_routes]     instance of every basic route 
    #            [_register_APIs]       instance of every API
    # ================================================================================== 

    def _register_routes(self):
        self.app.add_url_rule("/", "home", self.get_home, methods=["GET"])
        self.app.add_url_rule("/index", "index", self.get_index)
        self.app.add_url_rule("/settings", "settings", self.get_settings)
        self.app.add_url_rule("/login", "login", self.get_login, methods=["GET", "POST"])
        self.app.add_url_rule("/logout", "logout", self.get_logout, methods=["POST"])

    # ==================================================================================
    #                           BASIC ROUTINGS URLs
    #
    #            [get_home]             check user and redirect to get_index
    #            [get_index]            go to index.html
    #            [get_login]            log user and send his token
    #            [get_logout]           log user out, send to index.html 
    # ================================================================================== 
    
    def get_index(self):
        if not self.user_manager.check_user(request):
            return redirect(url_for("login"))
        return render_template("index.html")

    def get_settings(self):
        if not self.user_manager.check_user(request):
            return redirect(url_for("login"))
        return render_template("settings.html")
    
    def get_home(self):
        user = self.user_manager.check_user(request)
        if user:            
            return redirect(url_for("index"))  # Redirect to index.html
        return render_template("login.html")

    def get_login(self):
        error_message = None
        if request.method == "POST":
            data = request.get_json()

            username = data.get("username")
            password = data.get("password")

            token = self.user_manager.login(username, password)
            if token:
                payload = {"ok": True}
                if self._should_return_token_in_body():
                    payload["token"] = token
                response = jsonify(payload)
                response.set_cookie(
                    "token",
                    token,
                    httponly=True,
                    secure=request.is_secure,
                    samesite="Lax",
                    max_age=60 * 60,
                )
                return response
            
            error_message = "incorrect user data, try again"

        return render_template("login.html", error_message=error_message)

    def get_logout(self):
        
        token = self.user_manager.get_token_from_cookie(request)
        if not token:
            token = self.user_manager.get_request_token(request)
        
        if token:
            self.user_manager.logout(token)
        response = redirect(url_for("login"))
        response.delete_cookie("token", samesite="Lax")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    def _should_return_token_in_body(self):
        runtime = getattr(self.config_manager, "runtime", None)
        return bool(getattr(runtime, "return_token_in_login_response", False))
    
