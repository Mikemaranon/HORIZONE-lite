# db_methods/t_users.py
class UsersTable:
    def __init__(self, db):
        self.db = db

    def create(self, username, password_hash, role="user"):
        self.db.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, password_hash, role)
        )

    def get(self, username):
        _, row = self.db.execute(
            "SELECT username, password, role FROM users WHERE username = ?",
            (username,),
            fetchone=True
        )
        if not row:
            return None
        return {
            "username": row[0],
            "password": row[1],
            "role": row[2]
        }

    def all(self):
        _, rows = self.db.execute(
            "SELECT username, role FROM users",
            fetchall=True
        )
        return [{"username": r[0], "role": r[1]} for r in rows]

    def update_credentials(self, current_username, new_username, password_hash):
        self.db.execute(
            """
            UPDATE users
            SET username = ?, password = ?, updated_at = CURRENT_TIMESTAMP
            WHERE username = ?
            """,
            (new_username, password_hash, current_username)
        )

    def delete(self, username):
        self.db.execute(
            "DELETE FROM users WHERE username = ?",
            (username,)
        )
