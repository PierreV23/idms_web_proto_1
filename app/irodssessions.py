import ssl
import threading
import time
from apscheduler.schedulers.background import BackgroundScheduler
from flask import request
from flask_login import current_user
from irods.session import iRODSSession

def create_session(user):

    context = ssl._create_unverified_context(
        purpose=ssl.Purpose.SERVER_AUTH,
        cafile=None,
        capath=None,
        cadata=None
    )

    ssl_settings = {
        'irods_ssl_ca_certificate_file': '/etc/irods/ssl/acc/irods.crt',
        'ssl_context': context
    }

    # Creating an iRODS does not imply a connection is set up.
    # TODO: python-irodsclient should escape = tokens in password
    # at least in version 1.1.3 it does not do that
    # so, we do it here
    sess = iRODSSession(
        host=user.irods_server,
        port=1247,
        user=user.username,
        password=user.passwd.replace('=', '\='),
        zone=user.irods_zone,
        authentication_scheme='pam')
#        **ssl_settings)
    sess.collections.get('/')
    return sess

class PoolObject():
    def __init__(self, obj):
        self.timestamp = time.time()
        self.obj = obj


class Session():

    def __init__(self, pool, irods_session):
        self._pool = pool
        self.s = irods_session

    def __getattr__(self, attr):
        return getattr(self.s, attr)

    def __del__(self):
        if self.s:
            self._pool.add(self.s)


class SessionPool():
    def __init__(self, targetsize=0, min_age=60):
        self.targetsize = targetsize
        self.min_age = min_age
        self._sessions = []
        self._lock = threading.Lock()
        self.scheduler = BackgroundScheduler(daemon=True)
        self.scheduler.add_job(func=self.cleanup, trigger="interval", seconds=60)
        self.scheduler.start()
        self.total = 0
    
    def cleanup(self):
        with self._lock:
            i = len(self._sessions) - self.targetsize 
            removelist = []
            for s in self._sessions:
                if i<=0:
                    break
                if time.time() - s.timestamp > self.min_age:
                    removelist.append(s)
                    i -= 1
            for s in removelist:
                self._sessions.remove(s)
                self.total -= 1
            if len(self._sessions) == 0:
                self.scheduler.pause()

    def get(self, user):
        if not self._sessions:
            self.add(create_session(user))
        with self._lock:
            sess = self._sessions.pop().obj
        return Session(self, sess)

    def add(self, sess):
        with self._lock:
            self._sessions.append(PoolObject(sess))
            self.scheduler.resume()

class SessionPoolManager():

    def __init__(self, envdata):
        self.irods_server = envdata.get('host')
        self.irods_zone = envdata.get('zone')
        self._pools = {}
        self._lock = threading.Lock()

    def session(self, user):
        with self._lock:
            if user.username not in self._pools:
                self._pools[user.username] = SessionPool()
        sess = self._pools[user.username].get(user)
        return sess

class SessionManagers():

    def __init__(self):
        self._managers = {}

    def init_app(self, app):
        for envname, envdata in app.config.get('IRODS_ENVS', {}).items():
            self._managers[envname] = SessionPoolManager(envdata)
 
    def session(self, user=current_user):
        """ Return an irods session object
        for current_user
        """
        sess = None
        mgr = self._managers.get(user.environment)
        if mgr:
            sess = mgr.session(user)
        return sess

irods_manager = SessionManagers()