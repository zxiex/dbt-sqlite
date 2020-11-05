
from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3
from typing import List, Optional, Tuple, Any, Iterable, Dict


from dbt.adapters.base import Credentials
from dbt.adapters.sql import SQLConnectionManager
from dbt.contracts.connection import Connection, ConnectionState
from dbt.exceptions import (
    DatabaseException,
    FailedToConnectException,
    InternalException,
    RuntimeException,
    warn_or_error,
)
from dbt.logger import GLOBAL_LOGGER as logger


@dataclass
class SQLiteCredentials(Credentials):
    """ Required connections for a SQLite connection"""

    schema_paths: str

    @property
    def type(self):
        return "sqlite"

    def _connection_keys(self):
        """ Keys to show when debugging """
        return ["database", "schema", "schema_paths" ]


class SQLiteConnectionManager(SQLConnectionManager):
    TYPE = "sqlite"

    @classmethod
    def open(cls, connection):
        if connection.state == "open":
            logger.debug("Connection is already open, skipping open.")
            return connection

        credentials = connection.credentials

        schema_paths = {}
        for path_entry in credentials.schema_paths.split(";"):
            schema, path = path_entry.split("=", 1)
            schema_paths[schema] = path

        try:
            if 'main' in schema_paths:
                handle: sqlite3.Connection = sqlite3.connect(schema_paths['main'])
            else:
                raise FailedToConnectException("at least one schema must be called 'main'")
            
            cursor = handle.cursor()

            for schema in set(schema_paths.keys()) - set(['main']):
                path = schema_paths[schema]
                cursor.execute(f"attach '{path}' as '{schema}'")

            # # uncomment these lines to print out SQL: this only happens if statement is successful
            # handle.set_trace_callback(print)
            # sqlite3.enable_callback_tracebacks(True)

            connection.state = "open"
            connection.handle = handle

            return connection
        except sqlite3.Error as e:
            logger.debug(
                "Got an error when attempting to open a sqlite3 connection: '%s'", e
            )
            connection.handle = None
            connection.state = "fail"

            raise FailedToConnectException(str(e))
        except Exception as e:
            print(f"dunno what happened here: {e}")
            raise str(e)

        print("finished open")

    @classmethod
    def get_status(cls, cursor: sqlite3.Cursor):
        return f"OK"#  {cursor.rowcount}"

    def cancel(self, connection):
        """ cancel ongoing queries """

        logger.debug("Cancelling queries")
        try:
            connection.handle.interrupt()
        except sqlite3.Error:
            pass
        logger.debug("Queries canceled")

    @contextmanager
    def exception_handler(self, sql: str):
        try:
            yield
        except sqlite3.DatabaseError as e:
            self.release()
            logger.debug("sqlite3 error: {}".format(str(e)))
            raise DatabaseException(str(e))
        except Exception as e:
            logger.debug("Error running SQL: {}".format(sql))
            logger.debug("Rolling back transaction.")
            self.release()
            raise RuntimeException(str(e))

    def add_query(
        self,
        sql: str,
        auto_begin: bool = True,
        bindings: Optional[Any] = None,
        abridge_sql_log: bool = False
    ) -> Tuple[Connection, Any]:
        """
        sqlite3's cursor.execute() doesn't like None as the
        bindings argument, so substitute an empty dict
        """
        if not bindings:
            bindings = {}

        return super().add_query(sql=sql, auto_begin=auto_begin, bindings=bindings, abridge_sql_log=abridge_sql_log)

