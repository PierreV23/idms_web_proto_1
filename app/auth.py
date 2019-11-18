#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 14:33:10 2019

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user
from app.models import User
from irods.session import iRODSSession

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route("/login", methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        requestdata = request.form.to_dict()
        user = User(username=requestdata['username'], 
                        password=requestdata['password'],
                        environment=requestdata['environment'])
        if user.is_authenticated == False:
            print('Not auth')
            print(user.is_authenticated)
            print(user.irods_session)
            return redirect(url_for('auth.login'))
        else:
            print('Auth')
            login_user(user)
            return redirect('/')
    else:    
        return render_template('login.html')