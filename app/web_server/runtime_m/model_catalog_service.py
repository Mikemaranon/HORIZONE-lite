import json
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .exceptions import RuntimeRequestError

class RuntimeModelCatalogService:
    HUGGING_FACE_MODELS_URL = "https://huggingface.co/api/models"
    HUGGING_FACE_MODEL_URL = "https://huggingface.co/api/models/{repo_id}"
    HUGGING_FACE_REPO_URL = "https://huggingface.co/{repo_id}"
    PREFERRED_GGUF_QUANTS = (
        "q4_k_m",
        "q5_k_m",
        "q8_0",
        "q4_0",
        "q6_k",
        "q3_k_m",
    )
    NON_CHAT_GGUF_FILENAME_PARTS = (
        "mmproj",
        "projector",
    )

    def __init__(self, *, db_manager, catalog_path=None, opener=None):
        self.db = db_manager
        self.catalog_path = catalog_path or (
            Path(__file__).resolve().parent / "catalog" / "llama_models.json"
        )
        self.opener = opener or urlopen

    def sync_catalog(self):
        entries = self._load_catalog_file()
        synced_entries = []
        for entry in entries:
            synced_entries.append(self.db.runtime_model_catalog.upsert(**entry))
        return synced_entries

    def list_catalog(self):
        self.sync_catalog()
        return self._attach_runtime_state(self.db.runtime_model_catalog.all())

    def search_huggingface_catalog(self, query, *, limit=20):
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []

        models = self._fetch_huggingface_models(normalized_query, limit=limit)
        entries = []
        for model in models:
            entry = self._create_huggingface_catalog_entry(model)
            if entry:
                entries.append(self.db.runtime_model_catalog.upsert(**entry))

        return self._attach_runtime_state(entries)

    def _attach_runtime_state(self, entries):
        downloads_by_key = {}
        for download in self.db.runtime_model_downloads.all():
            downloads_by_key.setdefault(download["catalog_key"], download)
        models_by_name = {
            model["name"]: model
            for model in self.db.models.all()
            if model.get("provider") == "llama_cpp"
        }

        catalog = []
        for entry in entries:
            if not self._is_downloadable_chat_filename(entry.get("filename")):
                continue

            download = downloads_by_key.get(entry["catalog_key"])
            model = models_by_name.get(entry["catalog_key"])
            catalog.append(
                {
                    **entry,
                    "is_installed": bool(model),
                    "model_config_id": model["id"] if model else (download or {}).get("model_config_id"),
                    "download": download,
                }
            )
        return catalog

    def get_catalog_entry(self, catalog_key):
        self.sync_catalog()
        return self.db.runtime_model_catalog.get_by_catalog_key(catalog_key)

    def _fetch_huggingface_models(self, query, *, limit):
        params = urlencode(
            {
                "search": query,
                "filter": "gguf",
                "library": "gguf",
                "limit": max(1, min(int(limit or 20), 50)),
                "full": "true",
            }
        )
        url = f"{self.HUGGING_FACE_MODELS_URL}?{params}"
        payload = self._request_json(url)
        if not isinstance(payload, list):
            raise RuntimeRequestError("Hugging Face returned an unexpected model catalog response.")
        return payload

    def _create_huggingface_catalog_entry(self, model):
        repo_id = str(model.get("modelId") or model.get("id") or "").strip()
        if not repo_id or "/" not in repo_id:
            return None

        siblings = model.get("siblings") if isinstance(model.get("siblings"), list) else []
        if not self._has_gguf_sibling(siblings):
            detail = self._fetch_huggingface_model_detail(repo_id)
            siblings = detail.get("siblings") if isinstance(detail.get("siblings"), list) else siblings

        gguf_file = self._select_gguf_file(siblings)
        if not gguf_file:
            return None

        filename = str(gguf_file.get("rfilename") or "").strip()
        if not filename:
            return None

        tags = model.get("tags") if isinstance(model.get("tags"), list) else []
        repo_name = repo_id.rsplit("/", 1)[-1]
        display_name = self._format_display_name(repo_name, filename)
        return {
            "catalog_key": self._build_huggingface_catalog_key(repo_id, filename),
            "display_name": display_name,
            "description": repo_id,
            "provider_type": "llama_cpp",
            "source_url": self._build_huggingface_resolve_url(repo_id, filename),
            "filename": Path(filename).name,
            "size_bytes": int(gguf_file.get("size") or 0),
            "checksum_sha256": "",
            "architecture": self._guess_architecture(repo_id, filename),
            "quantization": self._guess_quantization(filename),
            "context_length": 0,
            "recommended_ram_gb": 0,
            "license": self._extract_license(tags),
            "is_featured": False,
            "sort_order": 1000,
        }

    def _fetch_huggingface_model_detail(self, repo_id):
        url = self.HUGGING_FACE_MODEL_URL.format(repo_id=quote(repo_id, safe="/"))
        payload = self._request_json(url)
        if not isinstance(payload, dict):
            raise RuntimeRequestError("Hugging Face returned an unexpected model detail response.")
        return payload

    def _request_json(self, url):
        request = Request(url, headers={"User-Agent": "HORIZONE-lite/1.0"})
        try:
            with self.opener(request, timeout=20) as response:
                raw_payload = response.read().decode("utf-8")
        except TypeError:
            with self.opener(request) as response:
                raw_payload = response.read().decode("utf-8")
        except Exception as error:
            raise RuntimeRequestError(f"Hugging Face catalog search failed: {error}") from error

        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError as error:
            raise RuntimeRequestError("Hugging Face returned invalid JSON.") from error

    def _has_gguf_sibling(self, siblings):
        return any(self._is_gguf_file(item) for item in siblings)

    def _select_gguf_file(self, siblings):
        files = [item for item in siblings if self._is_downloadable_chat_gguf_file(item)]
        if not files:
            return None
        return sorted(files, key=self._rank_gguf_file)[0]

    def _is_gguf_file(self, item):
        filename = str(item.get("rfilename") or "").strip().lower()
        return filename.endswith(".gguf")

    def _is_downloadable_chat_gguf_file(self, item):
        if not self._is_gguf_file(item):
            return False

        filename = Path(str(item.get("rfilename") or "").strip()).name.lower()
        return self._is_downloadable_chat_filename(filename)

    def _is_downloadable_chat_filename(self, filename):
        filename = Path(str(filename or "").strip()).name.lower()
        if not filename.endswith(".gguf"):
            return False
        return not any(part in filename for part in self.NON_CHAT_GGUF_FILENAME_PARTS)

    def _rank_gguf_file(self, item):
        filename = str(item.get("rfilename") or "").strip().lower()
        for index, quant in enumerate(self.PREFERRED_GGUF_QUANTS):
            if quant in filename:
                return (index, len(filename), filename)
        return (len(self.PREFERRED_GGUF_QUANTS), len(filename), filename)

    def _build_huggingface_catalog_key(self, repo_id, filename):
        raw_value = f"hf-{repo_id}-{filename}".lower()
        return "".join(character if character.isalnum() else "-" for character in raw_value).strip("-")

    def _build_huggingface_resolve_url(self, repo_id, filename):
        safe_repo_id = quote(repo_id, safe="/")
        safe_filename = quote(filename, safe="/")
        return f"{self.HUGGING_FACE_REPO_URL.format(repo_id=safe_repo_id)}/resolve/main/{safe_filename}"

    def _format_display_name(self, repo_name, filename):
        clean_repo = repo_name.replace("-GGUF", "").replace("-gguf", "")
        quantization = self._guess_quantization(filename)
        return f"{clean_repo} {quantization}".strip()

    def _guess_architecture(self, repo_id, filename):
        value = f"{repo_id} {filename}".lower()
        for architecture in ("qwen", "gemma", "llama", "mistral", "phi", "deepseek"):
            if architecture in value:
                return architecture
        return ""

    def _guess_quantization(self, filename):
        value = str(filename or "").lower()
        for quantization in ("q8_0", "q6_k", "q5_k_m", "q4_k_m", "q4_0", "q3_k_m"):
            if quantization in value:
                return quantization.upper()
        return ""

    def _extract_license(self, tags):
        for tag in tags:
            normalized = str(tag or "")
            if normalized.startswith("license:"):
                return normalized.split(":", 1)[1]
        return ""

    def _load_catalog_file(self):
        with open(self.catalog_path, "r", encoding="utf-8") as catalog_file:
            entries = json.load(catalog_file)

        if not isinstance(entries, list):
            raise ValueError("Runtime model catalog must be a list.")

        return [self._normalize_entry(entry) for entry in entries]

    def _normalize_entry(self, entry):
        if not isinstance(entry, dict):
            raise ValueError("Runtime model catalog entries must be objects.")

        required_fields = ["catalog_key", "display_name", "source_url", "filename"]
        for field_name in required_fields:
            if not str(entry.get(field_name, "")).strip():
                raise ValueError(f"Runtime model catalog entry missing {field_name}.")

        return {
            "catalog_key": str(entry["catalog_key"]).strip(),
            "display_name": str(entry["display_name"]).strip(),
            "description": str(entry.get("description", "")).strip(),
            "provider_type": str(entry.get("provider_type", "llama_cpp")).strip() or "llama_cpp",
            "source_url": str(entry["source_url"]).strip(),
            "filename": str(entry["filename"]).strip(),
            "size_bytes": int(entry.get("size_bytes") or 0),
            "checksum_sha256": str(entry.get("checksum_sha256", "")).strip(),
            "architecture": str(entry.get("architecture", "")).strip(),
            "quantization": str(entry.get("quantization", "")).strip(),
            "context_length": int(entry.get("context_length") or 0),
            "recommended_ram_gb": int(entry.get("recommended_ram_gb") or 0),
            "license": str(entry.get("license", "")).strip(),
            "is_featured": bool(entry.get("is_featured", False)),
            "sort_order": int(entry.get("sort_order") or 0),
        }
