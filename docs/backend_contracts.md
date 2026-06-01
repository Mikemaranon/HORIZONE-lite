# Backend contracts

This document captures the current backend boundaries for POLAR lite. Keep it small and update it when a phase in `audit.md` changes responsibility between modules.

## Module boundaries

- `api_m/domains/*`: HTTP transport only. Authenticate the request, read JSON/query/form data, call services or table gateways, and map results/errors to Flask responses.
- `api_m/services/*`: Application use cases and business rules. Services should be testable without a Flask request context.
- `data_m/db_methods/*`: SQL and serialization only. These classes should not decide product behavior or import Flask.
- `model_m/*`: Provider registry, model catalog, provider selection, message normalization, and model/provider response normalization.
- `config_m/*`: Runtime and provider configuration from environment variables. Secrets should not be exposed through `to_dict`.
- `user_m/*`: Local authentication, password hashing, token creation/validation, session persistence, and bootstrap-login policy.

## Provider Runtime

- Registered runtime providers are exactly `mlx`, `ollama`, and `cloud`.
- OpenAI, Anthropic, Google, and Microsoft-compatible endpoints are configured through `cloud` provider records.
- Direct `OpenAIProvider`, `AnthropicProvider`, and `GoogleProvider` exports are legacy compatibility adapters, not registered runtime providers.
- Saving a cloud provider performs local endpoint inference only and must not make network calls.
- Network probing belongs to the explicit provider connection-test path, currently `POST /api/providers/test`.
- MLX keeps at most one loaded model by default and exposes `clear_cache` for manual release.

## Invariants

- A persisted conversation always has a provider and model.
- A persisted message always belongs to one conversation.
- A project may exist without conversations.
- Provider API keys and secret settings are write-only from the API perspective.
- Login and credential refresh set the `token` cookie as `HttpOnly`, `SameSite=Lax`; bearer tokens remain a compatibility fallback.
- The insecure `admin/admin` bootstrap is only allowed when explicitly opted in with `POLAR_ALLOW_INSECURE_DEFAULT_ADMIN=1`.
