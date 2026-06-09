import os
import json
import struct
import subprocess
from pathlib import Path

from config_m import ConfigManager
from data_m import DBManager
from runtime_m import (
    LlamaCppRuntimeManager,
    ProcessSupervisor,
    RuntimeModelCatalogService,
    RuntimeModelDownloadService,
    RuntimeRequestError,
)
from tests.test_support import IsolatedDatabaseTestCase


class FakePaths:
    def __init__(self, binary_path="/usr/local/bin/llama-server", launch_command=None):
        self.binary_path = binary_path
        self.launch_command = launch_command

    def resolve_llama_server_binary(self):
        return self.binary_path

    def resolve_llama_server_launch_command(self):
        if self.launch_command is not None:
            return self.launch_command
        return [self.binary_path] if self.binary_path else []


class FakeSupervisor:
    def __init__(self, status="ready"):
        self.start_status = status
        self.status = "stopped"
        self.error_message = ""
        self.start_calls = []
        self.stop_called = False
        self.stop_calls = 0
        self.running = False

    def start(self, command, *, health_urls=None, timeout_seconds=30, env=None):
        self.start_calls.append(
            {
                "command": command,
                "health_urls": health_urls,
                "timeout_seconds": timeout_seconds,
                "env": env or {},
            }
        )
        self.status = self.start_status
        self.running = self.start_status == "ready"
        return self.running

    def stop(self):
        self.stop_called = True
        self.stop_calls += 1
        self.running = False
        self.status = "stopped"

    def is_running(self):
        return self.running


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if not self.terminated and not self.killed else 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


class FakeExitedProcess:
    def poll(self):
        return 1

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 1


class SyncThread:
    def __init__(self, target, *args):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


class FakeDownloadResponse:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.headers = {
            "Content-Length": str(sum(len(chunk) for chunk in self.chunks)),
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class FakeJsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def build_fake_gguf(metadata):
    payload = bytearray()
    payload.extend(b"GGUF")
    payload.extend(struct.pack("<I", 3))
    payload.extend(struct.pack("<Q", 0))
    payload.extend(struct.pack("<Q", len(metadata)))
    for key, value in metadata.items():
        encoded_key = key.encode("utf-8")
        encoded_value = str(value).encode("utf-8")
        payload.extend(struct.pack("<Q", len(encoded_key)))
        payload.extend(encoded_key)
        payload.extend(struct.pack("<I", 8))
        payload.extend(struct.pack("<Q", len(encoded_value)))
        payload.extend(encoded_value)
    return bytes(payload)


def build_fake_gguf_with_large_metadata_array(metadata):
    payload = bytearray()
    payload.extend(b"GGUF")
    payload.extend(struct.pack("<I", 3))
    payload.extend(struct.pack("<Q", 0))
    payload.extend(struct.pack("<Q", len(metadata) + 1))

    array_key = "tokenizer.ggml.tokens".encode("utf-8")
    payload.extend(struct.pack("<Q", len(array_key)))
    payload.extend(array_key)
    payload.extend(struct.pack("<I", 9))
    payload.extend(struct.pack("<I", 8))
    payload.extend(struct.pack("<Q", 100_001))
    for _ in range(100_001):
        payload.extend(struct.pack("<Q", 0))

    for key, value in metadata.items():
        encoded_key = key.encode("utf-8")
        encoded_value = str(value).encode("utf-8")
        payload.extend(struct.pack("<Q", len(encoded_key)))
        payload.extend(encoded_key)
        payload.extend(struct.pack("<I", 8))
        payload.extend(struct.pack("<Q", len(encoded_value)))
        payload.extend(encoded_value)
    return bytes(payload)


def fake_chat_gguf(architecture="llama"):
    return build_fake_gguf(
        {
            "general.architecture": architecture,
            "general.type": "model",
        }
    )


def fake_mmproj_gguf():
    return build_fake_gguf(
        {
            "general.architecture": "clip",
            "general.type": "mmproj",
        }
    )


class LlamaCppRuntimeManagerTests(IsolatedDatabaseTestCase):
    def tearDown(self):
        for key in [
            "FLASK_DEBUG",
            "HORIZONE_LLAMA_CPP_BINARY",
            "HORIZONE_LLAMA_CPP_PORT",
            "HORIZONE_LLAMA_CPP_PORT_MAX",
            "HORIZONE_RUNTIME_DISABLED",
            "HORIZONE_RUNTIME_MODELS_DIR",
            "WERKZEUG_RUN_MAIN",
        ]:
            os.environ.pop(key, None)
        super().tearDown()

