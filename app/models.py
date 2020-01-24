#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 16:39:47 2019

@author: wierinve
"""

import base64
import ssl
from flask_login import UserMixin
from flask import session
from irods.session import iRODSSession
from fs_irods import fs_irods

IRODS_ENVS = {
    'Productie':   'rivm-bioir-l01p.rivm.ssc-campus.nl',
    'Acceptatie':   'rivm-bioir-l01a.rivm.ssc-campus.nl',
    'Test':         'rivm-bioir-l01t.rivm.ssc-campus.nl',
}


def obfuscate(data):
    return base64.b64encode(data.encode('utf-8'))

def deobfuscate(data):
    return base64.b64decode(data).decode('utf-8')


class User(UserMixin):

    @property
    def irods_session(self):
        return self._irods_session

    @property
    def is_authenticated(self):
        return self._is_authenticated

    def __init__(self, username='', password='', environment='', is_authenticated=False):
        self.username = username
        self.password = obfuscate(password)
        self.environment = environment
        self._is_authenticated = is_authenticated
        self.irods_server = IRODS_ENVS.get(environment, None)
        self.configure_irods_session(username, password)

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
            'irods_ssl_ca_certificate_file': '/etc/irods/ssl/test/irods.crt',
            'ssl_context': context
        }

        # Creating an iRODS does not imply a connection is set up.
        self._irods_session = iRODSSession(
            host=self.irods_server,
            port=1247,
            user=username,
            password=password,
            zone='rivmZone',
            authentication_scheme='pam',
            **ssl_settings
        )
        self.ifs = fs_irods(session=self._irods_session)

    def validate_irods_session(self):
        try:
            self.irods_session.collections.get('/rivmZone')
            self._is_authenticated = True
            return True
        except:
            print('Authentication failed.')
        return False

    def get_id(self):
        return self.username
