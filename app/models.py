#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 16:39:47 2019

@author: wierinve
"""

import base64
import binascii
import hashlib
import ssl
from flask_login import UserMixin
from flask import session, current_app
from irods.session import iRODSSession
from irods.models import User, UserGroup
from irods.column import Criterion
from fs_irods import fs_irods

ATTR_DISPLAYNAME = 'sys::ad::displayName'

def obfuscate(data):
    return base64.b64encode(data.encode('utf-8'))

def deobfuscate(data):
    return base64.b64decode(data).decode('utf-8')


class WebUser(UserMixin):

    @property
    def irods_session(self):
        return self._irods_session

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

    def __init__(self, username='', password='', environment='', is_authenticated=False):
        self.username = username
        self.password = obfuscate(password)
        self.environment = environment
        self._is_authenticated = is_authenticated
        self._is_admin = None
        self.irods_server = None
        self.irods_zone = None
        self._irods_session = None
        self.features = []
        irods_env = current_app.config["IRODS_ENVS"].get(environment, None)
        if irods_env:
            self.irods_server = irods_env.get('host')
            self.irods_zone = irods_env.get('zone')
            self.features = irods_env.get('features', [])
        self.configure_irods_session(username, password)
        self._fullname = username
        self._irods_user = None

    @property
    def irods_user(self):
        if self._irods_user is None:
            if self.irods_session:
                try:
                    self._irods_user = self.irods_session.users.get(self.username)
                except KeyError:
                    pass
        print(self._irods_user)
        return self._irods_user
    
    @property
    def fullname(self):
        if self._fullname == self.username:
            if self.irods_session:
                if self.irods_user:
                    try:
                        displayname = self.irods_user.metadata.get_one(ATTR_DISPLAYNAME)
                    except KeyError:
                        pass
                    self._fullname = displayname.value
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
        if 'user_store' not in session:
            session['user_store'] = {}
        info = [self.username, self.password, self.environment, self.is_authenticated]
        session['user_store'][self.username] = info

    @classmethod
    def retrieve(cls, username):
        """Retrieve previously stored user from Flask session."""
        if 'user_store' in session and username in session['user_store']:
            username, pass_obfuscated, env, is_auth = session['user_store'][username]
            return cls(username, deobfuscate(pass_obfuscated), env, is_auth)
        return None
        

    def delete(self):
        """Delete user from Flask session."""
        if 'user_store' in session and self.username in session['user_store']:
            del session['user_store'][self.username]


    def configure_irods_session(self, username, password):
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
            user=username,
            password=password,
            zone=self.irods_zone,
            authentication_scheme='pam',
            **ssl_settings
        )
        self.ifs = fs_irods(session=self._irods_session)

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