    def test_does_not_start_without_ready_model(self):
        db = DBManager()
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths(),
            supervisor=supervisor,
        )
        snapshot = manager.start_if_available()

        self.assertEqual(snapshot["status"], "stopped")
        self.assertEqual(supervisor.start_calls, [])

    def test_starts_llama_server_for_latest_ready_model(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create(
            name="gemma-runtime",
            provider_config_id=runtime_provider["id"],
        )
        db.runtime_model_downloads.create(
            catalog_key="gemma-runtime",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
        )
        snapshot = manager.start_if_available()

        command = supervisor.start_calls[0]["command"]
        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(command[0], "/opt/llama-server")
        self.assertEqual(command[1:3], ["-m", str(model_path)])
        self.assertIn("--alias", command)
        self.assertIn("gemma-runtime", command)
        self.assertEqual(supervisor.start_calls[0]["health_urls"][0], "http://127.0.0.1:8080/health")
        self.assertIn("http://127.0.0.1:8080/v1/models", supervisor.start_calls[0]["health_urls"])
        self.assertEqual(snapshot["active_model"]["model_config_id"], model_id)

    def test_uses_next_port_when_first_runtime_port_is_in_conflict(self):
        os.environ["HORIZONE_LLAMA_CPP_PORT"] = "8080"
        os.environ["HORIZONE_LLAMA_CPP_PORT_MAX"] = "8081"
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-model", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-model",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()
        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
        )

        def conflict_on_first_port(model):
            if manager.active_port == 8080:
                manager.error_message = "port 8080 is already in use"
                return "conflict"
            return None

        manager.runtime_probe = conflict_on_first_port
        snapshot = manager.start_if_available(model_config_id=model_id)

        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(snapshot["port"], 8081)
        self.assertEqual(snapshot["base_url"], "http://127.0.0.1:8081")
        self.assertIn("8081", supervisor.start_calls[0]["command"])
        self.assertEqual(supervisor.start_calls[0]["health_urls"][0], "http://127.0.0.1:8081/health")

    def test_starts_requested_ready_model_instead_of_latest_ready_model(self):
        db = DBManager()
        first_model_path = Path(self.temp_dir.name) / "first.gguf"
        second_model_path = Path(self.temp_dir.name) / "second.gguf"
        first_model_path.write_text("gguf", encoding="utf-8")
        second_model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        first_model_id = db.models.create("first-runtime", runtime_provider["id"])
        second_model_id = db.models.create("second-runtime", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="first-runtime",
            status="ready",
            source_url="https://example.test/first.gguf",
            filename="first.gguf",
            model_config_id=first_model_id,
            local_path=str(first_model_path),
        )
        db.runtime_model_downloads.create(
            catalog_key="second-runtime",
            status="ready",
            source_url="https://example.test/second.gguf",
            filename="second.gguf",
            model_config_id=second_model_id,
            local_path=str(second_model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
        )
        snapshot = manager.start_if_available(model_config_id=first_model_id)

        command = supervisor.start_calls[0]["command"]
        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(command[1:3], ["-m", str(first_model_path)])
        self.assertIn("first-runtime", command)
        self.assertEqual(snapshot["active_model"]["model_config_id"], first_model_id)

    def test_hot_swaps_owned_runtime_when_requested_model_changes(self):
        db = DBManager()
        first_model_path = Path(self.temp_dir.name) / "first.gguf"
        second_model_path = Path(self.temp_dir.name) / "second.gguf"
        first_model_path.write_text("gguf", encoding="utf-8")
        second_model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        first_model_id = db.models.create("first-runtime", runtime_provider["id"])
        second_model_id = db.models.create("second-runtime", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="first-runtime",
            status="ready",
            source_url="https://example.test/first.gguf",
            filename="first.gguf",
            model_config_id=first_model_id,
            local_path=str(first_model_path),
        )
        db.runtime_model_downloads.create(
            catalog_key="second-runtime",
            status="ready",
            source_url="https://example.test/second.gguf",
            filename="second.gguf",
            model_config_id=second_model_id,
            local_path=str(second_model_path),
        )
        supervisor = FakeSupervisor()
        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
        )

        first_snapshot = manager.start_if_available(model_config_id=first_model_id)
        second_snapshot = manager.start_if_available(model_config_id=second_model_id)

        self.assertEqual(first_snapshot["active_model"]["model_config_id"], first_model_id)
        self.assertEqual(second_snapshot["active_model"]["model_config_id"], second_model_id)
        self.assertEqual(supervisor.stop_calls, 1)
        self.assertEqual(len(supervisor.start_calls), 2)
        self.assertEqual(supervisor.start_calls[1]["command"][1:3], ["-m", str(second_model_path)])
        self.assertIn("second-runtime", supervisor.start_calls[1]["command"])

    def test_reuses_owned_runtime_when_requested_model_is_already_active(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-model", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-model",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()
        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
        )

        manager.start_if_available(model_config_id=model_id)
        snapshot = manager.start_if_available(model_config_id=model_id)

        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(len(supervisor.start_calls), 1)
        self.assertEqual(supervisor.stop_calls, 0)

    def test_reuses_matching_runtime_already_listening_on_port(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-model", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-model",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
            runtime_probe=lambda model: "matching",
        )
        snapshot = manager.start_if_available()

        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(snapshot["active_model"]["model_name"], "runtime-model")
        self.assertEqual(supervisor.start_calls, [])

    def test_reports_conflicting_runtime_already_listening_on_port(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-model", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-model",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()
        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
        )

        def conflict_probe(model):
            manager.error_message = "port 8080 is already in use by another llama.cpp server"
            return "conflict"

        manager.runtime_probe = conflict_probe
        snapshot = manager.start_if_available()

        self.assertEqual(snapshot["status"], "error")
        self.assertIn("already in use", snapshot["error_message"])
        self.assertEqual(supervisor.start_calls, [])

    def test_missing_binary_sets_error_without_starting_process(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-model", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-model",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths(""),
            supervisor=supervisor,
        )
        snapshot = manager.start_if_available()

        self.assertEqual(snapshot["status"], "error")
        self.assertIn("llama-server", snapshot["error_message"])
        self.assertEqual(supervisor.start_calls, [])

    def test_starts_llama_cpp_python_server_when_binary_is_missing(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-model", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-model",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("", ["python", "-m", "llama_cpp.server"]),
            supervisor=supervisor,
        )
        snapshot = manager.start_if_available()

        command = supervisor.start_calls[0]["command"]
        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(command[:3], ["python", "-m", "llama_cpp.server"])
        self.assertIn("--model", command)
        self.assertIn(str(model_path), command)
        self.assertIn("--model_alias", command)
        self.assertIn("runtime-model", command)
        self.assertEqual(supervisor.start_calls[0]["env"]["GGML_METAL_DEVICES"], "-1")

    def test_preserves_configured_metal_device_filter_for_llama_cpp_python_server(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-model", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-model",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("", ["python", "-m", "llama_cpp.server"]),
            supervisor=supervisor,
            environ={"GGML_METAL_DEVICES": "0"},
        )
        manager.start_if_available()

        self.assertEqual(supervisor.start_calls[0]["env"]["GGML_METAL_DEVICES"], "0")

    def test_rejects_installed_mmproj_as_runtime_chat_model(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "mmproj-F16.gguf"
        model_path.write_bytes(fake_mmproj_gguf())
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-mmproj", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-mmproj",
            status="ready",
            source_url="https://example.test/mmproj-F16.gguf",
            filename="mmproj-F16.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
        )
        snapshot = manager.start_if_available()

        self.assertEqual(snapshot["status"], "error")
        self.assertIn("not a chat model", snapshot["error_message"])
        self.assertEqual(supervisor.start_calls, [])

    def test_rejects_installed_mmproj_metadata_even_when_filename_looks_like_model(self):
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "Kimi-K2.6-Q4_K_M.gguf"
        model_path.write_bytes(fake_mmproj_gguf())
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-kimi", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-kimi",
            status="ready",
            source_url="https://example.test/Kimi-K2.6-Q4_K_M.gguf",
            filename="Kimi-K2.6-Q4_K_M.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths("/opt/llama-server"),
            supervisor=supervisor,
        )
        snapshot = manager.start_if_available()

        self.assertEqual(snapshot["status"], "error")
        self.assertIn("Kimi-K2.6-Q4_K_M.gguf", snapshot["error_message"])
        self.assertEqual(supervisor.start_calls, [])

    def test_debug_reloader_parent_does_not_start_runtime(self):
        os.environ["FLASK_DEBUG"] = "true"
        db = DBManager()
        model_path = Path(self.temp_dir.name) / "model.gguf"
        model_path.write_text("gguf", encoding="utf-8")
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create("runtime-model", runtime_provider["id"])
        db.runtime_model_downloads.create(
            catalog_key="runtime-model",
            status="ready",
            source_url="https://example.test/model.gguf",
            filename="model.gguf",
            model_config_id=model_id,
            local_path=str(model_path),
        )
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths(),
            supervisor=supervisor,
            environ={},
        )
        snapshot = manager.start_if_available()

        self.assertEqual(snapshot["status"], "stopped")
        self.assertEqual(supervisor.start_calls, [])

    def test_runtime_disabled_does_not_start_runtime(self):
        os.environ["HORIZONE_RUNTIME_DISABLED"] = "true"
        db = DBManager()
        supervisor = FakeSupervisor()

        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            paths=FakePaths(),
            supervisor=supervisor,
        )
        snapshot = manager.start_if_available()

        self.assertEqual(snapshot["status"], "stopped")
        self.assertEqual(supervisor.start_calls, [])

    def test_stop_delegates_to_supervisor(self):
        db = DBManager()
        supervisor = FakeSupervisor()
        manager = LlamaCppRuntimeManager(
            config_manager=ConfigManager(),
            db_manager=db,
            supervisor=supervisor,
        )

        manager.stop()

        self.assertTrue(supervisor.stop_called)
        self.assertEqual(manager.status, "stopped")


