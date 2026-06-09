import os
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .model_file_validator import RuntimeModelFileValidationError, RuntimeModelFileValidator
from .process_supervisor import ProcessSupervisor
from .runtime_paths import RuntimePaths


@dataclass(frozen=True)
class RuntimeModelSelection:
    model_config_id: int
    model_name: str
    model_path: str


class LlamaCppRuntimeManager:
    HOST = "127.0.0.1"
    STARTUP_TIMEOUT_SECONDS = 180

    def __init__(
        self,
        *,
        config_manager,
        db_manager,
        paths=None,
        supervisor=None,
        model_file_validator=None,
        environ=None,
        runtime_probe=None,
    ):
        self.config_manager = config_manager
        self.db = db_manager
        self.runtime_config = config_manager.runtime
        self.paths = paths or RuntimePaths(self.runtime_config)
        self.supervisor = supervisor or ProcessSupervisor()
        self.model_file_validator = model_file_validator or RuntimeModelFileValidator()
        self.environ = environ if environ is not None else os.environ
        self.runtime_probe = runtime_probe or self._probe_existing_runtime
        self.status = "stopped"
        self.error_message = ""
        self.active_model = None
        self.active_port = self.runtime_config.llama_cpp_port
        self._runtime_lock = threading.Lock()

    def start_if_available(self, model_config_id=None, model_name=None):
        with self._runtime_lock:
            return self._start_if_available(
                model_config_id=model_config_id,
                model_name=model_name,
            )

    def _start_if_available(self, model_config_id=None, model_name=None):
        self.db.providers.ensure_seed_providers()
        self.error_message = ""

        if self.runtime_config.runtime_disabled:
            self.status = "stopped"
            return self.snapshot()

        if not self._should_start_in_current_process():
            self.status = "stopped"
            return self.snapshot()

        model = self.select_ready_model(
            model_config_id=model_config_id,
            model_name=model_name,
        )
        if not model:
            self.status = "error" if self.error_message else "stopped"
            return self.snapshot()

        if self._is_active_model(model) and self._owns_running_process():
            self.status = "ready"
            return self.snapshot()

        if self.active_model and not self._is_active_model(model) and self._owns_running_process():
            self.supervisor.stop()
            self.active_model = None

        launch_command = self._resolve_launch_command()
        if not launch_command:
            self.status = "error"
            self.error_message = (
                "HORIZONE runtime needs llama-server or llama-cpp-python. "
                "Install llama.cpp's llama-server, set HORIZONE_LLAMA_CPP_BINARY, "
                "or install project requirements in the active Python environment."
            )
            return self.snapshot()

        conflict_messages = []
        for port in self.iter_candidate_ports():
            self.active_port = port
            existing_runtime = self.runtime_probe(model)
            if existing_runtime == "matching":
                self.status = "ready"
                self.active_model = model
                return self.snapshot()
            if existing_runtime == "conflict":
                if self.error_message:
                    conflict_messages.append(self.error_message)
                continue

            command = self.build_command(launch_command, model)
            started = self.supervisor.start(
                command,
                health_urls=self.health_urls(),
                timeout_seconds=self.STARTUP_TIMEOUT_SECONDS,
                env=self.build_environment(launch_command),
            )
            self.status = self.supervisor.status
            self.error_message = self.supervisor.error_message
            self.active_model = model if started else None
            if started:
                return self.snapshot()

        self.status = "error"
        self.active_model = None
        if not self.error_message:
            self.error_message = self._build_port_range_error(conflict_messages)
        return self.snapshot()

    def stop(self):
        with self._runtime_lock:
            self.supervisor.stop()
            self.status = self.supervisor.status
            self.active_model = None

    def select_default_ready_model(self):
        return self.select_ready_model()

    def select_ready_model(self, model_config_id=None, model_name=None):
        requested_model_config_id = self._parse_optional_int(model_config_id)
        requested_model_name = str(model_name or "").strip()
        invalid_filenames = []
        for download in self.db.runtime_model_downloads.ready():
            model_path = Path(download["local_path"]).expanduser()
            if not model_path.is_file():
                continue
            try:
                self.model_file_validator.inspect_installed_chat_model_file(model_path)
            except RuntimeModelFileValidationError:
                invalid_filenames.append(model_path.name)
                continue

            model_config = self.db.models.get(download["model_config_id"])
            if not model_config or model_config.get("provider") != "llama_cpp":
                continue

            selection = RuntimeModelSelection(
                model_config_id=model_config["id"],
                model_name=model_config["name"],
                model_path=str(model_path),
            )

            if requested_model_config_id and selection.model_config_id != requested_model_config_id:
                continue
            if (
                not requested_model_config_id
                and requested_model_name
                and selection.model_name != requested_model_name
            ):
                continue

            return selection

        if invalid_filenames:
            names = ", ".join(sorted(set(invalid_filenames)))
            self.error_message = (
                "Installed HORIZONE runtime file is not a chat model: "
                f"{names}. Download a text/chat GGUF model instead of an mmproj projector file."
            )
        elif requested_model_config_id or requested_model_name:
            self.error_message = "Selected HORIZONE runtime model is not installed or ready."

        return None

    def build_command(self, launch_command, model):
        command = list(launch_command)
        if self._is_llama_cpp_python_server(command):
            model_args = ["--model", model.model_path, "--model_alias", model.model_name]
        else:
            model_args = ["-m", model.model_path, "--alias", model.model_name]

        return [
            *command,
            *model_args,
            "--host",
            self.HOST,
            "--port",
            str(self.active_port),
        ]

    def build_environment(self, launch_command):
        environment = dict(self.environ)
        if self._is_llama_cpp_python_server(list(launch_command)):
            environment.setdefault("GGML_METAL_DEVICES", "-1")
        return environment

    def health_urls(self):
        base_url = self.base_url()
        return [
            f"{base_url}/health",
            f"{base_url}/v1/health",
            f"{base_url}/v1/models",
        ]

    def base_url(self):
        return f"http://{self.HOST}:{self.active_port}"

    def snapshot(self):
        return {
            "status": self.status,
            "error_message": self.error_message,
            "base_url": self.base_url(),
            "openai_base_url": f"{self.base_url()}/v1",
            "port": self.active_port,
            "port_range": {
                "start": self.runtime_config.llama_cpp_port,
                "end": getattr(
                    self.runtime_config,
                    "llama_cpp_port_max",
                    self.runtime_config.llama_cpp_port,
                ),
            },
            "active_model": {
                "model_config_id": self.active_model.model_config_id,
                "model_name": self.active_model.model_name,
                "model_path": self.active_model.model_path,
            }
            if self.active_model
            else None,
        }

    def _should_start_in_current_process(self):
        if not self.runtime_config.debug:
            return True

        return self.environ.get("WERKZEUG_RUN_MAIN") == "true"

    def _resolve_launch_command(self):
        if hasattr(self.paths, "resolve_llama_server_launch_command"):
            return self.paths.resolve_llama_server_launch_command()

        binary_path = self.paths.resolve_llama_server_binary()
        return [binary_path] if binary_path else []

    def iter_candidate_ports(self):
        start_port = self._parse_optional_int(self.runtime_config.llama_cpp_port) or 8080
        end_port = (
            self._parse_optional_int(getattr(self.runtime_config, "llama_cpp_port_max", None))
            or start_port
        )
        if end_port < start_port:
            end_port = start_port

        if self.active_port and start_port <= self.active_port <= end_port:
            yield self.active_port

        for port in range(start_port, end_port + 1):
            if port == self.active_port:
                continue
            yield port

    def _is_llama_cpp_python_server(self, command):
        return len(command) >= 3 and command[-2:] == ["-m", "llama_cpp.server"]

    def _probe_existing_runtime(self, model):
        try:
            with urlopen(f"{self.base_url()}/v1/models", timeout=1) as response:
                if response.status < 200 or response.status >= 300:
                    return None
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            return None

        model_ids = self._extract_runtime_model_ids(payload)
        if model.model_name in model_ids:
            return "matching"

        loaded_models = ", ".join(sorted(model_ids)) or "unknown model"
        self.error_message = (
            f"HORIZONE runtime port {self.active_port} is already in use "
            f"by another llama.cpp server loaded with {loaded_models}. Stop that server, "
            "or set HORIZONE_LLAMA_CPP_PORT to a free port before starting HORIZONE."
        )
        return "conflict"

    def _extract_runtime_model_ids(self, payload):
        if not isinstance(payload, dict):
            return set()

        model_ids = set()
        for item in payload.get("data") or []:
            if isinstance(item, dict) and item.get("id"):
                model_ids.add(str(item["id"]))
        return model_ids

    def _is_active_model(self, model):
        return bool(
            self.active_model
            and self.active_model.model_config_id == model.model_config_id
            and self.active_model.model_name == model.model_name
            and self.active_model.model_path == model.model_path
        )

    def _owns_running_process(self):
        is_running = getattr(self.supervisor, "is_running", None)
        return bool(is_running and is_running())

    def _parse_optional_int(self, raw_value):
        if raw_value is None or raw_value == "":
            return None

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _build_port_range_error(self, conflict_messages):
        start_port = self.runtime_config.llama_cpp_port
        end_port = getattr(self.runtime_config, "llama_cpp_port_max", start_port)
        if conflict_messages:
            return (
                f"No free HORIZONE runtime port was available in {start_port}-{end_port}. "
                f"Last conflict: {conflict_messages[-1]}"
            )

        return f"No free HORIZONE runtime port was available in {start_port}-{end_port}."
