import os
import struct


class GgufMetadataError(ValueError):
    pass


class GgufMetadataReader:
    TYPE_UINT8 = 0
    TYPE_INT8 = 1
    TYPE_UINT16 = 2
    TYPE_INT16 = 3
    TYPE_UINT32 = 4
    TYPE_INT32 = 5
    TYPE_FLOAT32 = 6
    TYPE_BOOL = 7
    TYPE_STRING = 8
    TYPE_ARRAY = 9
    TYPE_UINT64 = 10
    TYPE_INT64 = 11
    TYPE_FLOAT64 = 12

    SCALARS = {
        TYPE_UINT8: "<B",
        TYPE_INT8: "<b",
        TYPE_UINT16: "<H",
        TYPE_INT16: "<h",
        TYPE_UINT32: "<I",
        TYPE_INT32: "<i",
        TYPE_FLOAT32: "<f",
        TYPE_BOOL: "<?",
        TYPE_UINT64: "<Q",
        TYPE_INT64: "<q",
        TYPE_FLOAT64: "<d",
    }

    def __init__(self, *, max_string_length=1_000_000, max_array_length=100_000):
        self.max_string_length = max_string_length
        self.max_array_length = max_array_length
        self._file_size = 0

    def read_metadata(self, path, keys=None):
        requested_keys = set(keys or [])
        with open(path, "rb") as input_file:
            self._file_size = os.fstat(input_file.fileno()).st_size
            if input_file.read(4) != b"GGUF":
                raise GgufMetadataError("Downloaded runtime model is not a GGUF file.")

            self._read_struct(input_file, "<I")
            self._read_struct(input_file, "<Q")
            metadata_count = self._read_struct(input_file, "<Q")

            metadata = {}
            for _ in range(metadata_count):
                key = self._read_string(input_file)
                value_type = self._read_struct(input_file, "<I")
                if not requested_keys or key in requested_keys:
                    metadata[key] = self._read_value(input_file, value_type)
                    if requested_keys and requested_keys.issubset(metadata):
                        return metadata
                else:
                    self._skip_value(input_file, value_type)

            return metadata

    def _read_value(self, input_file, value_type):
        if value_type == self.TYPE_STRING:
            return self._read_string(input_file)
        if value_type == self.TYPE_ARRAY:
            return self._read_array(input_file)
        if value_type not in self.SCALARS:
            raise GgufMetadataError(f"Unsupported GGUF metadata value type: {value_type}")

        return self._read_struct(input_file, self.SCALARS[value_type])

    def _read_array(self, input_file):
        item_type = self._read_struct(input_file, "<I")
        item_count = self._read_struct(input_file, "<Q")
        if item_count > self.max_array_length:
            raise GgufMetadataError("GGUF metadata array is too large to inspect safely.")

        return [
            self._read_value(input_file, item_type)
            for _ in range(item_count)
        ]

    def _skip_value(self, input_file, value_type):
        if value_type == self.TYPE_STRING:
            self._skip_string(input_file)
            return
        if value_type == self.TYPE_ARRAY:
            self._skip_array(input_file)
            return
        if value_type not in self.SCALARS:
            raise GgufMetadataError(f"Unsupported GGUF metadata value type: {value_type}")

        self._skip_bytes(input_file, struct.calcsize(self.SCALARS[value_type]))

    def _skip_array(self, input_file):
        item_type = self._read_struct(input_file, "<I")
        item_count = self._read_struct(input_file, "<Q")
        if item_type in self.SCALARS:
            self._skip_bytes(input_file, struct.calcsize(self.SCALARS[item_type]) * item_count)
            return

        for _ in range(item_count):
            self._skip_value(input_file, item_type)

    def _skip_string(self, input_file):
        length = self._read_struct(input_file, "<Q")
        self._skip_bytes(input_file, length)

    def _skip_bytes(self, input_file, byte_count):
        next_position = input_file.tell() + byte_count
        if next_position > self._file_size:
            raise GgufMetadataError("GGUF metadata ended unexpectedly.")
        input_file.seek(byte_count, os.SEEK_CUR)

    def _read_string(self, input_file):
        length = self._read_struct(input_file, "<Q")
        if length > self.max_string_length:
            raise GgufMetadataError("GGUF metadata string is too large to inspect safely.")

        data = input_file.read(length)
        if len(data) != length:
            raise GgufMetadataError("GGUF metadata ended unexpectedly.")

        return data.decode("utf-8", errors="replace")

    def _read_struct(self, input_file, format_string):
        size = struct.calcsize(format_string)
        data = input_file.read(size)
        if len(data) != size:
            raise GgufMetadataError("GGUF metadata ended unexpectedly.")

        return struct.unpack(format_string, data)[0]


def read_gguf_metadata(path, keys=None):
    return GgufMetadataReader().read_metadata(path, keys=keys)
