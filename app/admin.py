#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 15 10:46:50 2020

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import current_user, login_required
from irods.meta import iRODSMeta
from irods.models import Collection, CollectionMeta, DataObject
from irods.column import Criterion


bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/')
@login_required
def admin():
    if not current_user.is_admin:
        return render_template('denied.html')
    queues = {}
    for q in ['incoming', 'stage', 'queued', 'active', 'waiting']:
        enabled = True
        path = '/rivmZone/system/runsheet/' + q
        metaquery = current_user.irods_session.query(CollectionMeta.value).filter(
            Criterion('=', Collection.name, path)).filter(
            Criterion('=', CollectionMeta.name, 'sys::enable'))
        for meta in metaquery:
            enabled = meta[CollectionMeta.value] == 'true'
        items = current_user.irods_session.query(DataObject.id).filter(
            Criterion('=', Collection.name, path)).count(DataObject.id)
        count  = items.execute()[0][DataObject.id]
        print(count)
        #print(next(items.get_results()))
        queues[q] = {'enabled': enabled, 'count': count}
    return render_template('admin.html', queues=queues)

@bp.route('/modify')
@login_required
def modify():
    data = request.args.to_dict()
    action = data.get('action')
    if action is None:
        return redirect(url_for('admin.admin'))
    if action == 'disable' or action == 'enable':
        value = 'true' if action == 'enable' else 'false'
        new_meta = iRODSMeta('sys::enable', value)
        coll = '/rivmZone/system/runsheet/' + data.get('queue', 'none')
#        try:
        collobj = current_user.irods_session.collections.get(coll)
        collobj.metadata[new_meta.name] = new_meta
#        except:
#            print('ERROR')
    return redirect(url_for('admin.admin'))
