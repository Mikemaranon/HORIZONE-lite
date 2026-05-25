from .document_ingestion_service import (
    DocumentIngestionError,
    DocumentIngestionService,
)


class ProjectDocumentRequestError(ValueError):
    pass


class ProjectDocumentService:
    def __init__(self, db_manager, ingestion_service=None):
        self.db = db_manager
        self.ingestion_service = ingestion_service or DocumentIngestionService()

    def list_documents(self, project_id):
        self._ensure_project_exists(project_id)
        folders = self.db.project_document_folders.for_project(project_id)
        documents = self.db.project_documents.for_project(project_id)
        folder_paths = self._build_folder_paths(folders)

        return {
            "folders": [
                self.serialize_folder(item, folder_paths.get(item["id"], item["name"]))
                for item in folders
            ],
            "documents": [
                self.serialize_document(item, folder_paths)
                for item in documents
            ],
        }

    def create_documents(self, project_id, files, folder_id=None):
        self._ensure_project_exists(project_id)
        target_folder = self._require_folder_for_project(project_id, folder_id)
        if not files:
            raise DocumentIngestionError("Missing files")

        created_documents = []
        folders = self.db.project_document_folders.for_project(project_id)
        folder_paths = self._build_folder_paths(folders)
        for uploaded_file in files:
            document_payload = self.ingestion_service.extract_payload(uploaded_file)
            document_id = self.db.project_documents.create(
                project_id=project_id,
                filename=document_payload["filename"],
                content_type=document_payload["content_type"],
                size_bytes=document_payload["size_bytes"],
                text_content=document_payload["text_content"],
                folder_id=target_folder["id"] if target_folder else None,
            )
            self.db.project_document_chunks.replace_for_document(
                document_id=document_id,
                project_id=project_id,
                chunks=document_payload.get("chunks") or [],
            )
            created_documents.append(
                self.serialize_document(self.db.project_documents.get(document_id), folder_paths)
            )

        return created_documents

    def create_folder(self, project_id, name, parent_folder_id=None):
        self._ensure_project_exists(project_id)

        normalized_name = (name or "").strip()
        if not normalized_name:
            raise ProjectDocumentRequestError("Missing folder name")

        parent_folder = self._require_folder_for_project(project_id, parent_folder_id)

        if self.db.project_document_folders.find_by_name(
            project_id,
            normalized_name,
            parent_folder["id"] if parent_folder else None,
        ):
            raise ProjectDocumentRequestError("A folder with the same name already exists here")

        folder_id = self.db.project_document_folders.create(
            project_id=project_id,
            name=normalized_name,
            parent_folder_id=parent_folder["id"] if parent_folder else None,
        )
        folders = self.db.project_document_folders.for_project(project_id)
        folder_paths = self._build_folder_paths(folders)
        return self.serialize_folder(
            self.db.project_document_folders.get(folder_id),
            folder_paths.get(folder_id, normalized_name),
        )

    def move_document(self, document_id, folder_id=None):
        document = self.db.project_documents.get(document_id)
        if not document:
            raise LookupError("Document not found")

        target_folder = self._require_folder_for_project(document["project_id"], folder_id)
        self.db.project_documents.move_to_folder(
            document_id,
            target_folder["id"] if target_folder else None,
        )

        folders = self.db.project_document_folders.for_project(document["project_id"])
        folder_paths = self._build_folder_paths(folders)
        return self.serialize_document(
            self.db.project_documents.get(document_id),
            folder_paths,
        )

    def delete_folder(self, folder_id):
        folder = self.db.project_document_folders.get(folder_id)
        if not folder:
            raise LookupError("Folder not found")

        self.db.project_document_folders.delete(folder_id)
        return {
            "deleted": True,
            "folder_id": folder_id,
            "project_id": folder["project_id"],
            "parent_folder_id": folder["parent_folder_id"],
        }

    def delete_document(self, document_id):
        document = self.db.project_documents.get(document_id)
        if not document:
            raise LookupError("Document not found")

        self.db.project_documents.delete(document_id)
        return {
            "deleted": True,
            "document_id": document_id,
        }

    def serialize_document(self, document, folder_paths=None):
        folder_paths = folder_paths or {}
        folder_path = folder_paths.get(document.get("folder_id"))
        path = (
            f"{folder_path}/{document['filename']}"
            if folder_path
            else document["filename"]
        )
        return {
            "id": document["id"],
            "project_id": document["project_id"],
            "folder_id": document.get("folder_id"),
            "filename": document["filename"],
            "path": path,
            "folder_path": folder_path,
            "content_type": document["content_type"],
            "size_bytes": document["size_bytes"],
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
            "preview": document["text_content"][:240],
        }

    def serialize_folder(self, folder, path):
        return {
            "id": folder["id"],
            "project_id": folder["project_id"],
            "parent_folder_id": folder["parent_folder_id"],
            "name": folder["name"],
            "path": path,
            "created_at": folder["created_at"],
            "updated_at": folder["updated_at"],
        }

    def _ensure_project_exists(self, project_id):
        if self.db.projects.get(project_id):
            return

        raise LookupError("Project not found")

    def _require_folder_for_project(self, project_id, folder_id):
        if folder_id is None:
            return None

        folder = self.db.project_document_folders.get(folder_id)
        if not folder or folder["project_id"] != project_id:
            raise LookupError("Folder not found")
        return folder

    def _build_folder_paths(self, folders):
        folders_by_id = {folder["id"]: folder for folder in folders}
        paths = {}

        for folder in folders:
            self._resolve_folder_path(folder["id"], folders_by_id, paths, set())

        return paths

    def _resolve_folder_path(self, folder_id, folders_by_id, paths, active_ids):
        if folder_id in paths:
            return paths[folder_id]

        folder = folders_by_id.get(folder_id)
        if not folder:
            return ""

        if folder_id in active_ids:
            raise ProjectDocumentRequestError("Folder structure contains a cycle")

        next_active_ids = set(active_ids)
        next_active_ids.add(folder_id)
        parent_id = folder.get("parent_folder_id")
        if parent_id:
            parent_path = self._resolve_folder_path(parent_id, folders_by_id, paths, next_active_ids)
            path = f"{parent_path}/{folder['name']}" if parent_path else folder["name"]
        else:
            path = folder["name"]

        paths[folder_id] = path
        return path
