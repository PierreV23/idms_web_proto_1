#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 16:39:47 2019

@author: wierinve
"""

import base64
import binascii
import hashlib
import json
import ssl
import time
from flask_login import UserMixin
from flask import session, current_app
from flask_login import current_user
from irods.session import iRODSSession
from irods.models import User, UserGroup
from irods.column import Criterion
from irods.meta import iRODSMeta
from irods.user import iRODSUserGroup
from fs_irods import fs_irods
from . import flaskcache
from . import iqry
#from .ngsruns import db

ATTR_DISPLAYNAME = 'sys::ad::displayName'

def obfuscate(data):
    return base64.b64encode(data.encode('utf-8'))

def deobfuscate(data):
    return base64.b64decode(data).decode('utf-8')

class IRSettings:
    def __init__(self, user, prefix=''):
        self.user = user
        self.prefix = prefix

    def __getitem__(self, key):
        val = iqry.qcollmetaval(f'/{current_user.irods_zone}/home/{current_user.username}', f'{self.prefix}{key}')
        if val is None:
            raise KeyError
        return json.loads(val)

    def __setitem__(self, key, value):
        iqry.scollmetaval(f'/{current_user.irods_zone}/home/{current_user.username}', f'{self.prefix}{key}', json.dumps(value))

    def get(self, key, default=None):
        try:
            value = self[key]
        except KeyError:
            value = default
        return value

    def setdefault(self, key, default):
        try:
            value = self[key]
        except KeyError:
            self[key] = default
        return self[key]



class WebUser(UserMixin):

    @property
    def is_authenticated(self):
        return self._is_authenticated

    @property
    def is_admin(self):
        if self._is_admin is None:
            self._is_admin = False
            if self._is_authenticated:
                try:
                    groups = self._irods_session.query(UserGroup).filter(
                        Criterion('=', User.name, self.username)).filter(
                            Criterion('=', UserGroup.name, 'rodsadmin'))
                    for q in groups:
                        self._is_admin = True
                except:
                    self._is_admin = None
                    return False
        return self._is_admin

    def __init__(self, password=None, obfuscated_password=None, **kwargs):
        self.username = None
        self.environment = None
        self._is_authenticated = False
        self._is_admin = False
        self.irods_server = None
        self.irods_zone = None
        self._irods_session = None
        self._ifs = None
        self.features = []
        self._fullname = None

        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

        if password:
            self.password = obfuscate(password)
        elif obfuscated_password:
            self.password = obfuscated_password

        irods_env = current_app.config["IRODS_ENVS"].get(self.environment, None)
        if irods_env:
            self.irods_server = irods_env.get('host')
            self.irods_zone = irods_env.get('zone')
            self.features = irods_env.get('features', [])
            self.minilims_db = irods_env.get('minilims_db', 'sqlite://')
        self.settings = IRSettings(self.username, prefix='ngsweb::')

    def __repr__(self):
        return f'WebUser({self.username})'

    @flaskcache.cache.memoize(timeout=3600, make_name=flaskcache.dep_userzone)
    def groups(self):
        return [ r[UserGroup.name] for r in current_user.irods_session.query(UserGroup).filter( User.name == self.username ) ]

    @flaskcache.cache.memoize(timeout=3600, make_name=flaskcache.dep_userzone)
    def projects(self):
        usr_groups = [ current_user.irods_session.user_groups.get(r) for r in self.groups() ]
        # usr_groups = [ (iRODSUserGroup ( current_user.irods_session.user_groups, result) ) \
        #     for result in current_user.irods_session.query(UserGroup).filter( User.name == self.username ) ]

        my_projects = []
        for group in usr_groups:
            try:
                project = group.metadata.get_one('projectID')
                my_projects.append(project.value)
            except KeyError:
                pass
        return my_projects
        
    @property
    def fullname(self):
        if self._fullname is None or self._fullname == self.username:
            self._fullname = iqry.qusermetaval(self.username, ATTR_DISPLAYNAME, self.username)
        return self._fullname

    @property
    def ntlm_hash(self):
        password = deobfuscate(self.password)
        hash = binascii.hexlify(hashlib.new('md4', password.encode('utf-16le')).digest()).decode('ascii')
        lmntlm = '{}:{}'.format('0' * 32, hash) 
        return lmntlm

    @property
    def passwd(self):
        return deobfuscate(self.password)

    def store(self):
        """Store user in Flask session."""
        if 'user_data' not in session:
            session['user_data'] = {}
        info = {
            'username': self.username,
            'obfuscated_password': self.password,
            'environment': self.environment,
            '_is_authenticated': self.is_authenticated,
            '_is_admin': self.is_admin,
            '_fullname': self.fullname
        }
        session['user_data'][self.username] = info

    @classmethod
    def retrieve(cls, username):
        """Retrieve previously stored user from Flask session."""
        if 'user_data' in session and username in session['user_data']:
            try:
                user = cls(**session['user_data'][username])
            except:
                return None
            return user
        if 'user_store' in session and username in session['user_store']:
            try:
                username, pass_obfuscated, env, is_auth, is_admin = session['user_store'][username]
            except:
                return None
            return cls(username=username,obfuscated_password=pass_obfuscated, environment=env, _is_authenticated=is_auth, _is_admin=is_admin)
        return None
        
    def delete(self):
        """Delete user from Flask session."""
        if 'user_store' in session and self.username in session['user_store']:
            del session['user_store'][self.username]

    @property
    def irods_session(self):
        if self._irods_session is None:
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
            self._irods_session = iRODSSession(
                host=self.irods_server,
                port=1247,
                user=self.username,
                password=self.passwd,
                zone=self.irods_zone,
                authentication_scheme='pam',
                **ssl_settings
            )
        return self._irods_session

    @property
    def ifs(self):
        if self._ifs is None:
            self._ifs = fs_irods(session=self.irods_session)
        return self._ifs



    def cleanup(self):
        if self._irods_session:
            _irods_session.cleanup()

    def validate_irods_session(self):
        try:
            self.irods_session.collections.get(f'/{self.irods_zone}')
            self._is_authenticated = True
            return True
        except:
            print('Authentication failed.')
        return False

    def get_id(self):
        return self.username
