"""database connection classes

"""
import threading
from flask import current_app
from flask_login import current_user
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

def my_env():
    """Return environment the current_user is logged in to
       or None if not set
    Returns:
        str: environment name
    """
    if hasattr(current_user, 'environment'):
        return current_user.environment
    return None

class ICATDBUnavailableException(Exception):
    pass

class DBConnection:

    def __init__(self, dbpool):
        self._pool = dbpool
        self._conn = None

    def sql(self, statement):
        with self as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(statement)
            if cursor.rowcount == 0:
                return []
            else:
                return cursor.fetchall()

    def __enter__(self):
        self._conn = self._pool.getconn()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            if exc_type is not None:
                self._conn.rollback()
            else:
                self._conn.commit()
            self._pool.putconn(self._conn)

class DBPools:
    def __init__(self, db_key):
        self._db_key = db_key
        self._pools = {}
        self._lock = threading.Lock()

    def init_app(self, app):
        app.teardown_appcontext(self.close_all_pools)
    
    def close_all_pools(self, exception=None):
        """Close all active psycopg2 connection pools safely."""
        with self._lock:
            for env, db_pool in list(self._pools.items()):
                if db_pool and not db_pool.closed:
                    db_pool.closeall()
            self._pools.clear()

    def startpool(self, env):
        with self._lock:
            if env in self._pools:
                return
            env_params = current_app.config["IRODS_ENVS"].get(env)
            if not env_params or self._db_key not in env_params:
                raise ICATDBUnavailableException(f'Configuration missing for env={env}')
            
            db_connect = env_params[self._db_key]
            
            if isinstance(db_connect, dict):
                pool_inst = pool.ThreadedConnectionPool(5, 50, **db_connect)
            else:
                pool_inst = pool.ThreadedConnectionPool(5, 50, dsn=db_connect)
                
            self._pools[env] = pool_inst

    def connection(self):
        env = my_env()
        if not env:
            raise ICATDBUnavailableException('No environment set for current user.')

        if env not in self._pools:
            self.startpool(env)
            
        return DBConnection(self._pools[env])

jobs_db = DBPools("jobs_db")
search_db = DBPools("search_db")
