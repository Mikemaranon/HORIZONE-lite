import inspect
from importlib.util import find_spec
from pathlib import Path
import threading

from ..exceptions import ModelOperationError, ProviderUnavailableError
from .base_provider import ModelProvider


class MLXProvider(ModelProvider):
    provider_name = "mlx"
    KNOWN_MODEL_ALIASES = {
        "gemma-3-4b-it-4bit": "mlx-community/gemma-3-4b-it-4bit",
    }
    DEFAULT_MAX_LOADED_MODELS = 1

    def __init__(
        self,
        config,
        db_manager=None,
        http_client=None,
        settings_resolver=None,
        max_loaded_models=None,
    ):
        super().__init__(
            config,
            db_manager=db_manager,
            http_client=http_client,
            settings_resolver=settings_resolver,
        )
        self._loaded_models = {}
        self._model_lock = threading.Lock()
        self.max_loaded_models = (
            self.DEFAULT_MAX_LOADED_MODELS
            if max_loaded_models is None
            else max(1, int(max_loaded_models))
        )

    def is_available(self) -> bool:
        return find_spec("mlx_lm") is not None

    def get_availability_error(self):
        if self.is_available():
            return None

        return ProviderUnavailableError(
            "MLX runtime unavailable: install `mlx_lm` in the server environment to enable local inference.",
            provider=self.provider_name,
        )

    def list_models(self) -> list[dict]:
        discovered_models = {}

        for path in self._get_configured_model_paths():
            discovered_models[path.name] = self.normalize_model_entry(
                model_id=path.name,
                display_name=path.name,
                source=str(path),
                metadata={
                    "path": str(path),
                    "origin": "local",
                },
            )

        for repo_id, snapshot_path in self._get_cached_huggingface_models().items():
            discovered_models[repo_id] = self.normalize_model_entry(
                model_id=repo_id,
                display_name=repo_id.split("/")[-1],
                source=str(snapshot_path),
                metadata={
                    "path": str(snapshot_path),
                    "origin": "huggingface_cache",
                },
            )

        return sorted(discovered_models.values(), key=lambda item: item["id"])

    def chat(self, messages: list[dict], model: str, settings: dict | None = None) -> dict:
        if not self.is_available():
            raise ProviderUnavailableError(
                "mlx_lm is not installed. Install it before using the MLX provider.",
                provider=self.provider_name,
            )

        (
            stream_generate_fn,
            model_instance,
            tokenizer,
            generation_kwargs,
            resolved_model,
        ) = self._prepare_generation(messages, model, settings)

        try:
            content, finish_reason, usage = self._generate_content(
                stream_generate_fn,
                model_instance,
                tokenizer,
                generation_kwargs,
            )
        except Exception as error:
            raise ModelOperationError(
                f"MLX generation failed: {error}",
                provider=self.provider_name,
            ) from error

        return self.normalize_chat_response(
            model=model,
            content=str(content),
            usage=usage,
            finish_reason=finish_reason,
            raw_response={
                "resolved_model": str(resolved_model),
            },
        )

    def stream_chat(
        self,
        messages: list[dict],
        model: str,
        settings: dict | None = None,
        should_stop=None,
    ):
        if not self.is_available():
            raise ProviderUnavailableError(
                "mlx_lm is not installed. Install it before using the MLX provider.",
                provider=self.provider_name,
            )

        (
            stream_generate_fn,
            model_instance,
            tokenizer,
            generation_kwargs,
            resolved_model,
        ) = self._prepare_generation(messages, model, settings)

        segments = []
        finish_reason = "stop"
        usage = {}
        chunk_count = 0

        try:
            for response in stream_generate_fn(
                model_instance,
                tokenizer,
                **generation_kwargs,
            ):
                if self.is_stop_requested(should_stop):
                    break

                chunk_count += 1
                text = response.text or ""
                if text:
                    segments.append(text)
                    yield {
                        "type": "delta",
                        "delta": text,
                    }

                finish_reason = response.finish_reason or finish_reason
                usage = {
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.generation_tokens,
                    "prompt_tps": response.prompt_tps,
                    "generation_tps": response.generation_tps,
                    "peak_memory_gb": response.peak_memory,
                }
        except Exception as error:
            raise ModelOperationError(
                f"MLX generation failed: {error}",
                provider=self.provider_name,
            ) from error

        content = "".join(segments)
        if self.is_stop_requested(should_stop):
            finish_reason = "cancelled"
        usage["prompt_characters"] = len(generation_kwargs.get("prompt", ""))
        usage["completion_characters"] = len(content)

        yield {
            "type": "response",
            "response": self.normalize_chat_response(
                model=model,
                content=content,
                usage=usage,
                finish_reason=finish_reason,
                raw_response={
                    "resolved_model": str(resolved_model),
                    "streamed": True,
                    "chunk_count": chunk_count,
                    "cancelled": finish_reason == "cancelled",
                },
            ),
        }

    def _import_mlx_runtime(self):
        try:
            from mlx_lm import load, stream_generate
            from mlx_lm.sample_utils import make_sampler
        except ImportError as error:
            raise ProviderUnavailableError(
                "mlx_lm is not installed. Install it before using the MLX provider.",
                provider=self.provider_name,
            ) from error

        return load, stream_generate, make_sampler

    def _get_or_load_model(self, load_fn, resolved_model):
        cache_key = str(resolved_model)
        with self._model_lock:
            if cache_key not in self._loaded_models:
                try:
                    self._evict_loaded_models_if_needed(cache_key)
                    self._loaded_models[cache_key] = load_fn(cache_key)
                except Exception as error:
                    message = f"Could not load MLX model '{cache_key}': {error}"
                    hint = self._build_load_error_hint(cache_key, error)
                    if hint:
                        message = f"{message} {hint}"
                    raise ModelOperationError(
                        message,
                        provider=self.provider_name,
                    ) from error

            return self._loaded_models[cache_key]

    def clear_cache(self):
        with self._model_lock:
            self._loaded_models.clear()

    def _evict_loaded_models_if_needed(self, incoming_cache_key):
        if incoming_cache_key in self._loaded_models:
            return

        while len(self._loaded_models) >= self.max_loaded_models:
            oldest_cache_key = next(iter(self._loaded_models))
            self._loaded_models.pop(oldest_cache_key, None)

    def _prepare_generation(self, messages, model, settings):
        load_fn, stream_generate_fn, make_sampler_fn = self._import_mlx_runtime()
        resolved_model = self._resolve_model_target(model)
        model_instance, tokenizer = self._get_or_load_model(load_fn, resolved_model)

        prompt = self._build_prompt(tokenizer, self.normalize_messages(messages))
        generation_kwargs = self._build_generation_kwargs(
            stream_generate_fn,
            prompt,
            settings,
            make_sampler_fn=make_sampler_fn,
        )

        return (
            stream_generate_fn,
            model_instance,
            tokenizer,
            generation_kwargs,
            resolved_model,
        )

    def _build_prompt(self, tokenizer, messages):
        if hasattr(tokenizer, "apply_chat_template"):
            kwargs = {"add_generation_prompt": True}
            signature = inspect.signature(tokenizer.apply_chat_template)
            if "tokenize" in signature.parameters:
                kwargs["tokenize"] = False

            return tokenizer.apply_chat_template(messages, **kwargs)

        transcript = []
        for message in messages:
            transcript.append(f"{message['role'].upper()}: {message['content']}")
        transcript.append("ASSISTANT:")
        return "\n".join(transcript)

    def _build_generation_kwargs(self, stream_generate_fn, prompt, settings, *, make_sampler_fn):
        signature = inspect.signature(stream_generate_fn)
        common = self.get_common_generation_settings(settings)
        kwargs = {
            "prompt": prompt,
        }

        if "verbose" in signature.parameters:
            kwargs["verbose"] = False
        if common.get("max_tokens") is not None and self._accepts_kwarg(signature, "max_tokens"):
            kwargs["max_tokens"] = common["max_tokens"]

        sampler = self._build_sampler(common, make_sampler_fn)
        if sampler is not None:
            kwargs["sampler"] = sampler

        return kwargs

    def _build_sampler(self, common, make_sampler_fn):
        temperature = common.get("temperature")
        top_p = common.get("top_p")

        if temperature is None and top_p is None:
            return None

        return make_sampler_fn(
            temp=0.0 if temperature is None else temperature,
            top_p=1.0 if top_p is None else top_p,
        )

    def _generate_content(self, stream_generate_fn, model_instance, tokenizer, generation_kwargs):
        segments = []
        finish_reason = "stop"
        usage = {}

        for response in stream_generate_fn(
            model_instance,
            tokenizer,
            **generation_kwargs,
        ):
            segments.append(response.text)
            finish_reason = response.finish_reason or finish_reason
            usage = {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.generation_tokens,
                "prompt_tps": response.prompt_tps,
                "generation_tps": response.generation_tps,
                "peak_memory_gb": response.peak_memory,
            }

        content = "".join(segments)
        usage["prompt_characters"] = len(generation_kwargs.get("prompt", ""))
        usage["completion_characters"] = len(content)

        return content, finish_reason, usage

    def _accepts_kwarg(self, signature, parameter_name):
        if parameter_name in signature.parameters:
            return True

        return any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )

    def _resolve_model_target(self, model):
        direct_path = Path(model).expanduser()
        if direct_path.exists():
            return direct_path

        configured_models = {path.name: path for path in self._get_configured_model_paths()}
        cached_models = self._get_cached_huggingface_models()
        for candidate in self._candidate_model_ids(model):
            if candidate in configured_models:
                return configured_models[candidate]
            if candidate in cached_models:
                return cached_models[candidate]

        cached_basename_match = self._match_cached_model_basename(model, cached_models)
        if cached_basename_match:
            return cached_basename_match

        return model

    def _candidate_model_ids(self, model):
        candidates = [model]
        alias = self.KNOWN_MODEL_ALIASES.get(model)
        if alias and alias not in candidates:
            candidates.append(alias)
        return candidates

    def _match_cached_model_basename(self, model, cached_models):
        matches = [
            snapshot_path
            for repo_id, snapshot_path in cached_models.items()
            if repo_id.split("/")[-1] == model
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def _build_load_error_hint(self, model, error):
        error_message = str(error).lower()
        if "repository not found" not in error_message and "401 client error" not in error_message:
            return ""

        alias = self.KNOWN_MODEL_ALIASES.get(model)
        if alias:
            return (
                f"Try the canonical repo id `{alias}` or point `MLX_MODEL_PATHS` to a local model folder."
            )

        if "/" not in model and not Path(model).expanduser().exists():
            return (
                "Use a full Hugging Face repo id such as `mlx-community/<model>` "
                "or point `MLX_MODEL_PATHS` to a local model folder."
            )

        return ""

    def _get_configured_model_paths(self):
        model_paths = []
        for model_path in self.config.mlx_model_paths:
            path = Path(model_path).expanduser()
            if path.exists() and path.is_dir():
                model_paths.append(path)
        return model_paths

    def _get_cached_huggingface_models(self):
        cache_root = self._get_huggingface_cache_root()
        if not cache_root.exists():
            return {}

        models = {}
        for candidate in cache_root.iterdir():
            if not candidate.is_dir() or not candidate.name.startswith("models--"):
                continue

            repo_id = candidate.name.replace("models--", "", 1).replace("--", "/")
            snapshot_path = self._latest_snapshot(candidate)
            if snapshot_path:
                models[repo_id] = snapshot_path

        return models

    def _get_huggingface_cache_root(self):
        if self.config.huggingface_cache_dir:
            return Path(self.config.huggingface_cache_dir).expanduser()

        hf_home = Path.home() / ".cache" / "huggingface"
        return hf_home / "hub"

    def _latest_snapshot(self, cache_repo_dir):
        snapshots_dir = cache_repo_dir / "snapshots"
        if not snapshots_dir.exists():
            return None

        snapshots = [path for path in snapshots_dir.iterdir() if path.is_dir()]
        if not snapshots:
            return None

        return max(snapshots, key=lambda path: path.stat().st_mtime)
