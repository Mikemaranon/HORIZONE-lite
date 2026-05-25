class WorkspaceCommandRunsTable:
    def __init__(self, db):
        self.db = db

    def create(self, workspace_id, command, cwd, conversation_id=None, status="pending"):
        _, run_id = self.db.execute(
            """
            INSERT INTO workspace_command_runs (workspace_id, conversation_id, command, cwd, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (workspace_id, conversation_id, command, cwd, status),
            lastrowid=True,
        )
        return run_id
