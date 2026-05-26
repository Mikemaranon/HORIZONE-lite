# database.py
from contextlib import contextmanager
import threading

from .db_connector import DBConnector
from .schema import DatabaseSchemaInitializer

class Database:
    def __init__(self):
        self.connector = DBConnector()
        self.schema_initializer = DatabaseSchemaInitializer()
        self._transaction_state = threading.local()
        self._init_db()

    def execute(
        self,
        query,
        params=(),
        *,
        fetchone=False,
        fetchall=False,
        lastrowid=False,
    ):
        conn = self._active_connection() or self.connector.connect()
        cursor = conn.cursor()
        in_transaction = self._active_connection() is not None

        try:
            cursor.execute(query, params)
            if not in_transaction:
                conn.commit()

            op = query.strip().split()[0].upper()

            if fetchone:
                data = cursor.fetchone()
            elif fetchall:
                data = cursor.fetchall()
            elif lastrowid:
                data = cursor.lastrowid
            else:
                data = None

            return op, data

        except Exception as e:
            if not in_transaction:
                conn.rollback()
            raise e
        finally:
            cursor.close()
            if not in_transaction:
                self.connector.close(conn)

    @contextmanager
    def transaction(self):
        if self._active_connection() is not None:
            self._transaction_state.depth += 1
            try:
                yield self
            finally:
                self._transaction_state.depth -= 1
            return

        conn = self.connector.connect()
        self._transaction_state.connection = conn
        self._transaction_state.depth = 1
        try:
            yield self
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._transaction_state.connection = None
            self._transaction_state.depth = 0
            self.connector.close(conn)

    def _init_db(self):
        self.schema_initializer.initialize(self)

    def in_transaction(self):
        return self._active_connection() is not None

    def _active_connection(self):
        return getattr(self._transaction_state, "connection", None)
