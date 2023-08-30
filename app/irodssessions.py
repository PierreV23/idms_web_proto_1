import ssl
import sys
import threading
import time
import logging

from requests import session
from apscheduler.schedulers.background import BackgroundScheduler
from flask import request, current_app
from flask_login import current_user
from irods.session import iRODSSession
from irods.version import __version__

def versiontuple(v):
    return tuple(map(int, (v.split("."))))

irodsclient_before_1_1_4 = versiontuple(__version__) < versiontuple('1.1.4')

def create_session(envdata, user):

    context = ssl._create_unverified_context(
        purpose=ssl.Purpose.SERVER_AUTH,
        cafile=None,
        capath=None,
        cadata=None
    )

    ssl_settings = {
        'irods_client_server_negotiation': 'request_server_negotiation',
        'irods_client_server_policy': 'CS_NEG_REQUIRE',
        'irods_ssl_ca_certificate_file': envdata.get('certfile', 'dummy'),
        'irods_encryption_algorithm': 'AES-256-CBC',
        'irods_encryption_key_size': 32,
        'irods_encryption_num_hash_rounds': 16,
        'irods_encryption_salt_size': 8,
        'ssl_context': context
    }

    # Creating an iRODS does not imply a connection is set up.
    # TODO: python-irodsclient should escape = tokens in password
    # at least in version 1.1.3 it does not do that
    # so, we do it here
    if irodsclient_before_1_1_4:
        password = user.passwd.replace('=', '\=')
    else:
        password = user.passwd
    return iRODSSession(
        host=envdata.get('host'),
        port=1247,
        user=user.username,
        password=password,
        zone=envdata.get('zone'),
        authentication_scheme='pam',
        refresh_time=240,
        **ssl_settings)

class PoolObject():
    def __init__(self, obj):
        self.timestamp = time.time()
        self.obj = obj

    def update(self):
        self.timestamp = time.time()

    def __str__(self):
        return f"{self.timestamp=} {self.obj=}"

class Session():
    def __init__(self, pool, irods_session):
        self._pool = pool
        self.s = irods_session

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def release(self):
        if self.s:
            self._pool.release(self.s)        

    def __getattr__(self, attr):
        _attr = getattr(self.s, attr)
        return _attr

    def __del__(self):
        self.release()


def objfromlist(l, a, v):
    for i in l:
        if getattr(i, a) == v:
            return i
    return None
            

class SessionPool():
    """Pool of irodsSessions for one user and irods environment
    """
    def __init__(self, envdata, targetsize=0, idle_timeout=60, active_timeout=120):
        self.targetsize = targetsize
        self.idle_timeout = idle_timeout
        self.active_timeout = active_timeout
        self._idle = []
        self._active = []
        self._lock = threading.Lock()
        self.envdata = envdata
    
    def cleanup(self):
        """Remove unused sessions
            Return number of active sessions

            The function uses an progressive timeout model to calculate which sessions to remove:
            max_idle_time = idle_timeout/idle_sessions
            so idle sessions will be removed sooner when there are more
        """
        logging.debug(f"queue lengths: idle {len(self._idle)}, active {len(self._active)}")
        # current_app.debug(f"idle queue {list(map(str, self._idle))}")
        # current_app.debug(f"active queue {list(map(str, self._active))}")
        def remove_sessions(queue, removelist):
            for sess in removelist:
                queue.remove(sess)
                sess.obj.cleanup()

        with self._lock:
            # Reduce idle queue size
            removelist = []
            if len(self._idle) > self.targetsize:
                self._idle.sort(key=lambda s: s.timestamp)
                index = len(self._idle)
                for sess in self._idle:
                    idle_remove_age = self.active_timeout // index
                    if time.time() - sess.timestamp > idle_remove_age:
                        removelist.append(sess)
                        index -= 1
                    else:
                        break
                    if index <= self.targetsize:
                        break
                if removelist:
                    logging.debug(f"removing {list(map(str, removelist))} from idle queue")
                    remove_sessions(self._idle, removelist)

            # Remove long-running active sessions
            removelist = []
            for sess in self._active:
                if time.time() - sess.timestamp > self.active_timeout:
                    removelist.append(sess)
            if removelist:
                logging.debug(f"removing {list(map(str, removelist))} from active queue")
                remove_sessions(self._active, removelist)

        return len(self._idle) + len(self._active)

    def get(self, user):
        with self._lock:
            if not self._idle:
                poolentry = PoolObject(create_session(self.envdata, user))
            else:
                poolentry = self._idle.pop()
            poolentry.update()
            self._active.append(poolentry)
        return Session(self, poolentry.obj)

    def release(self, sess):
        with self._lock:
            poolentry = objfromlist(self._active, 'obj', sess)
            if poolentry:
                self._active.remove(poolentry)
                poolentry.update()
                self._idle.append(poolentry)

    def __del__(self):
        with self._lock:
            for sess in self._idle + self._active:
                sess.obj.cleanup()
            self._idle = []
            self._active = []


class SessionPoolManager():
    """Manage a set of SessionPools,
    one for each logged in user
    """
    def __init__(self, envdata, refresh_time=120):
        self.envdata = envdata
        self._pools = {}
        self._lock = threading.Lock()

    def session(self, user):
        with self._lock:
            if user.username not in self._pools:
                self._pools[user.username] = SessionPool(self.envdata)
        return self._pools[user.username].get(user)

    def cleanup(self):
        """Cleanup unused session pools"""
        empty_pools = []
        with self._lock:
            userlist = self._pools.keys()
            for user in userlist:
                logging.debug(f"Cleaning sessions for user: {user}")
                counter = self._pools[user].cleanup()
                if counter == 0:
                    logging.debug(f"Session pool for {user=} is now empty, removing {str(self._pools[user])}")
                    empty_pools.append(user)
            for user in empty_pools:
                del self._pools[user]

    def remove(self, user):
        with self._lock:
            if user.username in self._pools:
                del self._pools[user.username]

class MultiSessionManager():
    """Manage the SessionManagers for 
    all irods environments
    """
    def __init__(self):
        self._managers = {}
        self._lock = threading.Lock()

    def init_app(self, app):
        self.scheduler = BackgroundScheduler(daemon=True)
        self.scheduler.add_job(func=self.cleanup, trigger="interval", seconds=60, jitter=15)
        self.scheduler.start()
        with self._lock:
            for envname, envdata in app.config.get('IRODS_ENVS', {}).items():
                self._managers[envname] = SessionPoolManager(envdata, refresh_time=app.config.get('conn_refresh_time', 120))
 
    def session(self, user=current_user):
        """ Return an irods session object
        for current_user
        """
        with self._lock:
            mgr = self._managers.get(user.environment)
            if mgr:
                return mgr.session(user)
        return None

    def cleanup(self):
        """Calls cleanup for all managers"""
        with self._lock:
            for env, mgr in self._managers.items():
                mgr.cleanup()

    def remove(self, user):
        """Removes the session for user"""
        with self._lock:
            self._managers[user.environment].remove(user)

irods_manager = MultiSessionManager()