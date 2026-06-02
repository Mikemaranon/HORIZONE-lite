# log_repository.py
import json
from .database import Database

class LogRepository:
    def __init__(self, db_path=None, database=None):
        self.db = database or Database(db_path=db_path)

    def log(self, level, source, message, payload=None):
        payload_str = json.dumps(payload) if payload else None
        query = """
            INSERT INTO data_logs (level, source, message, payload)
            VALUES (?, ?, ?, ?)
        """
        self.db.execute(query, (level, source, message, payload_str))

    # -------------------------
    # Get logs (multiple filters)
    # -------------------------
    def get_logs(self, *, source=None, level=None, limit=100):
        query = "SELECT timestamp, source, level, message, payload FROM data_logs"
        conditions = []
        params = []

        if source:
            conditions.append("source = ?")
            params.append(source)

        if level:
            conditions.append("level = ?")
            params.append(level)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        _, rows = self.db.execute(query, params, fetchall=True)

        # Parse JSON payloads
        logs = []
        for ts, src, lvl, msg, payload_str in rows:
            payload = json.loads(payload_str) if payload_str else None
            logs.append({
                "timestamp": ts,
                "source": src,
                "level": lvl,
                "message": msg,
                "payload": payload
            })

        return logs

    # -------------------------
    # Delete old logs
    # -------------------------
    def purge(self, days: int):
        self.db.execute(
            """
            DELETE FROM data_logs
            WHERE timestamp <= datetime('now', ?)
            """,
            (f"-{days} days",)
        )
