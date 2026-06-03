import pkgutil
import importlib

from flask import jsonify
from user_m import UserManager
from data_m import DBManager as DBManagerClass
from model_m import ModelManager
from config_m import ConfigManager

from service_registry import ServiceRegistry


class ApiManager:
    def __init__(
        self,
        app,
        user_manager: UserManager | None = None,
        db_manager: DBManagerClass | None = None,
        model_manager: ModelManager | None = None,
        services: ServiceRegistry | None = None,
        DBManager: DBManagerClass | None = None,
    ):
        self.app = app
        resolved_db_manager = db_manager or DBManager
        self.services = services or self._build_services(
            user_manager=user_manager,
            db_manager=resolved_db_manager,
            model_manager=model_manager,
        )
        self.user_manager = self.services.user_manager
        self.db_manager = self.services.db_manager
        self.model_manager = self.services.model_manager
        self._register_apis()
        self._autoload_domains()

    def _register_apis(self):
        self.app.add_url_rule("/api/check", "check", self.API_check, methods=["GET"])

    def _autoload_domains(self):
        import api_m.domains as domains_package

        for _, module_name, _ in pkgutil.iter_modules(domains_package.__path__):
            full_module = f"{domains_package.__name__}.{module_name}"
            module = importlib.import_module(full_module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)

                if (
                    isinstance(attr, type)
                    and hasattr(attr, "register")
                    and attr.__name__ != "BaseAPI"
                ):
                    api_instance = attr(self.app, services=self.services)
                    api_instance.register()
                    self.app.logger.debug("Loaded API: %s", attr.__name__)

    def API_check(self):
        return jsonify({"status": "ok"}), 200

    def _build_services(self, user_manager, db_manager, model_manager):
        if not user_manager or not db_manager or not model_manager:
            raise ValueError(
                "ApiManager requires either a ServiceRegistry or the core managers."
            )

        config_manager = getattr(model_manager, "config_manager", None)
        if not isinstance(config_manager, ConfigManager):
            raise ValueError("ModelManager must expose a valid ConfigManager.")

        return ServiceRegistry(
            config_manager=config_manager,
            db_manager=db_manager,
            user_manager=user_manager,
            model_manager=model_manager,
        )
