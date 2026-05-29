"""database connection classes

"""
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
        self._pool.putconn(self._conn)

class DBPools:

    def __init__(self):
        self._pools = {}

    def init_app(self, app):
        pass
        #app.teardown_request(self.remove_session)

    def startpool(self):
        env = my_env()
        env_params = current_app.config.get('IRODS_ENVS', {}).get(env)
        db_connect = env_params.get('jobs_db')
        self._pools[env] = pool.ThreadedConnectionPool(5, 50, db_connect)

    def connection(self):
        env = my_env()
        if env not in self._pools:
            self.startpool()
        if env in self._pools:
            return DBConnection(self._pools.get(env))
        else:
            raise ICATDBUnavailableException(f'env={env}')


db = DBPools()
