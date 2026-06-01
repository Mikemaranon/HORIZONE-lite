from urllib.parse import urlparse


class CloudAdapterDetector:
    def __init__(self, http_client):
        self.http_client = http_client

    def resolve(self, endpoint, api_key="", *, allow_probe=True):
        normalized_endpoint = self._normalize_endpoint(endpoint)
        parsed = urlparse(normalized_endpoint)
        hostname = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")

        candidates = [
            self._resolve_by_host(hostname, normalized_endpoint, path),
            self._resolve_by_path(hostname, normalized_endpoint, path),
        ]
        for candidate in candidates:
            if candidate:
                return candidate

        if allow_probe:
            probed = self._probe_candidates(normalized_endpoint, api_key)
            if probed:
                return probed

        return self._build_resolution(
            "openai_compatible",
            self._normalize_openai_base_url(normalized_endpoint),
            "default",
        )

    def _resolve_by_host(self, hostname, endpoint, path):
        if hostname == "api.openai.com":
            return self._build_resolution(
                "openai_compatible",
                self._normalize_openai_base_url(endpoint),
                "hostname",
            )

        if hostname.endswith("api.anthropic.com"):
            return self._build_resolution(
                "anthropic",
                self._normalize_anthropic_base_url(endpoint),
                "hostname",
            )

        if hostname.endswith("generativelanguage.googleapis.com"):
            return self._build_resolution(
                "google",
                self._normalize_google_base_url(endpoint),
                "hostname",
            )

        if hostname.endswith("openai.azure.com"):
            return self._build_resolution(
                "openai_compatible",
                self._normalize_openai_base_url(endpoint),
                "hostname",
            )

        if hostname.endswith("services.ai.azure.com"):
            if "/openai/" in path or path.endswith("/openai/v1"):
                return self._build_resolution(
                    "openai_compatible",
                    self._normalize_openai_base_url(endpoint),
                    "hostname",
                )
            if path.endswith("/models") or not path:
                return self._build_resolution(
                    "microsoft_foundry",
                    self._normalize_foundry_base_url(endpoint),
                    "hostname",
                )

        return None

    def _resolve_by_path(self, hostname, endpoint, path):
        if path.endswith("/v1/messages"):
            return self._build_resolution(
                "anthropic",
                self._normalize_anthropic_base_url(endpoint),
                "path",
            )

        if "/v1beta/models" in path:
            return self._build_resolution(
                "google",
                self._normalize_google_base_url(endpoint),
                "path",
            )

        if path.endswith("/chat/completions") and hostname.endswith("services.ai.azure.com"):
            return self._build_resolution(
                "microsoft_foundry",
                self._normalize_foundry_base_url(endpoint),
                "path",
            )

        if path.endswith("/chat/completions") or path.endswith("/models") or "/openai/v1" in path:
            return self._build_resolution(
                "openai_compatible",
                self._normalize_openai_base_url(endpoint),
                "path",
            )

        return None

    def _probe_candidates(self, endpoint, api_key):
        for probe in (
            self._probe_openai_compatible,
            self._probe_anthropic,
            self._probe_google,
        ):
            try:
                resolved = probe(endpoint, api_key)
            except Exception:
                resolved = None
            if resolved:
                return resolved
        return None

    def _probe_openai_compatible(self, endpoint, api_key):
        base_url = self._normalize_openai_base_url(endpoint)
        response = self.http_client.get_json(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            provider_name="cloud",
        )
        if isinstance(response, dict) and isinstance(response.get("data"), list):
            return self._build_resolution("openai_compatible", base_url, "probe")
        return None

    def _probe_anthropic(self, endpoint, api_key):
        base_url = self._normalize_anthropic_base_url(endpoint)
        response = self.http_client.get_json(
            f"{base_url}/v1/models",
            headers=self._anthropic_headers(api_key),
            provider_name="cloud",
        )
        if isinstance(response, dict) and isinstance(response.get("data"), list):
            return self._build_resolution("anthropic", base_url, "probe")
        return None

    def _probe_google(self, endpoint, api_key):
        base_url = self._normalize_google_base_url(endpoint)
        response = self.http_client.get_json(
            f"{base_url}/v1beta/models",
            headers={"x-goog-api-key": api_key} if api_key else {},
            provider_name="cloud",
        )
        if isinstance(response, dict) and isinstance(response.get("models"), list):
            return self._build_resolution("google", base_url, "probe")
        return None

    def _build_resolution(self, adapter_name, base_url, detected_from):
        return {
            "resolved_adapter": adapter_name,
            "resolved_metadata": {
                "base_url": base_url,
                "detected_from": detected_from,
            },
        }

    def _normalize_endpoint(self, endpoint):
        normalized = str(endpoint or "").strip().rstrip("/")
        if not normalized:
            raise ValueError("Cloud providers need an endpoint.")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Cloud provider endpoint must be a valid http(s) URL.")
        return normalized

    def _normalize_openai_base_url(self, endpoint):
        normalized = self._normalize_endpoint(endpoint)
        if normalized.endswith("/chat/completions"):
            return normalized[: -len("/chat/completions")]
        if normalized.endswith("/models"):
            return normalized[: -len("/models")]
        if normalized == "https://api.openai.com":
            return f"{normalized}/v1"
        if normalized.endswith(".openai.azure.com") or normalized.endswith(".services.ai.azure.com/openai"):
            return f"{normalized}/v1"
        return normalized

    def _normalize_anthropic_base_url(self, endpoint):
        normalized = self._normalize_endpoint(endpoint)
        if normalized.endswith("/v1/messages"):
            return normalized[: -len("/v1/messages")]
        if normalized.endswith("/v1/models"):
            return normalized[: -len("/v1/models")]
        if normalized.endswith("/v1"):
            return normalized[: -len("/v1")]
        return normalized

    def _normalize_google_base_url(self, endpoint):
        normalized = self._normalize_endpoint(endpoint)
        for suffix in (
            "/v1beta/models",
            "/v1beta",
        ):
            if normalized.endswith(suffix):
                return normalized[: -len(suffix)]
        return normalized

    def _normalize_foundry_base_url(self, endpoint):
        normalized = self._normalize_endpoint(endpoint)
        if normalized.endswith("/chat/completions"):
            return normalized[: -len("/chat/completions")]
        if normalized.endswith("/models/chat/completions"):
            return normalized[: -len("/chat/completions")]
        if normalized.endswith("/models"):
            return normalized
        return f"{normalized}/models"

    def _anthropic_headers(self, api_key):
        headers = {"anthropic-version": "2023-06-01"}
        if api_key:
            headers["x-api-key"] = api_key
        return headers


