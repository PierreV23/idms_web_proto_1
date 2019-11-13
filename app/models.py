#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 16:39:47 2019

@author: wierinve
"""

from flask_login import UserMixin
from irods.session import iRODSSession
import ssl

class User(UserMixin):
    irods_session = None
    is_authenticated = False
    is_active = True
    is_anonymous = False
    def __init__(self, username='', password='', environment=''):
        self.username = username
        if environment == 'Productie':
            irodsServer = 'rivm-bioir-l01p.rivm.ssc-campus.nl'
        elif environment == 'Acceptatie':
            irodsServer = 'rivm-bioir-l01a.rivm.ssc-campus.nl'
        elif environment == 'Test':
            irodsServer = 'rivm-bioir-l01t.rivm.ssc-campus.nl'
        else:
            return None
        context = ssl._create_unverified_context(purpose=ssl.Purpose.SERVER_AUTH,
                                     cafile=None, capath=None, cadata=None)
        
        ssl_settings = {'irods_ssl_ca_certificate_file': '/etc/irods/ssl/test/irods.crt',
                'ssl_context': context }
        self.irods_session = iRODSSession(host=irodsServer,
                             port=1247,
                             user=username,
                             password=password,
                             zone='rivmZone',
                             **ssl_settings)    
        try:
            self.irods_session.collections.get('/rivmZone')
            self.is_authenticated = True
        except:
            print('NOT OK')
            pass
        
    def get_id(self):
        return self.username