class ProcessSupervisorTests(IsolatedDatabaseTestCase):
    def test_start_launches_process_and_waits_for_health(self):
        process = FakeProcess()
        launched = []

        def popen_factory(command, stdout=None, stderr=None):
            launched.append(
                {
                    "command": command,
                    "stdout": stdout,
                    "stderr": stderr,
                }
            )
            return process

        supervisor = ProcessSupervisor(
            popen_factory=popen_factory,
            health_probe=lambda url: url.endswith("/health"),
            sleeper=lambda seconds: None,
        )

        started = supervisor.start(
            ["llama-server", "-m", "model.gguf"],
            health_urls=["http://127.0.0.1:8080/health"],
        )

        self.assertTrue(started)
        self.assertEqual(supervisor.status, "ready")
        self.assertEqual(launched[0]["command"], ["llama-server", "-m", "model.gguf"])
        self.assertIsNotNone(launched[0]["stdout"])
        self.assertEqual(launched[0]["stderr"], subprocess.STDOUT)

        supervisor.stop()

        self.assertTrue(process.terminated)
        self.assertEqual(supervisor.status, "stopped")

    def test_start_reports_os_error(self):
        def failing_popen(command, stdout=None, stderr=None):
            raise OSError("missing binary")

        supervisor = ProcessSupervisor(popen_factory=failing_popen)

        started = supervisor.start(["missing"])

        self.assertFalse(started)
        self.assertEqual(supervisor.status, "error")
        self.assertIn("missing binary", supervisor.error_message)

    def test_start_preserves_process_exited_error(self):
        supervisor = ProcessSupervisor(
            popen_factory=lambda command, stdout=None, stderr=None: FakeExitedProcess(),
            health_probe=lambda url: False,
            sleeper=lambda seconds: None,
        )

        started = supervisor.start(
            ["llama-server", "-m", "bad.gguf"],
            health_urls=["http://127.0.0.1:8080/health"],
        )

        self.assertFalse(started)
        self.assertEqual(supervisor.status, "error")
        self.assertEqual(supervisor.error_message, "Runtime process exited before becoming ready.")

    def test_start_includes_runtime_log_when_process_exits(self):
        def popen_factory(command, stdout=None, stderr=None):
            stdout.write(b"{%- for message in messages %}\n")
            stdout.write(b"{{ tokenizer.chat_template }}\n")
            stdout.write(b"ggml_metal_init: error: failed to create command queue\n")
            stdout.write(b"ValueError: Failed to create llama_context\n")
            stdout.flush()
            return FakeExitedProcess()

        supervisor = ProcessSupervisor(
            popen_factory=popen_factory,
            health_probe=lambda url: False,
            sleeper=lambda seconds: None,
        )

        started = supervisor.start(
            ["llama-server", "-m", "bad.gguf"],
            health_urls=["http://127.0.0.1:8080/health"],
        )

        self.assertFalse(started)
        self.assertIn("Runtime process exited before becoming ready", supervisor.error_message)
        self.assertIn("failed to create command queue", supervisor.error_message)
        self.assertNotIn("tokenizer.chat_template", supervisor.error_message)


