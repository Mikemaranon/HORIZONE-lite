import json
import zlib
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .exceptions import ModelOperationError, ProviderUnavailableError


class JsonHttpClient:
    DEFAULT_HEADERS = {
        "Accept-Encoding": "identity",
    }

    def __init__(self, timeout_seconds=120):
        self.timeout_seconds = timeout_seconds

    def get_json(self, url, *, headers=None, provider_name=None):
        request = Request(url, headers=self._merge_headers(headers), method="GET")
        return self._send(request, provider_name=provider_name)

    def post_json(self, url, payload, *, headers=None, provider_name=None):
        request_headers = self._merge_headers(headers, {"Content-Type": "application/json"})

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        return self._send(request, provider_name=provider_name)

    def stream_sse_json(self, url, payload, *, headers=None, provider_name=None):
        request = self._build_post_request(url, payload, headers=headers)
        yield from self._stream_sse_json(request, provider_name=provider_name)

    def stream_json_lines(self, url, payload, *, headers=None, provider_name=None):
        request = self._build_post_request(url, payload, headers=headers)
        yield from self._stream_json_lines(request, provider_name=provider_name)

    def _build_post_request(self, url, payload, *, headers=None):
        request_headers = self._merge_headers(headers, {"Content-Type": "application/json"})

        return Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )

    def _send(self, request, *, provider_name=None):
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except HTTPError as error:
            payload = self._read_error_payload(error)
            message = self._extract_error_message(payload) or str(error)
            raise ModelOperationError(
                message,
                provider=provider_name,
                status_code=error.code,
                details=payload if isinstance(payload, dict) else {"raw": payload},
            ) from error
        except URLError as error:
            raise ProviderUnavailableError(
                f"Could not reach provider endpoint: {error.reason}",
                provider=provider_name,
            ) from error
        except json.JSONDecodeError as error:
            raise ModelOperationError(
                "Provider returned an invalid JSON response.",
                provider=provider_name,
            ) from error
        except (UnicodeDecodeError, zlib.error) as error:
            self._raise_response_decode_error(error, provider_name=provider_name)

    def _stream_sse_json(self, request, *, provider_name=None):
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                buffer = []

                for raw_line in response:
                    line = raw_line.decode("utf-8")
                    stripped = line.strip()

                    if not stripped:
                        payload = self._parse_sse_payload(buffer, provider_name=provider_name)
                        buffer = []
                        if payload is not None:
                            yield payload
                        continue

                    buffer.append(line.rstrip("\r\n"))

                payload = self._parse_sse_payload(buffer, provider_name=provider_name)
                if payload is not None:
                    yield payload
        except HTTPError as error:
            self._raise_http_error(error, provider_name=provider_name)
        except URLError as error:
            raise ProviderUnavailableError(
                f"Could not reach provider endpoint: {error.reason}",
                provider=provider_name,
            ) from error
        except (UnicodeDecodeError, zlib.error) as error:
            self._raise_response_decode_error(error, provider_name=provider_name)

    def _stream_json_lines(self, request, *, provider_name=None):
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    stripped = raw_line.decode("utf-8").strip()
                    if not stripped:
                        continue

                    try:
                        yield json.loads(stripped)
                    except json.JSONDecodeError as error:
                        raise ModelOperationError(
                            "Provider returned an invalid streaming JSON response.",
                            provider=provider_name,
                            details={"raw": stripped},
                        ) from error
        except HTTPError as error:
            self._raise_http_error(error, provider_name=provider_name)
        except URLError as error:
            raise ProviderUnavailableError(
                f"Could not reach provider endpoint: {error.reason}",
                provider=provider_name,
            ) from error
        except (UnicodeDecodeError, zlib.error) as error:
            self._raise_response_decode_error(error, provider_name=provider_name)

    def _parse_sse_payload(self, lines, *, provider_name=None):
        if not lines:
            return None

        data_lines = []
        for line in lines:
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())

        if not data_lines:
            return None

        raw_payload = "\n".join(data_lines)
        if raw_payload == "[DONE]":
            return None

        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError as error:
            raise ModelOperationError(
                "Provider returned an invalid streaming JSON response.",
                provider=provider_name,
                details={"raw": raw_payload},
            ) from error

    def _raise_http_error(self, error, *, provider_name=None):
        payload = self._read_error_payload(error)
        message = self._extract_error_message(payload) or str(error)
        raise ModelOperationError(
            message,
            provider=provider_name,
            status_code=error.code,
            details=payload if isinstance(payload, dict) else {"raw": payload},
        ) from error

    def _raise_response_decode_error(self, error, *, provider_name=None):
        raise ModelOperationError(
            "Provider returned a response body that could not be decoded.",
            provider=provider_name,
            details={"decode_error": str(error)},
        ) from error

    def _merge_headers(self, headers=None, defaults=None):
        merged = dict(self.DEFAULT_HEADERS)
        if defaults:
            merged.update(defaults)
        if headers:
            merged.update(headers)
        return merged

    def _read_error_payload(self, error):
        try:
            raw_payload = error.read().decode("utf-8")
        except Exception:
            return {"status": error.code}

        if not raw_payload:
            return {"status": error.code}

        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError:
            return {"status": error.code, "raw": raw_payload}

    def _extract_error_message(self, payload):
        if not isinstance(payload, dict):
            return None

        error_value = payload.get("error")
        if isinstance(error_value, dict):
            return error_value.get("message")
        if isinstance(error_value, str):
            return error_value

        return payload.get("message")
