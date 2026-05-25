import re

from .document_ingestion_service import DocumentIngestionService


class ProjectContextRetrievalService:
    MAX_SELECTED_CHUNKS = 4
    MAX_TOTAL_CHARS = 6_000
    MAX_CHUNK_CONTEXT_CHARS = 1_500
    STOP_WORDS = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "como",
        "con",
        "del",
        "dime",
        "do",
        "does",
        "el",
        "ella",
        "ellos",
        "for",
        "from",
        "haz",
        "how",
        "las",
        "los",
        "para",
        "por",
        "que",
        "the",
        "una",
        "what",
        "with",
    }

    def __init__(self, db_manager, ingestion_service=None):
        self.db = db_manager
        self.ingestion_service = ingestion_service or DocumentIngestionService()

    def build_context(self, project_id, query):
        query_terms = self._tokenize(query)
        if not query_terms:
            return ""

        self._ensure_project_chunks(project_id)
        chunks = self.db.project_document_chunks.for_project(project_id)
        if not chunks:
            return ""

        folder_paths = self._build_folder_paths(project_id)
        scored_chunks = self._score_chunks(chunks, query_terms, folder_paths)
        selected_chunks = self._select_chunks(scored_chunks, chunks)
        if not selected_chunks:
            return ""

        return self._format_context(selected_chunks, folder_paths)

    def _ensure_project_chunks(self, project_id):
        documents = self.db.project_documents.for_project(project_id)

        for document in documents:
            if self.db.project_document_chunks.count_for_document(document["id"]):
                continue

            chunks = self.ingestion_service.build_chunks(document.get("text_content") or "")
            self.db.project_document_chunks.replace_for_document(
                document_id=document["id"],
                project_id=project_id,
                chunks=chunks,
            )

    def _score_chunks(self, chunks, query_terms, folder_paths):
        scored_chunks = []

        for chunk in chunks:
            path = self._build_document_path(chunk, folder_paths)
            searchable_text = f"{path}\n{chunk.get('text_content') or ''}".lower()
            score = self._score_text(searchable_text, query_terms)
            if score <= 0:
                continue

            scored_chunks.append(
                {
                    **chunk,
                    "score": score,
                    "path": path,
                }
            )

        return sorted(
            scored_chunks,
            key=lambda item: (
                -item["score"],
                item["document_id"],
                item["chunk_index"],
            ),
        )

    def _select_chunks(self, scored_chunks, all_chunks):
        selected = []
        selected_keys = set()
        chunks_by_key = {
            (chunk["document_id"], chunk["chunk_index"]): chunk
            for chunk in all_chunks
        }

        for chunk in scored_chunks:
            if len(selected) >= self.MAX_SELECTED_CHUNKS:
                break

            self._append_selected_chunk(selected, selected_keys, chunk)

            neighbor = self._best_neighbor(chunk, chunks_by_key)
            if neighbor and len(selected) < self.MAX_SELECTED_CHUNKS:
                self._append_selected_chunk(selected, selected_keys, neighbor)

        return sorted(
            selected,
            key=lambda item: (item["document_id"], item["chunk_index"]),
        )

    def _append_selected_chunk(self, selected, selected_keys, chunk):
        key = (chunk["document_id"], chunk["chunk_index"])
        if key in selected_keys:
            return

        selected.append(chunk)
        selected_keys.add(key)

    def _best_neighbor(self, chunk, chunks_by_key):
        text = (chunk.get("text_content") or "").strip()
        if not text:
            return None

        previous_chunk = chunks_by_key.get(
            (chunk["document_id"], chunk["chunk_index"] - 1)
        )
        next_chunk = chunks_by_key.get(
            (chunk["document_id"], chunk["chunk_index"] + 1)
        )

        if text[0].islower() and previous_chunk:
            return previous_chunk

        if text[-1:] not in {".", "!", "?", ":", "`"} and next_chunk:
            return next_chunk

        return None

    def _format_context(self, chunks, folder_paths):
        blocks = []
        consumed = 0

        for index, chunk in enumerate(chunks, start=1):
            path = chunk.get("path") or self._build_document_path(chunk, folder_paths)
            header = f"[Document fragment {index}] {path} (chunk {chunk['chunk_index'] + 1})\n"
            body = (chunk.get("text_content") or "").strip()
            if len(body) > self.MAX_CHUNK_CONTEXT_CHARS:
                body = (
                    f"{body[:self.MAX_CHUNK_CONTEXT_CHARS].rstrip()}\n"
                    "[Fragment truncated for chat context.]"
                )

            block = f"{header}{body}"
            projected_size = consumed + len(block)
            if projected_size > self.MAX_TOTAL_CHARS:
                break

            blocks.append(block)
            consumed = projected_size

        if not blocks:
            return ""

        return (
            "Relevant project document fragments for the latest user message:\n\n"
            + "\n\n".join(blocks)
        )

    def _score_text(self, text, query_terms):
        score = 0

        for term in query_terms:
            occurrences = text.count(term)
            if occurrences:
                score += min(occurrences, 5)

        normalized_query = " ".join(query_terms)
        if normalized_query and normalized_query in text:
            score += 8

        return score

    def _tokenize(self, text):
        terms = []
        seen_terms = set()
        for raw_term in re.findall(r"[\w-]+", str(text or "").lower()):
            term = raw_term.strip("-_")
            if len(term) < 2 or term in self.STOP_WORDS or term in seen_terms:
                continue
            terms.append(term)
            seen_terms.add(term)

        return terms

    def _build_document_path(self, chunk, folder_paths):
        folder_path = folder_paths.get(chunk.get("folder_id"))
        filename = chunk.get("filename") or "document"
        if folder_path:
            return f"{folder_path}/{filename}"

        return filename

    def _build_folder_paths(self, project_id):
        folders = self.db.project_document_folders.for_project(project_id)
        folders_by_id = {folder["id"]: folder for folder in folders}
        paths = {}

        for folder in folders:
            self._resolve_folder_path(folder["id"], folders_by_id, paths)

        return paths

    def _resolve_folder_path(self, folder_id, folders_by_id, paths):
        if folder_id in paths:
            return paths[folder_id]

        folder = folders_by_id.get(folder_id)
        if not folder:
            return ""

        parent_id = folder.get("parent_folder_id")
        if parent_id:
            parent_path = self._resolve_folder_path(parent_id, folders_by_id, paths)
            path = f"{parent_path}/{folder['name']}" if parent_path else folder["name"]
        else:
            path = folder["name"]

        paths[folder_id] = path
        return path