class RuntimeModelCatalogAndDownloadTests(IsolatedDatabaseTestCase):
    def test_huggingface_search_returns_empty_without_query(self):
        db = DBManager()
        calls = []
        service = RuntimeModelCatalogService(
            db_manager=db,
            opener=lambda request, timeout=None: calls.append(request),
        )

        catalog = service.search_huggingface_catalog("")

        self.assertEqual(catalog, [])
        self.assertEqual(calls, [])

    def test_huggingface_search_registers_downloadable_gguf_model(self):
        db = DBManager()
        calls = []

        def opener(request, timeout=None):
            calls.append(request.full_url)
            return FakeJsonResponse(
                [
                    {
                        "modelId": "Qwen/Qwen2.5-7B-Instruct-GGUF",
                        "tags": ["gguf", "license:apache-2.0"],
                        "siblings": [
                            {"rfilename": "qwen2.5-7b-instruct-q8_0.gguf", "size": 20},
                            {"rfilename": "qwen2.5-7b-instruct-q4_k_m.gguf", "size": 10},
                        ],
                    }
                ]
            )

        service = RuntimeModelCatalogService(db_manager=db, opener=opener)

        catalog = service.search_huggingface_catalog("qwen-7b")

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["display_name"], "Qwen2.5-7B-Instruct Q4_K_M")
        self.assertEqual(catalog[0]["filename"], "qwen2.5-7b-instruct-q4_k_m.gguf")
        self.assertEqual(catalog[0]["license"], "apache-2.0")
        self.assertIn("/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf", catalog[0]["source_url"])
        self.assertFalse(catalog[0]["is_installed"])
        self.assertIsNotNone(db.runtime_model_catalog.get_by_catalog_key(catalog[0]["catalog_key"]))
        self.assertIn("search=qwen-7b", calls[0])

    def test_huggingface_search_ignores_mmproj_files(self):
        db = DBManager()

        def opener(request, timeout=None):
            return FakeJsonResponse(
                [
                    {
                        "modelId": "unsloth/Kimi-K2.6-GGUF",
                        "tags": ["gguf"],
                        "siblings": [
                            {"rfilename": "mmproj-F16.gguf", "size": 908},
                            {"rfilename": "Kimi-K2.6-Q4_K_M.gguf", "size": 4096},
                        ],
                    }
                ]
            )

        service = RuntimeModelCatalogService(db_manager=db, opener=opener)

        catalog = service.search_huggingface_catalog("kimi")

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["filename"], "Kimi-K2.6-Q4_K_M.gguf")

    def test_catalog_sync_marks_installed_and_download_status(self):
        db = DBManager()
        catalog_path = Path(self.temp_dir.name) / "catalog.json"
        catalog_path.write_text(
            """
            [
              {
                "catalog_key": "tiny-runtime",
                "display_name": "Tiny Runtime",
                "source_url": "https://example.test/tiny.gguf",
                "filename": "tiny.gguf",
                "quantization": "Q4_K_M"
              }
            ]
            """,
            encoding="utf-8",
        )
        runtime_provider = db.providers.get_by_builtin_key("horizone_runtime")
        model_id = db.models.create(
            name="tiny-runtime",
            display_name="Tiny Runtime",
            provider_config_id=runtime_provider["id"],
        )
        db.runtime_model_downloads.create(
            catalog_key="tiny-runtime",
            status="ready",
            source_url="https://example.test/tiny.gguf",
            filename="tiny.gguf",
            model_config_id=model_id,
            local_path="/tmp/tiny.gguf",
        )

        service = RuntimeModelCatalogService(
            db_manager=db,
            catalog_path=catalog_path,
        )
        catalog = service.list_catalog()

        self.assertEqual(catalog[0]["catalog_key"], "tiny-runtime")
        self.assertTrue(catalog[0]["is_installed"])
        self.assertEqual(catalog[0]["model_config_id"], model_id)
        self.assertEqual(catalog[0]["download"]["status"], "ready")

    def test_catalog_list_hides_cached_mmproj_entries(self):
        db = DBManager()
        catalog_path = Path(self.temp_dir.name) / "catalog.json"
        catalog_path.write_text("[]", encoding="utf-8")
        db.runtime_model_catalog.upsert(
            catalog_key="bad-mmproj",
            display_name="Bad mmproj",
            source_url="https://example.test/mmproj-F16.gguf",
            filename="mmproj-F16.gguf",
        )

        service = RuntimeModelCatalogService(
            db_manager=db,
            catalog_path=catalog_path,
        )
        catalog = service.list_catalog()

        self.assertEqual(catalog, [])

    def test_download_creates_model_and_ready_download(self):
        db = DBManager()
        catalog_path = Path(self.temp_dir.name) / "catalog.json"
        catalog_path.write_text(
            """
            [
              {
                "catalog_key": "tiny-runtime",
                "display_name": "Tiny Runtime",
                "source_url": "https://example.test/tiny.gguf",
                "filename": "tiny.gguf"
              }
            ]
            """,
            encoding="utf-8",
        )
        catalog_service = RuntimeModelCatalogService(db_manager=db, catalog_path=catalog_path)
        config = ConfigManager()
        runtime_config = config.runtime.__class__(
            **{
                **config.runtime.__dict__,
                "runtime_models_dir": str(Path(self.temp_dir.name) / "models"),
            }
        )
        fake_chat_gguf_payload = fake_chat_gguf()
        download_service = RuntimeModelDownloadService(
            db_manager=db,
            catalog_service=catalog_service,
            runtime_config=runtime_config,
            opener=lambda url: FakeDownloadResponse([fake_chat_gguf_payload]),
            thread_factory=lambda target, *args: SyncThread(target, *args),
        )

        result = download_service.start_download("tiny-runtime")
        download = db.runtime_model_downloads.get(result["download"]["id"])
        model = db.models.get(download["model_config_id"])

        self.assertEqual(download["status"], "ready")
        self.assertEqual(download["bytes_downloaded"], len(fake_chat_gguf_payload))
        self.assertTrue(Path(download["local_path"]).is_file())
        self.assertEqual(model["provider"], "llama_cpp")
        self.assertEqual(model["name"], "tiny-runtime")

    def test_download_rejects_mmproj_metadata_after_download(self):
        db = DBManager()
        catalog_path = Path(self.temp_dir.name) / "catalog.json"
        catalog_path.write_text(
            """
            [
              {
                "catalog_key": "bad-runtime",
                "display_name": "Bad Runtime",
                "source_url": "https://example.test/Kimi-K2.6-Q4_K_M.gguf",
                "filename": "Kimi-K2.6-Q4_K_M.gguf"
              }
            ]
            """,
            encoding="utf-8",
        )
        catalog_service = RuntimeModelCatalogService(db_manager=db, catalog_path=catalog_path)
        config = ConfigManager()
        runtime_config = config.runtime.__class__(
            **{
                **config.runtime.__dict__,
                "runtime_models_dir": str(Path(self.temp_dir.name) / "models"),
            }
        )
        download_service = RuntimeModelDownloadService(
            db_manager=db,
            catalog_service=catalog_service,
            runtime_config=runtime_config,
            opener=lambda url: FakeDownloadResponse([fake_mmproj_gguf()]),
            thread_factory=lambda target, *args: SyncThread(target, *args),
        )

        result = download_service.start_download("bad-runtime")
        download = db.runtime_model_downloads.get(result["download"]["id"])

        self.assertEqual(download["status"], "error")
        self.assertIn("mmproj projector", download["error_message"])
        self.assertEqual(db.models.get_by_provider_and_name("llama_cpp", "bad-runtime"), None)

    def test_download_accepts_chat_model_with_large_metadata_array(self):
        db = DBManager()
        catalog_path = Path(self.temp_dir.name) / "catalog.json"
        catalog_path.write_text(
            """
            [
              {
                "catalog_key": "large-metadata-runtime",
                "display_name": "Large Metadata Runtime",
                "source_url": "https://example.test/large.gguf",
                "filename": "large.gguf"
              }
            ]
            """,
            encoding="utf-8",
        )
        catalog_service = RuntimeModelCatalogService(db_manager=db, catalog_path=catalog_path)
        config = ConfigManager()
        runtime_config = config.runtime.__class__(
            **{
                **config.runtime.__dict__,
                "runtime_models_dir": str(Path(self.temp_dir.name) / "models"),
            }
        )
        fake_payload = build_fake_gguf_with_large_metadata_array(
            {
                "general.architecture": "llama",
                "general.type": "model",
            }
        )
        download_service = RuntimeModelDownloadService(
            db_manager=db,
            catalog_service=catalog_service,
            runtime_config=runtime_config,
            opener=lambda url: FakeDownloadResponse([fake_payload]),
            thread_factory=lambda target, *args: SyncThread(target, *args),
        )

        result = download_service.start_download("large-metadata-runtime")
        download = db.runtime_model_downloads.get(result["download"]["id"])
        model = db.models.get(download["model_config_id"])

        self.assertEqual(download["status"], "ready")
        self.assertEqual(model["name"], "large-metadata-runtime")

    def test_download_rejects_mmproj_runtime_file(self):
        db = DBManager()
        catalog_path = Path(self.temp_dir.name) / "catalog.json"
        catalog_path.write_text(
            """
            [
              {
                "catalog_key": "bad-runtime",
                "display_name": "Bad Runtime",
                "source_url": "https://example.test/mmproj-F16.gguf",
                "filename": "mmproj-F16.gguf"
              }
            ]
            """,
            encoding="utf-8",
        )
        catalog_service = RuntimeModelCatalogService(db_manager=db, catalog_path=catalog_path)
        download_service = RuntimeModelDownloadService(
            db_manager=db,
            catalog_service=catalog_service,
            runtime_config=ConfigManager().runtime,
        )

        with self.assertRaises(RuntimeRequestError):
            download_service.start_download("bad-runtime")

    def test_download_checksum_mismatch_marks_error(self):
        db = DBManager()
        catalog_path = Path(self.temp_dir.name) / "catalog.json"
        catalog_path.write_text(
            """
            [
              {
                "catalog_key": "tiny-runtime",
                "display_name": "Tiny Runtime",
                "source_url": "https://example.test/tiny.gguf",
                "filename": "tiny.gguf",
                "checksum_sha256": "0000"
              }
            ]
            """,
            encoding="utf-8",
        )
        catalog_service = RuntimeModelCatalogService(db_manager=db, catalog_path=catalog_path)
        config = ConfigManager()
        runtime_config = config.runtime.__class__(
            **{
                **config.runtime.__dict__,
                "runtime_models_dir": str(Path(self.temp_dir.name) / "models"),
            }
        )
        download_service = RuntimeModelDownloadService(
            db_manager=db,
            catalog_service=catalog_service,
            runtime_config=runtime_config,
            opener=lambda url: FakeDownloadResponse([b"bad"]),
            thread_factory=lambda target, *args: SyncThread(target, *args),
        )

        result = download_service.start_download("tiny-runtime")
        download = db.runtime_model_downloads.get(result["download"]["id"])

        self.assertEqual(download["status"], "error")
        self.assertIn("checksum", download["error_message"])
        self.assertEqual(db.models.get_by_provider_and_name("llama_cpp", "tiny-runtime"), None)

    def test_cancel_download_removes_partial_file_after_restart(self):
        db = DBManager()
        config = ConfigManager()
        models_dir = Path(self.temp_dir.name) / "models"
        runtime_config = config.runtime.__class__(
            **{
                **config.runtime.__dict__,
                "runtime_models_dir": str(models_dir),
            }
        )
        models_dir.mkdir(parents=True)
        partial_path = models_dir / "Kimi-K2.6-BF16-00001-of-00046.gguf.part"
        partial_path.write_bytes(b"partial")
        download_id = db.runtime_model_downloads.create(
            catalog_key="kimi-runtime",
            status="downloading",
            source_url="https://example.test/Kimi-K2.6-BF16-00001-of-00046.gguf",
            filename="Kimi-K2.6-BF16-00001-of-00046.gguf",
            bytes_downloaded=7,
            total_bytes=46332327264,
        )
        download_service = RuntimeModelDownloadService(
            db_manager=db,
            catalog_service=None,
            runtime_config=runtime_config,
        )

        download = download_service.cancel_download(download_id)

        self.assertEqual(download["status"], "cancelled")
        self.assertFalse(partial_path.exists())
        self.assertIn("cancelled", download["error_message"])
