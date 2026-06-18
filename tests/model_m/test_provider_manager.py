import os
import tempfile
from pathlib import Path

from config_m import ConfigManager
from data_m import DBManager
from model_m import (
    LEGACY_DIRECT_PROVIDER_NAMES,
    ModelOperationError,
    ProviderUnavailableError,
    REGISTERED_PROVIDER_NAMES,
    UnsupportedProviderError,
)
from model_m.provider_manager import ProviderManager
from model_m.providers.mlx_provider import MLXProvider
from tests.test_support import IsolatedDatabaseTestCase


class FakeHttpClient:
    def __init__(
        self,
        *,
        get_response=None,
        post_response=None,
        sse_events=None,
        json_lines=None,
        get_error=None,
        post_error=None,
        sse_error=None,
        json_lines_error=None,
    ):
        self.get_response = get_response or {}
        self.post_response = post_response or {}
        self.post_responses = list(post_response) if isinstance(post_response, list) else []
        self.sse_event_batches = (
            list(sse_events)
            if sse_events and all(isinstance(event, list) for event in sse_events)
            else []
        )
        self.sse_events = [] if self.sse_event_batches else (sse_events or [])
        self.json_lines = json_lines or []
        self.get_error = get_error
        self.post_error = post_error
        self.sse_error = sse_error
        self.json_lines_error = json_lines_error
        self.calls = []

    def get_json(self, url, *, headers=None, provider_name=None):
        self.calls.append(
            {
                "method": "GET",
                "url": url,
                "headers": headers or {},
                "provider_name": provider_name,
            }
        )
        if self.get_error:
            raise self.get_error
        return self.get_response

    def post_json(self, url, payload, *, headers=None, provider_name=None):
        self.calls.append(
            {
                "method": "POST",
                "url": url,
                "payload": payload,
                "headers": headers or {},
                "provider_name": provider_name,
            }
        )
        if self.post_error:
            raise self.post_error
        if self.post_responses:
            return self.post_responses.pop(0)
        return self.post_response

    def stream_sse_json(self, url, payload, *, headers=None, provider_name=None):
        self.calls.append(
            {
                "method": "POST_STREAM_SSE",
                "url": url,
                "payload": payload,
                "headers": headers or {},
                "provider_name": provider_name,
            }
        )
        if self.sse_error:
            raise self.sse_error
        events = self.sse_event_batches.pop(0) if self.sse_event_batches else self.sse_events
        for event in events:
            yield event

    def stream_json_lines(self, url, payload, *, headers=None, provider_name=None):
        self.calls.append(
            {
                "method": "POST_STREAM_JSON_LINES",
                "url": url,
                "payload": payload,
                "headers": headers or {},
                "provider_name": provider_name,
            }
        )
        if self.json_lines_error:
            raise self.json_lines_error
        for line in self.json_lines:
            yield line


class FakeRuntimeSupervisor:
    def __init__(self, output_tail=""):
        self.output_tail = output_tail

    def read_output_tail(self, *, max_bytes=4096):
        return self.output_tail


class FakeRuntimeManager:
    def __init__(self, snapshot, supervisor=None):
        self.snapshot = snapshot
        self.supervisor = supervisor
        self.start_calls = 0
        self.start_args = []
        self.stop_calls = 0

    def start_if_available(self, **kwargs):
        self.start_calls += 1
        self.start_args.append(kwargs)
        return self.snapshot

    def stop(self):
        self.stop_calls += 1

    def base_url(self):
        return self.snapshot.get("base_url", "http://127.0.0.1:8080")


def create_cloud_provider(
    db,
    *,
    name,
    endpoint,
    adapter,
    api_key="",
    base_url=None,
):
    return db.providers.create(
        name=name,
        provider_type="cloud",
        endpoint=endpoint,
        api_key=api_key,
        resolved_adapter=adapter,
        resolved_metadata={
            "base_url": base_url or endpoint.rstrip("/"),
            "detected_from": "test",
        },
    )


