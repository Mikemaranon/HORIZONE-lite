# db_methods/t_users.py
class UsersTable:
    def __init__(self, db):
        self.db = db

    def create(self, username, password_hash, role="user", avatar_image=""):
        self.db.execute(
            "INSERT INTO users (username, password, role, avatar_image) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, avatar_image or "")
        )

    def get(self, username):
        _, row = self.db.execute(
            "SELECT username, password, role, avatar_image FROM users WHERE username = ?",
            (username,),
            fetchone=True
        )
        if not row:
            return None
        return {
            "username": row[0],
            "password": row[1],
            "role": row[2],
            "avatar_image": row[3] or "",
        }

    def all(self):
        _, rows = self.db.execute(
            "SELECT username, role, avatar_image FROM users",
            fetchall=True
        )
        return [{"username": r[0], "role": r[1], "avatar_image": r[2] or ""} for r in rows]

    def update_credentials(self, current_username, new_username, password_hash):
        self.db.execute(
            """
            UPDATE users
            SET username = ?, password = ?, updated_at = CURRENT_TIMESTAMP
            WHERE username = ?
            """,
            (new_username, password_hash, current_username)
        )

    def update_avatar(self, username, avatar_image):
        self.db.execute(
            """
            UPDATE users
            SET avatar_image = ?, updated_at = CURRENT_TIMESTAMP
            WHERE username = ?
            """,
            (avatar_image or "", username)
        )

    def delete(self, username):
        self.db.execute(
            "DELETE FROM users WHERE username = ?",
            (username,)
        )
