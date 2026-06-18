import re
import xml.etree.ElementTree as ElementTree
import zipfile
import zlib
from html import unescape
from io import BytesIO
from pathlib import Path

from werkzeug.utils import secure_filename


class DocumentIngestionError(ValueError):
    pass


class DocumentIngestionService:
    MAX_DOCUMENT_BYTES = 1024 * 1024
    MAX_DOCUMENT_TEXT_CHARS = 20_000
    MAX_CHUNK_CHARS = 1_200
    SUPPORTED_STRUCTURED_EXTENSIONS = {
        ".docx",
        ".pdf",
    }
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

        text_content = self._extract_document_text(content_bytes, original_filename)
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
        if (
            suffix in self.SUPPORTED_TEXT_EXTENSIONS
            or suffix in self.SUPPORTED_STRUCTURED_EXTENSIONS
        ):
            return True

        return content_type.startswith("text/")

    def _extract_document_text(self, content_bytes, filename):
        suffix = Path(filename).suffix.lower()
        if suffix == ".docx":
            return self._extract_docx_text(content_bytes, filename)
        if suffix == ".pdf":
            return self._extract_pdf_text(content_bytes, filename)

        return self._decode_document_bytes(content_bytes, filename)

    def _extract_docx_text(self, content_bytes, filename):
        try:
            archive = zipfile.ZipFile(BytesIO(content_bytes))
        except zipfile.BadZipFile as error:
            raise DocumentIngestionError(
                f'The document "{filename}" is not a readable DOCX file.'
            ) from error

        text_parts = []
        xml_names = [
            name
            for name in archive.namelist()
            if name == "word/document.xml"
            or name.startswith("word/header")
            or name.startswith("word/footer")
        ]

        for xml_name in xml_names:
            try:
                root = ElementTree.fromstring(archive.read(xml_name))
            except ElementTree.ParseError:
                continue

            for paragraph in root.iter():
                if not paragraph.tag.endswith("}p"):
                    continue

                paragraph_parts = []
                for node in paragraph.iter():
                    if node.tag.endswith("}t") and node.text:
                        paragraph_parts.append(node.text)
                    elif node.tag.endswith("}tab"):
                        paragraph_parts.append("\t")
                    elif node.tag.endswith("}br") or node.tag.endswith("}cr"):
                        paragraph_parts.append("\n")

                paragraph_text = "".join(paragraph_parts).strip()
                if paragraph_text:
                    text_parts.append(paragraph_text)

        if not text_parts:
            raise DocumentIngestionError(
                f'The document "{filename}" has no readable DOCX text.'
            )

        return "\n\n".join(text_parts)

    def _extract_pdf_text(self, content_bytes, filename):
        decoded_streams = self._extract_pdf_streams(content_bytes)
        text_parts = []

        for stream in decoded_streams:
            stream_text = stream.decode("latin-1", errors="ignore")
            text_parts.extend(self._extract_pdf_text_operators(stream_text))

        if not text_parts:
            fallback_text = content_bytes.decode("latin-1", errors="ignore")
            text_parts.extend(self._extract_pdf_text_operators(fallback_text))

        normalized_parts = [part.strip() for part in text_parts if part.strip()]
        if not normalized_parts:
            raise DocumentIngestionError(
                f'The document "{filename}" has no readable PDF text.'
            )

        return "\n".join(normalized_parts)

    def _extract_pdf_streams(self, content_bytes):
        streams = []
        for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", content_bytes, re.DOTALL):
            stream = match.group(1).strip(b"\r\n")
            dictionary_bytes = content_bytes[max(0, match.start() - 500):match.start()]
            if b"/FlateDecode" in dictionary_bytes:
                try:
                    stream = zlib.decompress(stream)
                except zlib.error:
                    continue
            streams.append(stream)
        return streams

    def _extract_pdf_text_operators(self, stream_text):
        text_parts = []
        for block in re.findall(r"BT(.*?)ET", stream_text, flags=re.DOTALL):
            for array_body in re.findall(r"\[(.*?)\]\s*TJ", block, flags=re.DOTALL):
                fragments = [
                    self._decode_pdf_literal(match.group(1))
                    for match in re.finditer(r"\((.*?)\)", array_body, flags=re.DOTALL)
                ]
                if fragments:
                    text_parts.append("".join(fragments))

            for literal in re.finditer(r"\((.*?)\)\s*Tj", block, flags=re.DOTALL):
                text_parts.append(self._decode_pdf_literal(literal.group(1)))

            for hex_text in re.finditer(r"<([0-9A-Fa-f\s]+)>\s*Tj", block):
                text_parts.append(self._decode_pdf_hex(hex_text.group(1)))

        return text_parts

    def _decode_pdf_literal(self, value):
        value = re.sub(r"\\([nrtbf()\\])", self._replace_pdf_escape, value)
        value = re.sub(
            r"\\([0-7]{1,3})",
            lambda match: chr(int(match.group(1), 8)),
            value,
        )
        return unescape(value)

    def _replace_pdf_escape(self, match):
        escapes = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "b": "\b",
            "f": "\f",
            "(": "(",
            ")": ")",
            "\\": "\\",
        }
        return escapes.get(match.group(1), match.group(1))

    def _decode_pdf_hex(self, value):
        hex_value = re.sub(r"\s+", "", value)
        if len(hex_value) % 2:
            hex_value = f"{hex_value}0"

        try:
            raw = bytes.fromhex(hex_value)
        except ValueError:
            return ""

        if raw.startswith(b"\xfe\xff"):
            return raw[2:].decode("utf-16-be", errors="ignore")
        return raw.decode("latin-1", errors="ignore")

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
