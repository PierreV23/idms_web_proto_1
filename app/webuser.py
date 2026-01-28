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
from irods.models import User, Group, UserMeta
from irods.column import Criterion
from fs_irods import fs_irods
from . import flaskcache
from . import iqry
from app.irodssessions import irods_manager, create_session
from app.iconnect import Connection2
from app.constants import FEATURES

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

    def __init__(self, username=None, environment=None, encrypted_password="", encrypted_native_password=None,
                 is_authenticated=None, is_admin=None, fullname=None, **kwargs):
        """WebUser application user instance

        These args are required.
            username (_type_, optional): _description_. Defaults to None.
            environment (_type_, optional): _description_. Defaults to None.
            password (str, optional): _description_. Defaults to "".
        
        These args can be supplied to speed up the user creation, but they are optional.
            native_password (_type_, optional): _description_. Defaults to None.
            is_authenticated (bool, optional): _description_. Defaults to False.
            is_admin (bool, optional): _description_. Defaults to False.
            fullname (_type_, optional): _description_. Defaults to None.
        """        
        self.username = username
        self.environment = environment
        self._encrypted_password = encrypted_password
        self._encrypted_native_password = encrypted_native_password
        self._is_authenticated = is_authenticated
        self._is_admin = is_admin
        self._fullname = fullname

        self._irods_env = {}

        self.settings = IRSettings(self.username, prefix='ngsweb::')
        
    @classmethod
    def from_login(cls, username=None, password=None, environment=None):
        return cls(username=username, encrypted_password=encrypt(password), environment=environment)

    def __repr__(self):
        return f'WebUser({self.username})'

# iRODS session properties
    @property
    def irods_env(self):
        return current_app.config["IRODS_ENVS"].get(self.environment, None)
    
    @property
    def irods_server(self):
        return self.irods_env.get('host')
    
    @property
    def irods_zone(self):
        return self.irods_env.get('zone')
    
    @property
    def refdata_coll(self):
        return self.irods_env.get('refdata_collection', None)
    
    @flaskcache.cache.memoize(timeout=5, make_name=flaskcache.dep_userzone)
    def feature(self, name):
        default = FEATURES.get(name, (None, 'false'))[1]
        return self.settings.get(f'feature::{name}', default) == 'true'
    
    @property
    def minilims_db(self):
        self.minilims_db = self.irods_env.get('minilims_db', 'sqlite://')
    
# Authentication properties        

    @property
    def is_authenticated(self):
        if self._is_authenticated is None:
            self.validate_irods_session()
        return self._is_authenticated
    
    @property
    def password(self):
        return decrypt(self._encrypted_password)
   
    @property
    def native_password(self):
        if self._encrypted_native_password is None:
            self.validate_irods_session()
        return decrypt(self._encrypted_native_password)

    @property
    def is_admin(self):
        if self._is_admin is None:
            self._is_admin = False
            if self._is_authenticated:
                try:
                    with irods_manager.session() as session:
                        user = session.users.get(self.username)
                        self._is_admin = user.type == 'rodsadmin'
                except:
                    self._is_admin = None
                    return False
        return self._is_admin
    
    @flaskcache.cache.memoize(timeout=3600, make_name=flaskcache.dep_userzone)
    def groups(self):
        with irods_manager.session() as session:
            q = session.query(Group).filter( User.name == self.username )
            result = [ r[Group.name] for r in q ]
        return result

    @flaskcache.cache.memoize(timeout=3600, make_name=flaskcache.dep_userzone)
    def projects(self):
        with irods_manager.session() as session:
            q = session.query(Group.name, UserMeta.value).filter(\
                Criterion('=', UserMeta.name, 'projectID'))
            grps = self.groups()
            usr_groups = [ r for r in q if r[Group.name] in grps ]

            my_projects = list(set([ r[UserMeta.value] for r in usr_groups ]))

        return my_projects
        
    @property
    def fullname(self):
        if self._fullname is None or self._fullname == self.username:
            self._fullname = iqry.qusermetaval(self.username, ATTR_DISPLAYNAME, self.username)
        return self._fullname

    @property
    def ntlm_hash(self):
        ntlm_hash = MD4.new(self.password.encode('utf-16le')).hexdigest()
        lmntlm = '{}:{}'.format('0' * 32, ntlm_hash)
        return lmntlm

    def store(self):
        """Store user in Flask session."""
        if 'user_data' not in session:
            session['user_data'] = {}
        info = {
            'username': self.username,
            'environment': self.environment,
            'encrypted_password': self._encrypted_password,
            'encrypted_native_password': self._encrypted_native_password,
            'is_authenticated': self.is_authenticated,
            'is_admin': self.is_admin,
            'fullname': self.fullname
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
        irods_manager.remove(self)


    @property
    def ifs(self):
        return fs_irods(session=irods_manager.session())

    def validate_irods_session(self):
        try:
            # we cannot use the session in the sessionmanager, as it is identified by the username only
            # to check the credentials, we need to make a new session with the password of this webuser.
            
            # Create iRODS session and verify if root collection can be retrieved
            check_pw_session = create_session(current_app.config["IRODS_ENVS"].get(self.environment, None), self, use_pam=True)
            # Get the temporary password from our custom Connection class
            conn = Connection2(check_pw_session.pool, check_pw_session.pool.account)
            # Store the temporary password
            self._encrypted_native_password = encrypt(conn.native_password)
            self._is_authenticated = True
            check_pw_session.cleanup()
            # Remove old sessions
            irods_manager.remove(self)
            return True
        except:
            logging.info(f"Authentication (session validation) failed for user {self.username} on {self.environment}")
            irods_manager.remove(self)
        return False


    def get_id(self):
        return self.username
