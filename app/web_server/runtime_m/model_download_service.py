import hashlib
import threading
from pathlib import Path
from urllib.request import urlopen

from .exceptions import RuntimeConflictError, RuntimeRequestError, RuntimeResourceNotFoundError
from .model_file_validator import RuntimeModelFileValidationError, RuntimeModelFileValidator


class RuntimeModelDownloadService:
    CHUNK_SIZE = 1024 * 1024

    def __init__(
        self,
        *,
        db_manager,
        catalog_service,
        runtime_config,
        opener=None,
        thread_factory=None,
        model_file_validator=None,
    ):
        self.db = db_manager
        self.catalog_service = catalog_service
        self.runtime_config = runtime_config
        self.opener = opener or urlopen
        self.thread_factory = thread_factory or self._create_thread
        self.model_file_validator = model_file_validator or RuntimeModelFileValidator()
        self._cancel_events = {}
        self._cancel_events_lock = threading.Lock()

    def list_downloads(self):
        return self.db.runtime_model_downloads.all()

    def get_download(self, download_id):
        download = self.db.runtime_model_downloads.get(self._parse_required_id(download_id, "id"))
        if not download:
            raise RuntimeResourceNotFoundError("Runtime model download not found")
        return download

    def start_download(self, catalog_key):
        normalized_key = str(catalog_key or "").strip()
        if not normalized_key:
            raise RuntimeRequestError("Missing catalog_key")

        entry = self.catalog_service.get_catalog_entry(normalized_key)
        if not entry:
            raise RuntimeResourceNotFoundError("Runtime model catalog entry not found")

        installed_model = self.db.models.get_by_provider_and_name("llama_cpp", entry["catalog_key"])
        if installed_model:
            latest_download = self.db.runtime_model_downloads.latest_for_catalog_key(entry["catalog_key"])
            return {
                "download": latest_download,
                "model": installed_model,
                "already_installed": True,
            }

        self._validate_runtime_model_entry(entry)

        active_downloads = self.db.runtime_model_downloads.active()
        if active_downloads:
            raise RuntimeConflictError("Another runtime model download is already active.")

        safe_filename = self._sanitize_filename(entry["filename"])
        download_id = self.db.runtime_model_downloads.create(
            catalog_key=entry["catalog_key"],
            status="queued",
            source_url=entry["source_url"],
            filename=safe_filename,
            total_bytes=entry["size_bytes"],
        )
        download = self.db.runtime_model_downloads.get(download_id)
        self._create_cancel_event(download_id)
        worker = self.thread_factory(self._run_download, download_id, entry)
        worker.start()
        return {
            "download": download,
            "model": None,
            "already_installed": False,
        }

    def cancel_download(self, download_id):
        parsed_download_id = self._parse_required_id(download_id, "id")
        download = self.get_download(parsed_download_id)
        if download["status"] not in {"queued", "downloading", "verifying"}:
            raise RuntimeConflictError("Runtime model download is not active.")

        self._request_cancel(parsed_download_id)
        self._remove_download_file(download, partial=True)
        return self.db.runtime_model_downloads.finish(
            parsed_download_id,
            status="cancelled",
            error_message="Download cancelled.",
        )

    def _run_download(self, download_id, entry):
        models_dir = Path(self.runtime_config.runtime_models_dir).expanduser()
        safe_filename = self._sanitize_filename(entry["filename"])
        final_path = models_dir / safe_filename
        partial_path = models_dir / f"{safe_filename}.part"

        try:
            models_dir.mkdir(parents=True, exist_ok=True)
            self.db.runtime_model_downloads.update_progress(download_id, status="downloading")
            self._raise_if_cancelled(download_id)
            total_bytes = int(entry.get("size_bytes") or 0)
            bytes_downloaded = 0

            with self.opener(entry["source_url"]) as response:
                response_total = response.headers.get("Content-Length") if hasattr(response, "headers") else None
                if response_total:
                    total_bytes = int(response_total)

                with open(partial_path, "wb") as output_file:
                    while True:
                        self._raise_if_cancelled(download_id)
                        chunk = response.read(self.CHUNK_SIZE)
                        if not chunk:
                            break

                        output_file.write(chunk)
                        bytes_downloaded += len(chunk)
                        self.db.runtime_model_downloads.update_progress(
                            download_id,
                            status="downloading",
                            bytes_downloaded=bytes_downloaded,
                            total_bytes=total_bytes,
                        )
                        self._raise_if_cancelled(download_id)

            self._raise_if_cancelled(download_id)
            self.db.runtime_model_downloads.update_progress(
                download_id,
                status="verifying",
                bytes_downloaded=bytes_downloaded,
                total_bytes=total_bytes,
            )
            self._raise_if_cancelled(download_id)
            self._verify_checksum(partial_path, entry.get("checksum_sha256", ""))
            self.model_file_validator.validate_chat_model_file(partial_path)
            self._raise_if_cancelled(download_id)
            partial_path.replace(final_path)
            model = self._create_or_update_model(entry)
            return self.db.runtime_model_downloads.finish(
                download_id,
                status="ready",
                model_config_id=model["id"],
                local_path=str(final_path),
            )
        except RuntimeModelDownloadCancelled:
            if partial_path.exists():
                partial_path.unlink()
            return self.db.runtime_model_downloads.finish(
                download_id,
                status="cancelled",
                error_message="Download cancelled.",
            )
        except Exception as error:
            if partial_path.exists():
                partial_path.unlink()
            return self._finish_error_or_cancelled(download_id, error)
        finally:
            self._discard_cancel_event(download_id)

    def _create_or_update_model(self, entry):
        provider = self.db.providers.get_by_builtin_key("horizone_runtime")
        if not provider:
            self.db.providers.ensure_seed_providers()
            provider = self.db.providers.get_by_builtin_key("horizone_runtime")
        if not provider:
            raise RuntimeError("HORIZONE runtime provider is unavailable.")

        existing_model = self.db.models.get_by_provider_and_name("llama_cpp", entry["catalog_key"])
        if existing_model:
            self.db.models.update(
                model_id=existing_model["id"],
                name=entry["catalog_key"],
                display_name=entry["display_name"],
                provider_config_id=provider["id"],
                is_default=existing_model["is_default"],
                is_builtin=True,
            )
            return self.db.models.get(existing_model["id"])

        model_id = self.db.models.create(
            name=entry["catalog_key"],
            display_name=entry["display_name"],
            provider_config_id=provider["id"],
            is_builtin=True,
        )
        return self.db.models.get(model_id)

    def _verify_checksum(self, path, checksum_sha256):
        expected = str(checksum_sha256 or "").strip().lower()
        if not expected:
            return

        digest = hashlib.sha256()
        with open(path, "rb") as input_file:
            for chunk in iter(lambda: input_file.read(self.CHUNK_SIZE), b""):
                digest.update(chunk)

        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError("Downloaded model checksum did not match the catalog.")

    def _sanitize_filename(self, filename):
        try:
            return self.model_file_validator.validate_downloadable_filename(filename)
        except RuntimeModelFileValidationError as error:
            raise RuntimeRequestError(str(error)) from error

    def _validate_runtime_model_entry(self, entry):
        self._sanitize_filename(entry.get("filename"))

    def _parse_required_id(self, value, field_name):
        if value is None or value == "":
            raise RuntimeRequestError(f"Missing {field_name}")
        try:
            return int(value)
        except (TypeError, ValueError):
            raise RuntimeRequestError(f"Invalid {field_name}")

    def _create_thread(self, target, *args):
        return threading.Thread(target=target, args=args, daemon=True)

    def _create_cancel_event(self, download_id):
        cancel_event = threading.Event()
        with self._cancel_events_lock:
            self._cancel_events[download_id] = cancel_event
        return cancel_event

    def _request_cancel(self, download_id):
        with self._cancel_events_lock:
            cancel_event = self._cancel_events.get(download_id)
        if cancel_event:
            cancel_event.set()

    def _discard_cancel_event(self, download_id):
        with self._cancel_events_lock:
            self._cancel_events.pop(download_id, None)

    def _raise_if_cancelled(self, download_id):
        with self._cancel_events_lock:
            cancel_event = self._cancel_events.get(download_id)
        if cancel_event and cancel_event.is_set():
            raise RuntimeModelDownloadCancelled()

        download = self.db.runtime_model_downloads.get(download_id)
        if download and download["status"] == "cancelled":
            raise RuntimeModelDownloadCancelled()

    def _remove_download_file(self, download, *, partial=False):
        filename = self._sanitize_filename(download["filename"])
        models_dir = Path(self.runtime_config.runtime_models_dir).expanduser()
        suffix = ".part" if partial else ""
        target_path = models_dir / f"{filename}{suffix}"
        try:
            if target_path.exists():
                target_path.unlink()
        except FileNotFoundError:
            return

    def _finish_error_or_cancelled(self, download_id, error):
        download = self.db.runtime_model_downloads.get(download_id)
        if download and download["status"] == "cancelled":
            return self.db.runtime_model_downloads.finish(
                download_id,
                status="cancelled",
                error_message="Download cancelled.",
            )

        return self.db.runtime_model_downloads.finish(
            download_id,
            status="error",
            error_message=str(error),
        )


class RuntimeModelDownloadCancelled(Exception):
    pass
