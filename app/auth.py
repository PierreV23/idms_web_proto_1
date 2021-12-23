#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 14:33:10 2019

@author: wierinve
"""
from datetime import timedelta
from flask import Blueprint, flash, render_template, redirect, request, url_for, current_app
from flask_login import login_user, logout_user, current_user, login_required
from app.models import WebUser
from . import messages

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route("/login", methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        requestdata = request.form.to_dict()
        user = WebUser(username=requestdata['username'],
                    password=requestdata['password'],
                    environment=requestdata['environment'])

        if not user.validate_irods_session():
            flash('Login to the web interface failed', 'login')
            return redirect(url_for("auth.login"))
        user.store()
        login_user(user, duration=timedelta(hours=24))
        # Check for messages
        for message in messages.getmessages():
            flash(message, "news")
        return redirect(requestdata['next'])
    else:
        nexturl = request.args.get('next', default='/', type=str)
        return render_template('login.html', next=nexturl, envs=current_app.config["IRODS_ENVS"])


@bp.route('/logout')
@login_required
def logout():
    current_user.delete()
    logout_user()
    return redirect(url_for('auth.login'))
