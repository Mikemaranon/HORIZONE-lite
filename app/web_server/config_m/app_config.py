from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    secret_key: str
    host: str = "127.0.0.1"
    port: int = 5050
    debug: bool = False
    llama_cpp_binary: str = ""
    llama_cpp_server_kind: str = "native"
    llama_cpp_port: int = 8080
    llama_cpp_port_max: int = 9000
    runtime_models_dir: str = ""
    runtime_disabled: bool = False
    bootstrap_admin_password: str | None = None
    allow_insecure_default_admin: bool = False
    return_token_in_login_response: bool = False
    allow_public_registration: bool = False


@dataclass(frozen=True)
class ProviderConfig:
    default_provider: str = "mlx"
    ollama_base_url: str = "http://localhost:11434/api"
    ollama_api_key: str | None = None
    llama_cpp_base_url: str = "http://127.0.0.1:8080/v1"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_key: str | None = None
    google_base_url: str = "https://generativelanguage.googleapis.com"
    google_api_key: str | None = None
    mlx_model_paths: tuple[str, ...] = ()
    huggingface_cache_dir: str | None = None
    request_timeout_seconds: int = 120