class ProviderManagerTests(IsolatedDatabaseTestCase):
    def tearDown(self):
        for key in [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
            "MLX_MODEL_PATHS",
            "OLLAMA_API_KEY",
            "HUGGINGFACE_HUB_CACHE",
        ]:
            os.environ.pop(key, None)
        super().tearDown()

    def test_registers_expected_providers(self):
        manager = ProviderManager(ConfigManager())

        self.assertEqual(
            manager.get_registered_providers(),
            list(REGISTERED_PROVIDER_NAMES),
        )
        self.assertIn("llama_cpp", manager.get_registered_providers())
        self.assertEqual(LEGACY_DIRECT_PROVIDER_NAMES, ("openai", "anthropic", "google"))

    def test_raises_for_unsupported_provider(self):
        manager = ProviderManager(ConfigManager())

        with self.assertRaises(UnsupportedProviderError):
            manager.get_provider("vertex")

    def test_cloud_provider_detects_known_endpoint_hosts(self):
        manager = ProviderManager(ConfigManager())

        openai_resolution = manager.resolve_provider_configuration(
            "cloud",
            "https://api.openai.com/v1",
            "sk-test",
        )
        google_resolution = manager.resolve_provider_configuration(
            "cloud",
            "https://generativelanguage.googleapis.com",
            "sk-test",
        )

        self.assertEqual(openai_resolution["resolved_adapter"], "openai_compatible")
        self.assertEqual(
            openai_resolution["resolved_metadata"]["base_url"],
            "https://api.openai.com/v1",
        )
        self.assertEqual(google_resolution["resolved_adapter"], "google")

    def test_cloud_provider_save_resolution_does_not_probe_unknown_endpoint(self):
        manager = ProviderManager(ConfigManager())
        provider = manager.get_provider("cloud")
        fake_http = FakeHttpClient(get_response={"data": [{"id": "remote-model"}]})
        provider.detector.http_client = fake_http

        resolution = manager.resolve_provider_configuration(
            "cloud",
            "https://custom.example/v1",
            "sk-test",
            allow_probe=False,
        )

        self.assertEqual(resolution["resolved_adapter"], "openai_compatible")
        self.assertEqual(resolution["resolved_metadata"]["detected_from"], "default")
        self.assertEqual(fake_http.calls, [])

    def test_cloud_provider_explicit_connection_test_can_probe_unknown_endpoint(self):
        manager = ProviderManager(ConfigManager())
        provider = manager.get_provider("cloud")
        fake_http = FakeHttpClient(get_response={"data": [{"id": "remote-model"}]})
        provider.detector.http_client = fake_http

        resolution = manager.resolve_provider_configuration(
            "cloud",
            "https://custom.example/v1",
            "sk-test",
            allow_probe=True,
        )

        self.assertEqual(resolution["resolved_adapter"], "openai_compatible")
        self.assertEqual(resolution["resolved_metadata"]["detected_from"], "probe")
        self.assertEqual(fake_http.calls[0]["method"], "GET")

    def test_generate_conversation_title_sanitizes_provider_response(self):
        manager = ProviderManager(ConfigManager())
        provider = manager.get_provider("ollama")

        def fake_chat(messages, model, settings=None):
            self.assertEqual(messages[0]["role"], "system")
            self.assertIn("User: I need help with linear algebra", messages[1]["content"])
            self.assertIn("Assistant: We can focus on vectors and matrices", messages[1]["content"])
            self.assertEqual(settings["max_tokens"], 24)
            return {
                "message": {
                    "content": '  Título: "Algebra lineal aplicada"\n',
                }
            }

        provider.chat = fake_chat

        title = manager.generate_conversation_title(
            "ollama",
            "qwen3",
            [
                {"role": "user", "content": "I need help with linear algebra"},
                {"role": "assistant", "content": "We can focus on vectors and matrices"},
            ],
        )

        self.assertEqual(title, "Algebra lineal aplicada")

    def test_openai_provider_requires_api_key(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="OpenAI Cloud",
            endpoint="https://api.openai.com/v1",
            adapter="openai_compatible",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)

        with self.assertRaises(ProviderUnavailableError):
            manager.get_provider("cloud").chat([], "gpt-4.1")

    def test_anthropic_provider_requires_api_key(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="Anthropic Cloud",
            endpoint="https://api.anthropic.com",
            adapter="anthropic",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)

        with self.assertRaises(ProviderUnavailableError):
            manager.get_provider("cloud").chat([], "claude-sonnet-4")

    def test_google_provider_requires_api_key(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="Google Cloud",
            endpoint="https://generativelanguage.googleapis.com",
            adapter="google",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)

        with self.assertRaises(ProviderUnavailableError):
            manager.get_provider("cloud").chat([], "gemini-2.5-flash")

    def test_mlx_provider_lists_existing_local_model_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_a = Path(temp_dir) / "model-a"
            model_b = Path(temp_dir) / "model-b"
            empty_hf_cache = Path(temp_dir) / "hf-cache"
            model_a.mkdir()
            model_b.mkdir()
            empty_hf_cache.mkdir()
            os.environ["MLX_MODEL_PATHS"] = f"{model_a},{model_b}"
            os.environ["HUGGINGFACE_HUB_CACHE"] = str(empty_hf_cache)

            manager = ProviderManager(ConfigManager())
            models = manager.list_models("mlx")["models"]

            self.assertEqual(len(models), 2)
            self.assertEqual(
                [model["id"] for model in models],
                ["model-a", "model-b"],
            )

    def test_mlx_provider_resolves_cached_model_by_basename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir) / "hf-cache"
            snapshot_dir = (
                cache_root
                / "models--mlx-community--gemma-3-4b-it-4bit"
                / "snapshots"
                / "snapshot-123"
            )
            snapshot_dir.mkdir(parents=True)
            os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache_root)

            captured = {}

            class FakeTokenizer:
                def apply_chat_template(self, messages, add_generation_prompt=True, tokenize=False):
                    return "PROMPT"

            def fake_load(model_name):
                captured["loaded_model"] = model_name
                return "MODEL", FakeTokenizer()

            class FakeResponse:
                def __init__(self, text, generation_tokens, finish_reason=None):
                    self.text = text
                    self.prompt_tokens = 12
                    self.prompt_tps = 45.0
                    self.generation_tokens = generation_tokens
                    self.generation_tps = 18.0
                    self.peak_memory = 2.5
                    self.finish_reason = finish_reason

            def fake_make_sampler(temp=0.0, top_p=1.0):
                return "SAMPLER"

            def fake_stream_generate(model, tokenizer, prompt, max_tokens=None, sampler=None, verbose=None):
                yield FakeResponse("Respuesta", 1, finish_reason="stop")

            provider = MLXProvider(ConfigManager().get_provider_config())
            provider.is_available = lambda: True
            provider._import_mlx_runtime = lambda: (fake_load, fake_stream_generate, fake_make_sampler)

            response = provider.chat(
                [{"role": "user", "content": "Hello"}],
                "gemma-3-4b-it-4bit",
            )

            self.assertEqual(captured["loaded_model"], str(snapshot_dir))
            self.assertEqual(response["message"]["content"], "Respuesta")

    def test_openai_provider_lists_models_via_http(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="OpenAI Cloud",
            endpoint="https://api.openai.com/v1",
            adapter="openai_compatible",
            api_key="test-key",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)
        fake_http = FakeHttpClient(
            get_response={
                "data": [
                    {"id": "gpt-4.1", "owned_by": "openai", "created": 123},
                ]
            }
        )
        provider = manager.get_provider("cloud")
        provider.adapters["openai_compatible"].http_client = fake_http

        models = provider.list_models()

        self.assertEqual(models[0]["id"], "gpt-4.1")
        self.assertEqual(fake_http.calls[0]["headers"]["Authorization"], "Bearer test-key")
        self.assertTrue(fake_http.calls[0]["url"].endswith("/models"))

    def test_openai_provider_chat_uses_chat_completion_shape(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="OpenAI Cloud",
            endpoint="https://api.openai.com/v1",
            adapter="openai_compatible",
            api_key="test-key",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)
        fake_http = FakeHttpClient(
            post_response={
                "id": "chatcmpl-123",
                "model": "gpt-4.1",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hello from OpenAI"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4},
            }
        )
        provider = manager.get_provider("cloud")
        provider.adapters["openai_compatible"].http_client = fake_http

        response = provider.chat(
            [{"role": "user", "content": "Hello"}],
            "gpt-4.1",
            {"temperature": 0.2, "top_p": 0.8, "max_tokens": 128},
        )

        call = fake_http.calls[0]
        self.assertTrue(call["url"].endswith("/chat/completions"))
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(call["payload"]["model"], "gpt-4.1")
        self.assertEqual(call["payload"]["messages"][0]["content"], "Hello")
        self.assertEqual(call["payload"]["temperature"], 0.2)
        self.assertEqual(call["payload"]["top_p"], 0.8)
        self.assertEqual(call["payload"]["max_completion_tokens"], 128)
        self.assertFalse(call["payload"]["stream"])
        self.assertEqual(response["message"]["content"], "Hello from OpenAI")
        self.assertEqual(response["message_id"], "chatcmpl-123")

    def test_openai_provider_stream_chat_yields_deltas_and_final_response(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="OpenAI Cloud",
            endpoint="https://api.openai.com/v1",
            adapter="openai_compatible",
            api_key="test-key",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)
        fake_http = FakeHttpClient(
            sse_events=[
                {
                    "id": "chatcmpl-1",
                    "model": "gpt-4.1",
                    "choices": [
                        {
                            "delta": {"content": "Hola"},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": "chatcmpl-1",
                    "model": "gpt-4.1",
                    "choices": [
                        {
                            "delta": {"content": " mundo"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"completion_tokens": 2},
                },
            ]
        )
        provider = manager.get_provider("cloud")
        provider.adapters["openai_compatible"].http_client = fake_http

        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Saluda"}],
                "gpt-4.1",
            )
        )

        self.assertEqual(events[0]["delta"], "Hola")
        self.assertEqual(events[1]["delta"], " mundo")
        self.assertEqual(events[2]["response"]["message"]["content"], "Hola mundo")
        self.assertEqual(events[2]["response"]["message_id"], "chatcmpl-1")
        self.assertEqual(events[2]["response"]["usage"]["completion_tokens"], 2)
        self.assertTrue(fake_http.calls[0]["payload"]["stream"])

    def test_openai_provider_stream_chat_can_stop_early(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="OpenAI Cloud",
            endpoint="https://api.openai.com/v1",
            adapter="openai_compatible",
            api_key="test-key",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)
        fake_http = FakeHttpClient(
            sse_events=[
                {
                    "id": "chatcmpl-1",
                    "model": "gpt-4.1",
                    "choices": [
                        {
                            "delta": {"content": "Hola"},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": "chatcmpl-1",
                    "model": "gpt-4.1",
                    "choices": [
                        {
                            "delta": {"content": " mundo"},
                            "finish_reason": None,
                        }
                    ],
                },
            ]
        )
        provider = manager.get_provider("cloud")
        provider.adapters["openai_compatible"].http_client = fake_http

        stop_checks = iter([False, True])
        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Saluda"}],
                "gpt-4.1",
                should_stop=lambda: next(stop_checks, True),
            )
        )

        self.assertEqual(events[0]["delta"], "Hola")
        self.assertEqual(events[1]["response"]["message"]["content"], "Hola")
        self.assertEqual(events[1]["response"]["finish_reason"], "cancelled")
        self.assertTrue(events[1]["response"]["raw"]["cancelled"])

    def test_ollama_provider_chat_maps_common_settings(self):
        manager = ProviderManager(ConfigManager())
        fake_http = FakeHttpClient(
            post_response={
                "model": "gemma3",
                "message": {"role": "assistant", "content": "Hola"},
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 4,
            }
        )
        provider = manager.get_provider("ollama")
        provider.http_client = fake_http

        response = provider.chat(
            [{"role": "user", "content": "Hola"}],
            "gemma3",
            {"temperature": 0.2, "top_p": 0.8, "max_tokens": 128},
        )

        payload = fake_http.calls[0]["payload"]
        self.assertEqual(payload["options"]["temperature"], 0.2)
        self.assertEqual(payload["options"]["top_p"], 0.8)
        self.assertEqual(payload["options"]["num_predict"], 128)
        self.assertEqual(response["message"]["content"], "Hola")
        self.assertEqual(response["usage"]["prompt_tokens"], 10)

    def test_ollama_provider_stream_chat_yields_deltas_and_final_response(self):
        manager = ProviderManager(ConfigManager())
        fake_http = FakeHttpClient(
            json_lines=[
                {
                    "model": "gemma3",
                    "message": {"role": "assistant", "content": "Ho"},
                    "done": False,
                },
                {
                    "model": "gemma3",
                    "message": {"role": "assistant", "content": "la"},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 10,
                    "eval_count": 2,
                },
            ]
        )
        provider = manager.get_provider("ollama")
        provider.http_client = fake_http

        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Hola"}],
                "gemma3",
                {"temperature": 0.2},
            )
        )

        self.assertEqual(events[0]["delta"], "Ho")
        self.assertEqual(events[1]["delta"], "la")
        self.assertEqual(events[2]["response"]["message"]["content"], "Hola")
        self.assertEqual(events[2]["response"]["finish_reason"], "stop")
        self.assertTrue(fake_http.calls[0]["payload"]["stream"])

    def test_ollama_provider_stream_chat_can_stop_early(self):
        manager = ProviderManager(ConfigManager())
        fake_http = FakeHttpClient(
            json_lines=[
                {
                    "model": "gemma3",
                    "message": {"role": "assistant", "content": "Ho"},
                    "done": False,
                },
                {
                    "model": "gemma3",
                    "message": {"role": "assistant", "content": "la"},
                    "done": False,
                },
            ]
        )
        provider = manager.get_provider("ollama")
        provider.http_client = fake_http

        stop_checks = iter([False, True])
        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Hola"}],
                "gemma3",
                should_stop=lambda: next(stop_checks, True),
            )
        )

        self.assertEqual(events[0]["delta"], "Ho")
        self.assertEqual(events[1]["response"]["message"]["content"], "Ho")
        self.assertEqual(events[1]["response"]["finish_reason"], "cancelled")
        self.assertTrue(events[1]["response"]["raw"]["cancelled"])

    def test_ollama_provider_raises_for_json_error_payload(self):
        manager = ProviderManager(ConfigManager())
        fake_http = FakeHttpClient(
            post_response={
                "error": "llama runner process has terminated: %!w(<nil>)",
            }
        )
        provider = manager.get_provider("ollama")
        provider.http_client = fake_http

        with self.assertRaises(ModelOperationError) as error:
            provider.chat(
                [{"role": "user", "content": "Hola"}],
                "qwen2.5-coder:7b",
            )

        self.assertIn("local runner stopped", str(error.exception))

    def test_llama_cpp_provider_lists_models_via_openai_compatible_endpoint(self):
        manager = ProviderManager(ConfigManager())
        fake_http = FakeHttpClient(
            get_response={
                "data": [
                    {
                        "id": "gemma-3-1b-it-q4",
                        "object": "model",
                        "owned_by": "horizone",
                    },
                ]
            }
        )
        provider = manager.get_provider("llama_cpp")
        provider.http_client = fake_http

        models = provider.list_models()

        self.assertEqual(models[0]["id"], "gemma-3-1b-it-q4")
        self.assertEqual(models[0]["source"], "horizone_runtime")
        self.assertTrue(fake_http.calls[0]["url"].endswith("/v1/models"))
        self.assertEqual(fake_http.calls[0]["headers"]["Accept-Encoding"], "identity")
        self.assertEqual(fake_http.calls[0]["provider_name"], "llama_cpp")

    def test_llama_cpp_provider_chat_uses_chat_completion_shape(self):
        runtime_manager = FakeRuntimeManager({"status": "ready"})
        manager = ProviderManager(ConfigManager(), runtime_manager=runtime_manager)
        fake_http = FakeHttpClient(
            post_response={
                "id": "chatcmpl-runtime",
                "model": "gemma-3-1b-it-q4",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hola desde llama.cpp"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
        )
        provider = manager.get_provider("llama_cpp")
        provider.http_client = fake_http

        response = provider.chat(
            [{"role": "user", "content": "Hola"}],
            "gemma-3-1b-it-q4",
            {
                "temperature": 0.2,
                "top_p": 0.8,
                "max_tokens": 128,
                "_model_config_id": 42,
            },
        )

        self.assertEqual(runtime_manager.start_calls, 1)
        self.assertEqual(
            runtime_manager.start_args[0],
            {"model_config_id": 42, "model_name": "gemma-3-1b-it-q4"},
        )
        payload = fake_http.calls[0]["payload"]
        self.assertTrue(fake_http.calls[0]["url"].endswith("/v1/chat/completions"))
        self.assertEqual(payload["model"], "gemma-3-1b-it-q4")
        self.assertEqual(payload["messages"][0]["content"], "Hola")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["top_p"], 0.8)
        self.assertEqual(payload["max_tokens"], 128)
        self.assertFalse(payload["stream"])
        self.assertEqual(fake_http.calls[0]["headers"]["Accept-Encoding"], "identity")
        self.assertEqual(response["message"]["content"], "Hola desde llama.cpp")
        self.assertEqual(response["message_id"], "chatcmpl-runtime")

    def test_llama_cpp_provider_raises_when_runtime_cannot_start(self):
        runtime_manager = FakeRuntimeManager(
            {
                "status": "error",
                "error_message": "HORIZONE runtime needs llama-server or llama-cpp-python.",
                "base_url": "http://127.0.0.1:8080",
                "active_model": None,
            }
        )
        manager = ProviderManager(ConfigManager(), runtime_manager=runtime_manager)
        fake_http = FakeHttpClient(post_response={"unexpected": True})
        provider = manager.get_provider("llama_cpp")
        provider.http_client = fake_http

        with self.assertRaises(ProviderUnavailableError) as error:
            provider.chat([{"role": "user", "content": "Hola"}], "tiny-runtime")

        self.assertIn("llama-server", str(error.exception))
        self.assertEqual(runtime_manager.start_calls, 1)
        self.assertEqual(fake_http.calls, [])

    def test_llama_cpp_provider_restarts_runtime_once_after_decode_error_response(self):
        runtime_manager = FakeRuntimeManager({"status": "ready", "base_url": "http://127.0.0.1:8080"})
        manager = ProviderManager(ConfigManager(), runtime_manager=runtime_manager)
        fake_http = FakeHttpClient(
            post_response=[
                {
                    "error": {
                        "message": "Error -3 while decompressing data: incorrect header check",
                    },
                },
                {
                    "id": "chatcmpl-runtime",
                    "model": "qwen35",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "Hola"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            ]
        )
        provider = manager.get_provider("llama_cpp")
        provider.http_client = fake_http

        response = provider.chat(
            [{"role": "user", "content": "Hola"}],
            "qwen35",
        )

        self.assertEqual(response["message"]["content"], "Hola")
        self.assertEqual(runtime_manager.stop_calls, 1)
        self.assertEqual(runtime_manager.start_calls, 2)
        self.assertEqual(len(fake_http.calls), 2)

    def test_llama_cpp_provider_stream_chat_yields_deltas_and_final_response(self):
        manager = ProviderManager(ConfigManager())
        fake_http = FakeHttpClient(
            sse_events=[
                {
                    "id": "chatcmpl-runtime",
                    "model": "gemma-3-1b-it-q4",
                    "choices": [
                        {
                            "delta": {"content": "Ho"},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": "chatcmpl-runtime",
                    "model": "gemma-3-1b-it-q4",
                    "choices": [
                        {
                            "delta": {"content": "la"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"completion_tokens": 2},
                },
            ]
        )
        provider = manager.get_provider("llama_cpp")
        provider.http_client = fake_http

        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Hola"}],
                "gemma-3-1b-it-q4",
            )
        )

        self.assertEqual(events[0]["delta"], "Ho")
        self.assertEqual(events[1]["delta"], "la")
        self.assertEqual(events[2]["response"]["message"]["content"], "Hola")
        self.assertEqual(events[2]["response"]["finish_reason"], "stop")
        self.assertEqual(events[2]["response"]["usage"]["completion_tokens"], 2)
        self.assertTrue(fake_http.calls[0]["payload"]["stream"])
        self.assertEqual(fake_http.calls[0]["payload"]["stream_options"]["include_usage"], True)
        self.assertEqual(fake_http.calls[0]["headers"]["Accept-Encoding"], "identity")

    def test_llama_cpp_provider_stream_chat_restarts_runtime_once_before_tokens(self):
        runtime_manager = FakeRuntimeManager({"status": "ready", "base_url": "http://127.0.0.1:8080"})
        manager = ProviderManager(ConfigManager(), runtime_manager=runtime_manager)
        fake_http = FakeHttpClient(
            sse_events=[
                [
                    {
                        "error": {
                            "message": "Error -3 while decompressing data: incorrect header check",
                        },
                    }
                ],
                [
                    {
                        "id": "chatcmpl-runtime",
                        "model": "qwen35",
                        "choices": [
                            {
                                "delta": {"content": "Ho"},
                                "finish_reason": None,
                            }
                        ],
                    },
                    {
                        "id": "chatcmpl-runtime",
                        "model": "qwen35",
                        "choices": [
                            {
                                "delta": {"content": "la"},
                                "finish_reason": "stop",
                            }
                        ],
                    },
                ],
            ]
        )
        provider = manager.get_provider("llama_cpp")
        provider.http_client = fake_http

        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Hola"}],
                "qwen35",
            )
        )

        self.assertEqual(events[0]["delta"], "Ho")
        self.assertEqual(events[1]["delta"], "la")
        self.assertEqual(events[2]["response"]["message"]["content"], "Hola")
        self.assertEqual(runtime_manager.stop_calls, 1)
        self.assertEqual(runtime_manager.start_calls, 2)
        self.assertEqual(len(fake_http.calls), 2)

    def test_llama_cpp_provider_cancel_stream_stops_runtime_manager(self):
        runtime_manager = FakeRuntimeManager({"status": "ready", "base_url": "http://127.0.0.1:8080"})
        manager = ProviderManager(ConfigManager(), runtime_manager=runtime_manager)
        provider = manager.get_provider("llama_cpp")

        self.assertTrue(provider.cancel_stream())

        self.assertEqual(runtime_manager.stop_calls, 1)

    def test_llama_cpp_provider_stream_chat_returns_cancelled_after_cancel_disconnect(self):
        runtime_manager = FakeRuntimeManager({"status": "ready", "base_url": "http://127.0.0.1:8080"})
        manager = ProviderManager(ConfigManager(), runtime_manager=runtime_manager)
        fake_http = FakeHttpClient(sse_error=OSError("socket closed"))
        provider = manager.get_provider("llama_cpp")
        provider.http_client = fake_http

        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Hola"}],
                "qwen35",
                should_stop=lambda: True,
            )
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["response"]["finish_reason"], "cancelled")
        self.assertTrue(events[0]["response"]["raw"]["cancelled"])

    def test_llama_cpp_provider_adds_runtime_diagnostics_to_decode_errors(self):
        runtime_manager = FakeRuntimeManager(
            {"status": "ready", "base_url": "http://127.0.0.1:8080"},
            supervisor=FakeRuntimeSupervisor(
                "llama_init_from_model: failed\n"
                "Error -3 while decompressing data: incorrect header check"
            ),
        )
        manager = ProviderManager(ConfigManager(), runtime_manager=runtime_manager)
        fake_http = FakeHttpClient(
            sse_error=ModelOperationError(
                "Provider returned a response body that could not be decoded.",
                provider="llama_cpp",
                details={
                    "decode_error": "Error -3 while decompressing data: incorrect header check"
                },
            )
        )
        provider = manager.get_provider("llama_cpp")
        provider.http_client = fake_http

        with self.assertRaises(ModelOperationError) as error:
            list(
                provider.stream_chat(
                    [{"role": "user", "content": "Hola"}],
                    "gemma-3-1b-it-q4",
                )
            )

        self.assertIn("undecodable response", str(error.exception))
        self.assertEqual(error.exception.details["model"], "gemma-3-1b-it-q4")
        self.assertIn("incorrect header check", error.exception.details["decode_error"])
        self.assertIn("llama_init_from_model", error.exception.details["runtime_log_tail"])

    def test_llama_cpp_provider_returns_partial_response_when_stream_drops_after_tokens(self):
        runtime_manager = FakeRuntimeManager(
            {"status": "ready", "base_url": "http://127.0.0.1:8080"},
            supervisor=FakeRuntimeSupervisor("disconnected"),
        )
        manager = ProviderManager(ConfigManager(), runtime_manager=runtime_manager)

        class DroppingHttpClient(FakeHttpClient):
            def stream_sse_json(self, url, payload, *, headers=None, provider_name=None):
                self.calls.append(
                    {
                        "method": "POST_STREAM_SSE",
                        "url": url,
                        "payload": payload,
                        "headers": headers or {},
                        "provider_name": provider_name,
                    }
                )
                yield {
                    "id": "chatcmpl-runtime",
                    "model": "gemma-runtime",
                    "choices": [{"delta": {"content": "Ho"}, "finish_reason": None}],
                }
                raise ModelOperationError(
                    "Provider stream disconnected.",
                    provider="llama_cpp",
                )

        provider = manager.get_provider("llama_cpp")
        provider.http_client = DroppingHttpClient()

        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Hola"}],
                "gemma-runtime",
            )
        )

        self.assertEqual(events[0]["delta"], "Ho")
        self.assertEqual(events[1]["response"]["message"]["content"], "Ho")
        self.assertEqual(events[1]["response"]["finish_reason"], "stream_error")
        self.assertIn("stream_error", events[1]["response"]["raw"])
        self.assertEqual(runtime_manager.stop_calls, 0)

    def test_anthropic_provider_chat_uses_messages_api_shape(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="Anthropic Cloud",
            endpoint="https://api.anthropic.com",
            adapter="anthropic",
            api_key="anthropic-key",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)
        fake_http = FakeHttpClient(
            post_response={
                "id": "msg_123",
                "model": "claude-sonnet-4",
                "content": [{"type": "text", "text": "Hello from Claude"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 7},
            }
        )
        provider = manager.get_provider("cloud")
        provider.adapters["anthropic"].http_client = fake_http

        response = provider.chat(
            [
                {"role": "system", "content": "Be brief"},
                {"role": "user", "content": "Hello"},
            ],
            "claude-sonnet-4",
            {"temperature": 0.3, "max_tokens": 256},
        )

        payload = fake_http.calls[0]["payload"]
        self.assertEqual(payload["system"], "Be brief")
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertEqual(payload["max_tokens"], 256)
        self.assertEqual(response["message"]["content"], "Hello from Claude")

    def test_google_provider_lists_generate_content_models(self):
        db = DBManager()
        create_cloud_provider(
            db,
            name="Google Cloud",
            endpoint="https://generativelanguage.googleapis.com",
            adapter="google",
            api_key="google-key",
        )
        manager = ProviderManager(ConfigManager(), db_manager=db)
        fake_http = FakeHttpClient(
            get_response={
                "models": [
                    {
                        "name": "models/gemini-2.5-flash",
                        "baseModelId": "gemini-2.5-flash",
                        "displayName": "Gemini 2.5 Flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/embedding-001",
                        "baseModelId": "embedding-001",
                        "displayName": "Embedding",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            }
        )
        provider = manager.get_provider("cloud")
        provider.adapters["google"].http_client = fake_http

        models = provider.list_models()

        self.assertEqual([model["id"] for model in models], ["gemini-2.5-flash"])
        self.assertEqual(fake_http.calls[0]["headers"]["x-goog-api-key"], "google-key")

    def test_mlx_provider_chat_passes_max_tokens_and_sampler_to_stream_generate(self):
        captured = {}

        class FakeTokenizer:
            def apply_chat_template(self, messages, add_generation_prompt=True, tokenize=False):
                captured["messages"] = messages
                return "PROMPT"

        def fake_load(model_name):
            captured["loaded_model"] = model_name
            return "MODEL", FakeTokenizer()

        class FakeResponse:
            def __init__(self, text, generation_tokens, finish_reason=None):
                self.text = text
                self.prompt_tokens = 12
                self.prompt_tps = 45.0
                self.generation_tokens = generation_tokens
                self.generation_tps = 18.0
                self.peak_memory = 2.5
                self.finish_reason = finish_reason

        def fake_make_sampler(temp=0.0, top_p=1.0):
            captured["sampler_config"] = {
                "temp": temp,
                "top_p": top_p,
            }
            return "SAMPLER"

        def fake_stream_generate(model, tokenizer, prompt, max_tokens=None, sampler=None, verbose=None):
            captured["generate"] = {
                "model": model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "sampler": sampler,
                "verbose": verbose,
            }
            yield FakeResponse("Respuesta", 1)
            yield FakeResponse("", 1, finish_reason="length")

        provider = MLXProvider(ConfigManager().get_provider_config())
        provider.is_available = lambda: True
        provider._import_mlx_runtime = lambda: (fake_load, fake_stream_generate, fake_make_sampler)

        response = provider.chat(
            [{"role": "user", "content": "Hola"}],
            "demo-model",
            {"temperature": 0.4, "top_p": 0.9, "max_tokens": 64},
        )

        self.assertEqual(captured["loaded_model"], "demo-model")
        self.assertEqual(captured["generate"]["prompt"], "PROMPT")
        self.assertEqual(captured["generate"]["max_tokens"], 64)
        self.assertEqual(captured["generate"]["sampler"], "SAMPLER")
        self.assertEqual(captured["sampler_config"]["temp"], 0.4)
        self.assertEqual(captured["sampler_config"]["top_p"], 0.9)
        self.assertEqual(response["message"]["content"], "Respuesta")
        self.assertEqual(response["finish_reason"], "length")
        self.assertEqual(response["usage"]["completion_tokens"], 1)

    def test_mlx_provider_limits_loaded_model_cache(self):
        loaded_models = []

        class FakeTokenizer:
            def apply_chat_template(self, messages, add_generation_prompt=True, tokenize=False):
                return "PROMPT"

        def fake_load(model_name):
            loaded_models.append(model_name)
            return f"MODEL:{model_name}", FakeTokenizer()

        provider = MLXProvider(ConfigManager().get_provider_config(), max_loaded_models=1)

        provider._get_or_load_model(fake_load, "model-a")
        provider._get_or_load_model(fake_load, "model-b")

        self.assertEqual(loaded_models, ["model-a", "model-b"])
        self.assertEqual(list(provider._loaded_models.keys()), ["model-b"])
        provider.clear_cache()
        self.assertEqual(provider._loaded_models, {})

    def test_mlx_provider_stream_chat_yields_incremental_deltas(self):
        class FakeTokenizer:
            def apply_chat_template(self, messages, add_generation_prompt=True, tokenize=False):
                return "PROMPT"

        def fake_load(model_name):
            return "MODEL", FakeTokenizer()

        class FakeResponse:
            def __init__(self, text, generation_tokens, finish_reason=None):
                self.text = text
                self.prompt_tokens = 12
                self.prompt_tps = 45.0
                self.generation_tokens = generation_tokens
                self.generation_tps = 18.0
                self.peak_memory = 2.5
                self.finish_reason = finish_reason

        def fake_make_sampler(temp=0.0, top_p=1.0):
            return "SAMPLER"

        def fake_stream_generate(model, tokenizer, prompt, max_tokens=None, sampler=None, verbose=None):
            yield FakeResponse("Hel", 1)
            yield FakeResponse("lo", 2, finish_reason="stop")

        provider = MLXProvider(ConfigManager().get_provider_config())
        provider.is_available = lambda: True
        provider._import_mlx_runtime = lambda: (fake_load, fake_stream_generate, fake_make_sampler)

        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Hola"}],
                "demo-model",
                {"temperature": 0.4, "top_p": 0.9, "max_tokens": 64},
            )
        )

        self.assertEqual(events[0]["delta"], "Hel")
        self.assertEqual(events[1]["delta"], "lo")
        self.assertEqual(events[2]["response"]["message"]["content"], "Hello")
        self.assertEqual(events[2]["response"]["finish_reason"], "stop")
        self.assertEqual(events[2]["response"]["usage"]["completion_tokens"], 2)


class ProviderManagerCacheFallbackTests(IsolatedDatabaseTestCase):
    def test_cloud_providers_can_read_shared_settings_blob(self):
        db = DBManager()
        openai_id = create_cloud_provider(
            db,
            name="OpenAI Cloud",
            endpoint="https://api.openai.com/v1",
            adapter="openai_compatible",
        )
        anthropic_id = create_cloud_provider(
            db,
            name="Anthropic Cloud",
            endpoint="https://api.anthropic.com",
            adapter="anthropic",
        )
        google_id = create_cloud_provider(
            db,
            name="Google Cloud",
            endpoint="https://generativelanguage.googleapis.com",
            adapter="google",
        )
        db.settings.set(
            "openai_api_key",
            '{"openai":"sk-openai","anthropic":"sk-anthropic","google":"sk-google"}',
        )

        manager = ProviderManager(ConfigManager(), db_manager=db)
        provider = manager.get_provider("cloud")

        self.assertEqual(
            provider.adapters["openai_compatible"]._build_headers(db.providers.get(openai_id))["Authorization"],
            "Bearer sk-openai",
        )
        self.assertEqual(
            provider.adapters["anthropic"]._build_headers(db.providers.get(anthropic_id))["x-api-key"],
            "sk-anthropic",
        )
        self.assertEqual(
            provider.adapters["google"]._build_headers(db.providers.get(google_id))["x-goog-api-key"],
            "sk-google",
        )

    def test_returns_cached_models_when_provider_listing_fails(self):
        from model_m.exceptions import ProviderUnavailableError

        db = DBManager()
        create_cloud_provider(
            db,
            name="OpenAI Cloud",
            endpoint="https://api.openai.com/v1",
            adapter="openai_compatible",
            api_key="test-key",
        )
        db.models_cache.upsert(
            provider="cloud",
            model_id="gpt-4.1",
            display_name="GPT-4.1",
            source="openai",
        )

        manager = ProviderManager(ConfigManager(), db_manager=db)
        provider = manager.get_provider("cloud")

        def failing_list_models():
            raise ProviderUnavailableError(
                "Cloud down",
                provider="cloud",
            )

        provider.list_models = failing_list_models

        catalog = manager.list_models("cloud")

        self.assertFalse(catalog["available"])
        self.assertEqual(catalog["models"][0]["id"], "gpt-4.1")
        self.assertTrue(catalog["models"][0]["metadata"]["cached"])
        self.assertEqual(catalog["error"]["code"], "provider_unavailable")

    def test_mlx_catalog_exposes_runtime_error_when_package_is_missing(self):
        from data_m import DBManager

        db = DBManager()
        manager = ProviderManager(ConfigManager(), db_manager=db)
        provider = manager.get_provider("mlx")
        provider.is_available = lambda: False
        provider.list_models = lambda: [
            {
                "id": "gemma-3",
                "provider": "mlx",
                "display_name": "gemma-3",
                "source": "/tmp/gemma-3",
                "metadata": {},
            }
        ]

        catalog = manager.list_models("mlx")

        self.assertFalse(catalog["available"])
        self.assertEqual(catalog["models"][0]["id"], "gemma-3")
        self.assertEqual(catalog["error"]["code"], "provider_unavailable")
        self.assertIn("mlx_lm", catalog["error"]["message"])

    def test_mlx_provider_surfaces_canonical_repo_hint_for_known_alias(self):
        provider = MLXProvider(ConfigManager().get_provider_config())

        hint = provider._build_load_error_hint(
            "gemma-3-4b-it-4bit",
            RuntimeError("401 Client Error. Repository Not Found"),
        )

        self.assertIn("mlx-community/gemma-3-4b-it-4bit", hint)
