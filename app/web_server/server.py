import atexit

from flask import Flask

from config_m import ConfigManager
from data_m import DBManager
from model_m import ModelManager
from runtime_m import LlamaCppRuntimeManager
from user_m import UserManager
from api_m import ApiManager
from app_routes import AppRoutes
from service_registry import ServiceRegistry


class Server:
    def __init__(self, app: Flask):
        self.app = app

        self.config_manager = self.init_config_manager()
        self.app.secret_key = self.config_manager.runtime.secret_key

        self.db_manager = self.init_db_manager()
        self.user_manager = self.init_user_manager()
        self.runtime_manager = self.init_runtime_manager()
        self.model_manager = self.init_model_manager()
        self.services = self.init_service_registry()
        self.app_routes = self.init_app_routes()
        self.api_manager = self.init_api_manager()

        self.run()

    def init_config_manager(self):
        return ConfigManager()

    def init_db_manager(self):
        return DBManager()

    def init_user_manager(self):
        runtime = self.config_manager.runtime
        return UserManager(
            db_manager=self.db_manager,
            secret_key=runtime.secret_key,
            bootstrap_admin_password=runtime.bootstrap_admin_password,
            allow_insecure_default_admin=runtime.allow_insecure_default_admin,
        )

    def init_model_manager(self):
        return ModelManager(
            self.config_manager,
            self.db_manager,
            runtime_manager=self.runtime_manager,
        )

    def init_runtime_manager(self):
        runtime_manager = LlamaCppRuntimeManager(
            config_manager=self.config_manager,
            db_manager=self.db_manager,
        )
        runtime_manager.start_if_available()
        atexit.register(runtime_manager.stop)
        return runtime_manager

    def init_service_registry(self):
        return ServiceRegistry(
            config_manager=self.config_manager,
            db_manager=self.db_manager,
            user_manager=self.user_manager,
            model_manager=self.model_manager,
        )

    def init_app_routes(self):
        return AppRoutes(
            self.app,
            self.user_manager,
            self.db_manager,
            self.config_manager,
        )

    def init_api_manager(self):
        return ApiManager(self.app, services=self.services)

    def run(self):
        runtime = self.config_manager.runtime
        self.app.run(
            debug=runtime.debug,
            host=runtime.host,
            port=runtime.port,
        )
