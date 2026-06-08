from pathlib import Path

from .gguf_metadata import GgufMetadataError, read_gguf_metadata


class RuntimeModelFileValidationError(ValueError):
    pass


class RuntimeModelFileValidator:
    NON_CHAT_FILENAME_PARTS = (
        "mmproj",
        "projector",
    )
    NON_CHAT_GENERAL_TYPES = {
        "mmproj",
        "projector",
    }
    NON_CHAT_ARCHITECTURES = {
        "clip",
    }
    INSPECTION_METADATA_KEYS = (
        "general.architecture",
        "general.type",
    )

    def validate_downloadable_filename(self, filename):
        path = Path(str(filename or "").strip())
        if path.name != str(filename or "").strip() or not path.name:
            raise RuntimeModelFileValidationError("Invalid runtime model filename.")
        if path.name.endswith(".part"):
            raise RuntimeModelFileValidationError("Invalid runtime model filename.")
        if self._filename_looks_non_chat(path.name):
            raise RuntimeModelFileValidationError(
                "HORIZONE runtime needs a text/chat GGUF model file, not an mmproj projector file."
            )
        return path.name

    def validate_chat_model_file(self, path):
        model_path = Path(path)
        metadata = read_gguf_metadata(model_path, keys=self.INSPECTION_METADATA_KEYS)
        general_type = str(metadata.get("general.type") or "").strip().lower()
        architecture = str(metadata.get("general.architecture") or "").strip().lower()

        if general_type in self.NON_CHAT_GENERAL_TYPES or architecture in self.NON_CHAT_ARCHITECTURES:
            raise RuntimeModelFileValidationError(
                "HORIZONE runtime needs a text/chat GGUF model file, not an mmproj projector file."
            )

        return metadata

    def inspect_installed_chat_model_file(self, path):
        model_path = Path(path)
        if self._filename_looks_non_chat(model_path.name):
            raise RuntimeModelFileValidationError(
                f"Installed HORIZONE runtime file is not a chat model: {model_path.name}. "
                "Download a text/chat GGUF model instead of an mmproj projector file."
            )

        try:
            self.validate_chat_model_file(model_path)
        except GgufMetadataError:
            return
        except RuntimeModelFileValidationError as error:
            raise RuntimeModelFileValidationError(
                f"Installed HORIZONE runtime file is not a chat model: {model_path.name}. "
                "Download a text/chat GGUF model instead of an mmproj projector file."
            ) from error

    def _filename_looks_non_chat(self, filename):
        lowered = str(filename or "").lower()
        return any(part in lowered for part in self.NON_CHAT_FILENAME_PARTS)
