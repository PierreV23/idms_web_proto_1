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
import logging

from Crypto.Hash import MD4
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from flask_login import UserMixin
from flask import session, current_app
from flask_login import current_user
from irods.models import User, UserGroup, UserMeta
from irods.column import Criterion
from fs_irods import fs_irods
from . import flaskcache
from . import iqry
from app.irodssessions import irods_manager, create_session

ATTR_DISPLAYNAME = 'sys::ad::displayName'

class AuthException(Exception):
    pass

def encrypt(data):
    public_key = current_app.config.get("RSA_PUBLIC_KEY")
    cipher_rsa = PKCS1_OAEP.new(public_key)
    enc_data = cipher_rsa.encrypt(data.encode('utf-8'))
    return enc_data

def decrypt(enc_data):
    private_key = current_app.config.get("RSA_PRIVATE_KEY")
    cipher_rsa = PKCS1_OAEP.new(private_key)
    data = cipher_rsa.decrypt(enc_data)
    return data.decode('utf-8')

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

    def items(self):
        meta = iqry.qcollmetadict(f'/{current_user.irods_zone}/home/{current_user.username}')
        keys = [ k[len(self.prefix):] for k in meta if k.startswith(self.prefix) ]
        return [ (k, self[k]) for k in keys ]

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
                    with irods_manager.session() as session:
                        groups = session.query(UserGroup).filter(
                            Criterion('=', User.name, self.username)).filter(
                                Criterion('=', UserGroup.name, 'rodsadmin'))
                        for q in groups:
                            self._is_admin = True
                except:
                    self._is_admin = None
                    return False
        return self._is_admin

    def __init__(self, password=None, encrypted_password=None, **kwargs):
        self.username = None
        self.environment = None
        self._is_authenticated = False
        self._is_admin = None
        self.irods_server = None
        self.irods_zone = None
        self.features = []
        self._fullname = None

        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

        if password:
            self.password = encrypt(password)
        elif encrypted_password:
            self.password = encrypted_password
        else:
            raise AuthException

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
        with irods_manager.session() as session:
            q = session.query(UserGroup).filter( User.name == self.username )
            result = [ r[UserGroup.name] for r in q ]
        return result

    @flaskcache.cache.memoize(timeout=3600, make_name=flaskcache.dep_userzone)
    def projects(self):
        with irods_manager.session() as session:
            q = session.query(UserGroup.name, UserMeta.value).filter(\
                Criterion('=', UserMeta.name, 'projectID'))
            grps = self.groups()
            usr_groups = [ r for r in q if r[UserGroup.name] in grps ]

            my_projects = [ r[UserMeta.value] for r in usr_groups ]

        return my_projects
        
    @property
    def fullname(self):
        if self._fullname is None or self._fullname == self.username:
            self._fullname = iqry.qusermetaval(self.username, ATTR_DISPLAYNAME, self.username)
        return self._fullname

    @property
    def ntlm_hash(self):
        password = self.passwd
        ntlm_hash = MD4.new(password.encode('utf-16le')).hexdigest()
        lmntlm = '{}:{}'.format('0' * 32, ntlm_hash)
        return lmntlm

    @property
    def passwd(self):
        try:
            return decrypt(self.password)
        except:
            raise AuthException
    
    @property
    def passwd_hash(self):
        return base64.b64encode(self.passwd.encode()).decode('ascii')

    def store(self):
        """Store user in Flask session."""
        if 'user_data' not in session:
            session['user_data'] = {}
        info = {
            'username': self.username,
            'encrypted_password': self.password,
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
            if user.is_authenticated:
                return user
            else:
                return None
        return None
        
    def delete(self):
        """Delete user from Flask session."""
        if 'user_data' in session:
            del session['user_data']


    @property
    def ifs(self):
        return fs_irods(session=irods_manager.session())

    def validate_irods_session(self):
        try:
            # we cannot use the session in the sessionmanager, as it is identified by the username only
            # to check the credentials, we need to make a new session with the password of this webuser.
            check_pw_session = create_session(current_app.config["IRODS_ENVS"].get(self.environment, None), self)
            check_pw_session.collections.get("/")
            self._is_authenticated = True
            return True
        except:
            logging.info(f"Authentication (session validation) failed for user {self.username} on {self.environment}")
            irods_manager.remove(self)
        return False


    def get_id(self):
        return self.username
