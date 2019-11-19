#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 16:39:47 2019

@author: wierinve
"""

from flask_login import UserMixin
from irods.session import iRODSSession
import ssl
from fs_irods import fs_irods

class User(UserMixin):
    _irods_session = None
    is_authenticated = False
    is_active = True
    is_anonymous = False
    username = ''
    
    @property
    def irods_session(self):
        return self._irods_session
    
    def __init__(self, username='', password='', environment=''):
        self.username = username
        if environment == 'Productie':
            self.irods_server = 'rivm-bioir-l01p.rivm.ssc-campus.nl'
        elif environment == 'Acceptatie':
            self.irods_server = 'rivm-bioir-l01a.rivm.ssc-campus.nl'
        elif environment == 'Test':
            self.irods_server = 'rivm-bioir-l01t.rivm.ssc-campus.nl'
        else:
            return None
        context = ssl._create_unverified_context(purpose=ssl.Purpose.SERVER_AUTH,
                                     cafile=None, capath=None, cadata=None)
        
        ssl_settings = {'irods_ssl_ca_certificate_file': '/etc/irods/ssl/test/irods.crt',
                'ssl_context': context }
        self._irods_session = iRODSSession(host=self.irods_server,
                             port=1247,
                             user=username,
                             password=password,
                             zone='rivmZone',
                             authentication_scheme='pam',
                             **ssl_settings)    
        
        try:
            self.irods_session.collections.get('/rivmZone')
            self.is_authenticated = True
        except:
            print('NOT OK')

        if self.is_authenticated:
            self.ifs = fs_irods(session = self.irods_session)
            Userstore.AddUser(self)
        
    def get_id(self):
        return self.username

class clUserStore():
    def __init__(self):
        self.store = {}

    def AddUser(self, User):
        self.store[User.username] = User

    def GetUser(self, Name):
        if Name in self.store:
            return self.store[Name]
        else:
            return None
        
    def delete(self, username):
        if username in self.store:
            del self.store[username]

Userstore = clUserStore()
