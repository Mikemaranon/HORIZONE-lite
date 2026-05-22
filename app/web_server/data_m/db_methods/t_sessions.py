# db_methods/t_sessions.py
class SessionsTable:
    def __init__(self, db):
        self.db = db

    def create(self, username, token, expires_at=None):
        self.db.execute(
            """
            INSERT INTO sessions (token, username, expires_at)
            VALUES (?, ?, ?)
            """,
            (token, username, expires_at)
        )

    def get(self, token):
        _, row = self.db.execute(
            """
            SELECT token, username, created_at, expires_at
            FROM sessions
            WHERE token = ?
            """,
            (token,),
            fetchone=True
        )
        if not row:
            return None

        return {
            "token": row[0],
            "username": row[1],
            "created_at": row[2],
            "expires_at": row[3]
        }

    def delete(self, token):
        self.db.execute(
            "DELETE FROM sessions WHERE token = ?",
            (token,)
        )

    def delete_for_username(self, username):
        self.db.execute(
            "DELETE FROM sessions WHERE username = ?",
            (username,)
        )
