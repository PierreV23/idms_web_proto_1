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
from irods.models import Collection, CollectionMeta, DataObject, Resource, ResourceMeta, DataObjectMeta
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
    for q in ['incoming', 'stage', 'queued', 'startup', 'active']:
        enabled = True
        path = f'/{current_user.irods_zone}/system/runsheet'
        metaquery = current_user.irods_session.query(CollectionMeta.value).filter(
            Criterion('=', Collection.name, path)).filter(
            Criterion('=', CollectionMeta.name, f'sys::enable::{q}'))
        for meta in metaquery:
            enabled = meta[CollectionMeta.value] == 'true'
        items = current_user.irods_session.query(DataObject.id).filter(\
            Criterion('=', Collection.name, '/rivmZone/system/runsheet/processing')).filter(\
            Criterion('=', DataObjectMeta.name, 'sys::runsheet::state')).filter(\
            Criterion('=', DataObjectMeta.value, q)).count(DataObject.id)
        count  = items.execute()[0][DataObject.id]
        #print(next(items.get_results()))
        queues[q] = {'enabled': enabled, 'count': count}
    return render_template('queues.html', queues=queues)

@login_required
@bp.route('/resources')
def resources():
    resources =  {}
    q = current_user.irods_session.query(Resource.name)
    for r in q:
        resource = current_user.irods_session.resources.get(r[Resource.name])
        resources[r[Resource.name]] = { m.name: m.value for m in resource.metadata.items() if m.name.startswith('sys::resource')}
        m = resource.metadata.get_all('sys::tiering::group')
        if m:
            resources[r[Resource.name]]['group'] = m[0].value
            resources[r[Resource.name]]['id'] = m[0].units
    return render_template('resources.html', resources=resources)

@login_required
@bp.route('/_update_resources', methods=['POST'])
def update_resources():
    TEXT_PROPERTIES = ( 
        "sys::resource::copies",
        "sys::resource::cost",
        "sys::resource::minfree",
        "sys::resource::min_age_before_copy",
        "sys::resource::min_age_before_trim"
    )
    BOOL_PROPERTIES = (
        "sys::resource::local",
        "sys::resource::online",
        "sys::resource::stage",
        "sys::resource::surf",
        "sys::resource::tar",
        "sys::resource::keep"
    )
    data = request.form.to_dict()
    # Create a dict of the form data
    resources = {}
    for d in data:
        resource, attr = d.split('__')
        value = data[d]
        if not resource in resources:
            resources[resource] = {}
        resources[resource][attr] = value
    # Update resource settings
    for resource in resources:
        res_obj = current_user.irods_session.resources.get(resource)
        for property in TEXT_PROPERTIES:
            if property in resources[resource] and resources[resource][property]:
                res_obj.metadata[property] = iRODSMeta(property, resources[resource][property])
            else:
                del res_obj.metadata[property]
        for property in BOOL_PROPERTIES:
            value = resources[resource].get(property, 'false')
            res_obj.metadata[property] = iRODSMeta(property, value)
        group = resources[resource].get('group')
        id = resources[resource].get('id')
        if group and id:
            res_obj.metadata['sys::tiering::group'] = iRODSMeta('sys::tiering::group', group, id)
        else:
            del res_obj.metadata['sys::tiering::group']

    return redirect(url_for('admin.resources'))

@bp.route('/modify')
@login_required
def modify():
    data = request.args.to_dict()
    action = data.get('action')
    queue = data.get('queue', 'none')
    if action is None:
        return redirect(url_for('admin.admin'))
    if action == 'disable' or action == 'enable':
        value = 'true' if action == 'enable' else 'false'
        new_meta = iRODSMeta(f'sys::enable::{queue}', value)
        coll = os.path.join('/', current_user.irods_zone, 'system/runsheet')
#        try:
        collobj = current_user.irods_session.collections.get(coll)
        collobj.metadata[new_meta.name] = new_meta
#        except:
#            print('ERROR')
    return redirect(url_for('admin.admin'))
