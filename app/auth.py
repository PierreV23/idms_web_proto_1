#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 14:33:10 2019

@author: wierinve
"""
from datetime import timedelta
from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user, logout_user, current_user, login_required
from app.models import WebUser

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route("/login", methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        requestdata = request.form.to_dict()
        user = WebUser(username=requestdata['username'],
                    password=requestdata['password'],
                    environment=requestdata['environment'])

        if not user.validate_irods_session():
            print('Not auth')
            print(user.is_authenticated)
            print(user.irods_session)
            return redirect(url_for('auth.login'))
        print('Auth')
        print(user.is_admin)
        user.store()
        login_user(user, duration=timedelta(hours=24))
        return redirect(requestdata['next'])
    else:
        nexturl = request.args.get('next', default='/', type=str)
        return render_template('login.html', next=nexturl, debug=False)


@bp.route('/logout')
@login_required
def logout():
    current_user.delete()
    logout_user()
    return redirect(url_for('auth.login'))
