# web_server/user_m/user_manager.py

import jwt
import datetime
import threading
from werkzeug.security import check_password_hash, generate_password_hash
from data_m import DBManager

class UserManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(UserManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_manager=None, secret_key="your-secret-key"):
        if hasattr(self, 'initialized') and self.initialized:
            return # Already initialized
        # Initialize the singleton instance
        
        self.db = db_manager or DBManager()
        self.secret_key = secret_key
        self.initialized = True

        # ========================================================
        #  Ensure default admin user exists
        # ========================================================
        existing_admin = self.db.users.get("admin")
        if not existing_admin:
            
            hashed = generate_password_hash("admin")
            self.db.users.create(
                username="admin",
                password_hash=hashed,
                role="admin"
            )
            self._log_info("Default admin user created (admin/admin)")


    def authenticate(self, username: str, password: str):
        user = self.db.users.get(username)

        if user:
            if check_password_hash(user["password"], password):
                return True

        return False
    
    # ========================================================
    #     working with the request to get the token
    # ========================================================
    
    def get_token_from_cookie(self, request):
        token = request.cookies.get("token")
        return token

    def get_request_token(self, request):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            return token
        return None
    
    def check_user(self, request):
        token = self.get_token_from_cookie(request)
        if not token:
            token = self.get_request_token(request)  # fallback to Authorization header
        
        if token:
            user = self.get_user(token)
            if user:
                return user
        return None
    
    # ========================================================
    #     working with the user login and token generation
    #     DB interactions
    # ========================================================

    def create_user(self, username: str, password: str, role: str = "user"):
        # Check if the user already exists
        existing = self.db.users.get(username)
        if existing:
            return False

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Create user in database
        self.db.users.create(
            username=username,
            password_hash=hashed_password,
            role=role
        )

        return True

    def update_user_credentials(
        self,
        token: str,
        current_password: str,
        new_username: str | None = None,
        new_password: str | None = None,
    ):
        session = self.db.sessions.get(token)
        if session is None:
            raise ValueError("Unauthorized")

        current_username = session["username"]
        user = self.db.users.get(current_username)
        if user is None:
            raise ValueError("User not found")

        if not current_password or not check_password_hash(user["password"], current_password):
            raise ValueError("La contraseña actual no es correcta.")

        normalized_username = (new_username or current_username).strip()
        if not normalized_username:
            raise ValueError("El nombre de usuario no puede estar vacío.")

        normalized_password = (new_password or "").strip()
        if normalized_username != current_username and self.db.users.get(normalized_username):
            raise ValueError("Ese nombre de usuario ya está en uso.")

        if normalized_username == current_username and not normalized_password:
            return (
                {
                    "username": current_username,
                    "role": user["role"],
                },
                token,
            )

        password_hash = user["password"]
        if normalized_password:
            password_hash = generate_password_hash(normalized_password)

        self.db.users.update_credentials(
            current_username=current_username,
            new_username=normalized_username,
            password_hash=password_hash,
        )
        self.db.sessions.delete_for_username(current_username)

        refreshed_token = self.generate_token(normalized_username)
        self.db.sessions.create(username=normalized_username, token=refreshed_token)

        return (
            {
                "username": normalized_username,
                "role": user["role"],
            },
            refreshed_token,
        )
    
    def login(self, username: str, password: str):
        if self.authenticate(username, password):
            token = self.generate_token(username)
            # database: INSERT INTO sessions VALUES(username, token)
            self.db.sessions.create(username=username, token=token)
            return token
        return None

    def logout(self, token):
        # database: DELETE FROM sessions WHERE token = %s
        query = self.db.sessions.delete(token)
        if query:
            return {'status': 'success'}, 200 # TODO: CHANGE THIS TO TRUE/FALSE, JSON TO API
        return {'status': 'not found'}, 404

    def get_user(self, token):
        # database: SELECT FROM sessions WHERE token = %s
        session_query = self.db.sessions.get(token)
        if session_query != None:
            user = session_query["username"]
            # database: SELECT FROM users WHERE username = %s
            user_query = self.db.users.get(user)
            return user_query
        return None

    # ========================================================
    #     working with the tokens
    # ========================================================

    def generate_token(self, username: str):
        expiration_time = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        payload = {
            'username': username,
            'exp': expiration_time
        }
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')

        if isinstance(token, bytes):
            token = token.decode('utf-8')
        return token

    def _get_username_from_token(self, token):
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            username = payload.get('username')
            return username
        
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        
    def validate_token(self, token: str):

        # 1. Lookup the token in the database
        session = self.db.sessions.get(token)
        if not session:
            return False  # Token not found in DB

        # 2. Decode and validate the token (JWT)
        try:
            jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return True   # Valid token

        except jwt.ExpiredSignatureError:
            # If the token has expired, remove it from the database
            self.db.sessions.delete(token)
            return False

        except jwt.InvalidTokenError:
            # Corrupted token, remove it from the database
            self.db.sessions.delete(token)
            return False

    def _log_info(self, message):
        if hasattr(self.db, "logger"):
            self.db.logger.log(
                level="INFO",
                source="UserManager",
                message=message,
            )
