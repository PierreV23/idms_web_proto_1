#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 15 10:46:50 2020

@author: wierinve
"""
import os
from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import current_user, login_required
from irods.meta import iRODSMeta
from irods.models import Collection, CollectionMeta, DataObject
from irods.column import Criterion
from irods.query import SpecificQuery


bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/_issues')
def query_issues():
    if not current_user.is_admin:
        return('<TR><TD COLSPAN=3>Access denied</TD></TR>')
    data = ''
    query = SpecificQuery(current_user.irods_session, alias='checksums_differ')
    for result in query:
        base, name = os.path.split(result[0])
        data = '{}<TR><TD COLSPAN=5><A HREF="{}?path={}">{}</A></TD></TR>'.format(data, url_for("collbrowser.collbrowser"), base, result[0])
        q = current_user.irods_session.query(DataObject.path,
                                             DataObject.resource_name,
                                             DataObject.size, 
                                             DataObject.checksum).filter(
            Criterion('=', Collection.name, base)).filter(
            Criterion('=', DataObject.name, name))
        for objfile in q:
            data = '{}<TR><td></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></TR>'.format(data, 
                                                            objfile[DataObject.path],
                                                            objfile[DataObject.resource_name],
                                                            objfile[DataObject.size],
                                                            objfile[DataObject.checksum])
    return data

@bp.route('/issues')
@login_required
def issues():
    return render_template('issues.html')

@bp.route('/queues')
@login_required
def admin():
    if not current_user.is_admin:
        return render_template('denied.html')
    queues = {}
    for q in ['incoming', 'stage', 'queued', 'active']:
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
    return render_template('queues.html', queues=queues)

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
