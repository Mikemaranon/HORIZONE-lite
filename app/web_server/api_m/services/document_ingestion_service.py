from pathlib import Path

from werkzeug.utils import secure_filename


class DocumentIngestionError(ValueError):
    pass


class DocumentIngestionService:
    MAX_DOCUMENT_BYTES = 1024 * 1024
    MAX_DOCUMENT_TEXT_CHARS = 20_000
    MAX_CHUNK_CHARS = 1_200
    SUPPORTED_TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        ".log",
        ".json",
        ".csv",
        ".tsv",
        ".toml",
        ".ini",
        ".cfg",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".py",
        ".java",
        ".rb",
        ".go",
        ".php",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".sql",
        ".sh",
    }

    def extract_payload(self, uploaded_file):
        original_filename = secure_filename((uploaded_file.filename or "").strip())
        if not original_filename:
            raise DocumentIngestionError("Each document needs a valid filename.")

        content_type = (uploaded_file.mimetype or "text/plain").strip() or "text/plain"
        if not self._is_supported_document(original_filename, content_type):
            raise DocumentIngestionError(
                f'The document "{original_filename}" is not a supported text format yet.'
            )

        content_bytes = uploaded_file.read()
        if not content_bytes:
            raise DocumentIngestionError(f'The document "{original_filename}" is empty.')

        if len(content_bytes) > self.MAX_DOCUMENT_BYTES:
            raise DocumentIngestionError(
                f'The document "{original_filename}" exceeds the limit of 1 MB.'
            )

        text_content = self._decode_document_bytes(content_bytes, original_filename)
        normalized_text = self._normalize_document_text(text_content)
        if not normalized_text:
            raise DocumentIngestionError(
                f'The document "{original_filename}" has no readable text.'
            )

        return {
            "filename": original_filename,
            "content_type": content_type,
            "size_bytes": len(content_bytes),
            "text_content": normalized_text,
            "chunks": self.build_chunks(normalized_text),
        }

    def build_chunks(self, text_content):
        normalized_text = self._normalize_document_text(text_content)
        if not normalized_text:
            return []

        blocks = self._split_paragraph_blocks(normalized_text)
        chunks = []
        current_parts = []
        current_size = 0

        for block in blocks:
            if len(block) > self.MAX_CHUNK_CHARS:
                self._flush_chunk(chunks, current_parts)
                current_parts = []
                current_size = 0
                chunks.extend(self._split_long_block(block))
                continue

            projected_size = current_size + len(block) + (2 if current_parts else 0)
            if current_parts and projected_size > self.MAX_CHUNK_CHARS:
                self._flush_chunk(chunks, current_parts)
                current_parts = [block]
                current_size = len(block)
                continue

            current_parts.append(block)
            current_size = projected_size

        self._flush_chunk(chunks, current_parts)
        return [
            {
                "chunk_index": index,
                "text_content": chunk,
            }
            for index, chunk in enumerate(chunks)
            if chunk
        ]

    def _is_supported_document(self, filename, content_type):
        suffix = Path(filename).suffix.lower()
        if suffix in self.SUPPORTED_TEXT_EXTENSIONS:
            return True

        return content_type.startswith("text/")

    def _decode_document_bytes(self, content_bytes, filename):
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return content_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue

        raise DocumentIngestionError(
            f'The document "{filename}" could not be decoded as text.'
        )

    def _normalize_document_text(self, text_content):
        normalized = (
            str(text_content or "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )
        if len(normalized) <= self.MAX_DOCUMENT_TEXT_CHARS:
            return normalized

        truncated = normalized[: self.MAX_DOCUMENT_TEXT_CHARS].rstrip()
        return (
            f"{truncated}\n\n"
            "[Document truncated automatically because it exceeded the local context limit.]"
        )

    def _split_paragraph_blocks(self, text_content):
        blocks = []
        current_lines = []

        for line in text_content.split("\n"):
            stripped_line = line.strip()
            if not stripped_line:
                self._flush_block(blocks, current_lines)
                current_lines = []
                continue

            current_lines.append(stripped_line)

        self._flush_block(blocks, current_lines)
        return blocks

    def _flush_block(self, blocks, current_lines):
        block = "\n".join(current_lines).strip()
        if block:
            blocks.append(block)

    def _flush_chunk(self, chunks, current_parts):
        chunk = "\n\n".join(current_parts).strip()
        if chunk:
            chunks.append(chunk)

    def _split_long_block(self, block):
        chunks = []
        remaining = block.strip()

        while remaining:
            if len(remaining) <= self.MAX_CHUNK_CHARS:
                chunks.append(remaining)
                break

            split_at = remaining.rfind(" ", 0, self.MAX_CHUNK_CHARS)
            if split_at < self.MAX_CHUNK_CHARS // 2:
                split_at = self.MAX_CHUNK_CHARS

            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()

        return chunks
