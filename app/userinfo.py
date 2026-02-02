#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 15:23:56 2019

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user, current_user, login_required
import sys
import subprocess
from app.irodssessions import irods_manager

bp = Blueprint('userinfo', __name__, url_prefix='/userinfo')

@bp.route('/api/setting', methods=['GET', 'POST', 'DELETE'])
def usersetting():
    if request.method == 'POST':
        if request.is_json:
            attr = request.json.get('attr')
            value = request.json.get('value')
        else:
            formdata = request.form.to_dict()
            attr = formdata.get('attr')
            value = formdata.get('value')
        current_user.settings[attr] = value
        return { 'result': 'OK'}, 200
    elif request.method == 'GET':
        attr = request.args.get('attr')
        value = current_user.settings.get(attr)
        if value is None:
            return { 'result': 'NOT FOUND' }, 404
        else:
            return { 'value': current_user.settings.get(attr, '') }, 200
    elif request.method == 'DELETE':
        if request.is_json:
            attr = request.json.get('attr')
            current_user.settings.delete(attr)
            return {'result': 'OK'}, 200

def userinfo(user):
    with irods_manager.session() as session:
        userinfo = session.users.get(user)
        input_meta = { x.name: x.value for x in userinfo.metadata.items()}
    return(input_meta)


def groupinfo(group):
    ginfo={}
    try:
        with irods_manager.session() as session:
            gobj = session.user_groups.get(group)
    except:
        ginfo["None"] = {'sys::ad::mail': None, 'sys::ad::department': None}
        return(ginfo)
    for n in gobj.members:
        x = n.name.split("_")
        if x[0] == "svc-irods" or x[0] == "svc-sscc-irods":
            ginfo[n.name] = userinfo(n.name)
            ginfo[n.name].update({"serviceaccount": True})
        else:
            ginfo[n.name] = userinfo(n.name)
            ginfo[n.name].update({"serviceaccount": False})
    return(ginfo)
 
@bp.route('/groupdetails')
@login_required
def groupdetails(): 
    group = request.args.get('group','', type=str)
    ginfo = groupinfo(group)
    return render_template('groupdetails.html', group=group, ginfo=ginfo)
