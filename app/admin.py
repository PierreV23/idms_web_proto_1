#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 15 10:46:50 2020

@author: wierinve
"""
import os
import irods.exception
from flask import Blueprint, render_template, redirect, jsonify, request, url_for
from flask_login import current_user, login_required
from irods.meta import iRODSMeta
from irods.models import Collection, CollectionMeta, DataObject, Resource, ResourceMeta, DataObjectMeta
from irods.column import Criterion
from irods.query import SpecificQuery
from app.irods_helper import getmetaitem
from app.datafield import datafield

ATTR_ARCHIVE_STATUS = "sys::archive::status"
ATTR_ARCHIVE_STATUSMSG = "sys::archive::statusmsg"
ATTR_ARCHIVE_LASTCHECK = "sys::archive::lastcheck"
ATTR_ARCHIVE_STATE = "sys::archive::state"

ATTR_ARCHIVE_TARFILE = 'sys::archive::tarfile'
ATTR_ARCHIVE_MANIFESTFILE = 'sys::archive::manifest'

bp = Blueprint('admin', __name__, url_prefix='/admin')

# iRODS resource properties


RESOURCE_PROPS = {
    'group': {
        'label': 'Group', 
        'meta' : 'sys::tiering::group',
        'type' : 'text'
    },
    'group_id': {
        'label': 'ID',
        'meta': 'sys::tiering::group',
        'type': 'text',
        'unit': True
    },
    'copies': {
        'label': 'Copies',
        'meta': 'sys::resource::copies',
        'type': 'text'
    },
    'cost': {
        'label': 'Cost',
        'meta': 'sys::resource::cost',
        'type': 'text'
    },
    'age_before_copy': {
        'label': 'Minimum age before copy',
        'meta': 'sys::resource::min_age_before_copy',
        'type': 'text'
    },
    'age_before_trim': {
        'label': 'Minimum age before trim',
        'meta': 'sys::resource::min_age_before_trim',
        'type': 'text'
    },
    'minfree': {
        'label': 'Minimum free space',
        'meta': 'sys::resource::minfree',
        'type': 'text'
    },
    'local': {
        'label': 'Local',
        'meta': 'sys::resource::local',
        'type': 'bool'
    },
    'online': {
        'label': 'Online',
        'meta': 'sys::resource::online',
        'type': 'bool'
    },
    'stage': {
        'label': 'Stage',
        'meta': 'sys::resource::stage',
        'type': 'bool'
    },
    'keep': {
        'label': 'Keep',
        'meta': 'sys::resource::keep',
        'type': 'bool'
    },
    'surf': {
        'label': 'SURF',
        'meta': 'sys::resource::surf',
        'type': 'bool'
    },
    'tar': {
        'label': 'TAR',
        'meta': 'sys::resource::tar',
        'type': 'bool'
    },
    'manifest': {
        'label': 'MANIFEST',
        'meta': 'sys::resource::manifest',
        'type': 'bool'
    },
    'available': {
        'label': 'Available',
        'meta': 'sys::resource::available',
        'type': 'bool'
    },
    'enabled': {
        'label': 'Enabled',
        'meta': 'sys::resource::enabled',
        'type': 'bool'
    }
}


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

@bp.route('/_aract', methods=['POST'])
def archive_action():
    requestdata = request.form.to_dict()
    action = requestdata.get('action')
    collection = requestdata.get('collection')
    try:
        collobj = current_user.irods_session.collections.get(collection)
    except irods.exception.CollectionDoesNotExist:
        return jsonify({'message': 'Collection does not exist'})
    if action == 'remove_archive':
        state =  getmetaitem(collobj, ATTR_ARCHIVE_STATE)
        if state is None:
            return jsonify({'message': 'Cannot modify collection with unknown state'})
        if state.count('1')<2: # Dont remove archive if no other copy is present
            return jsonify({'message': 'Cannot remove last data copy in collection'})
        for attr in (ATTR_ARCHIVE_TARFILE, ATTR_ARCHIVE_MANIFESTFILE):
            filename = getmetaitem(collobj, attr)
            if filename and current_user.ifs.fileexists(filename):
                current_user.irods_session.data_objects.unlink(filename)
                collobj.metadata.remove(iRODSMeta(attr, filename))
    if action in ('clear_status', 'remove_archive') :
        for attr in (ATTR_ARCHIVE_STATUS, ATTR_ARCHIVE_STATUSMSG, ATTR_ARCHIVE_LASTCHECK):
            val = getmetaitem(collobj, attr)
            if val:
                collobj.metadata.remove(iRODSMeta(attr, val))
    return jsonify({'status':'ok'})

@bp.route('_archissue', methods=['GET'])
@login_required
def archive_issues():
    # Get issue collections
    query = current_user.irods_session.query(Collection.name, CollectionMeta.value).filter(
        Criterion('=', CollectionMeta.name, ATTR_ARCHIVE_STATUS)).filter(
        Criterion('!=', CollectionMeta.value, 'OK'))
    items = []
    for result in query:
        statusmsg = ""
        coll = current_user.irods_session.collections.get(result[Collection.name])
        statusmsg = getmetaitem(coll, ATTR_ARCHIVE_STATUSMSG, default="")
        allow_remove = False
        state = getmetaitem(coll, ATTR_ARCHIVE_STATE)
        if state and state.count('1')>1:
            allow_remove = True
        items.append({ 
            'collection': datafield('Collection', result[Collection.name], 'irods_collection'),
            'status': result[CollectionMeta.value],
            'statusmsg': statusmsg,
            'allow_remove': allow_remove
        })
    return render_template('archive_issues.html', items=items)


@bp.route('/queues')
@login_required
def admin():
    if not current_user.is_admin:
        return render_template('denied.html')
    queues = {}
    for q in ['incoming', 'prepare', 'stage', 'queued', 'startup', 'active', 'poststartup', 'postprocessing', 'waiting']:
        enabled = True
        path = f'/{current_user.irods_zone}/system/runsheet'
        metaquery = current_user.irods_session.query(CollectionMeta.value).filter(
            Criterion('=', Collection.name, path)).filter(
            Criterion('=', CollectionMeta.name, f'sys::enable::{q}'))
        for meta in metaquery:
            enabled = meta[CollectionMeta.value] == 'true'
        if q == 'incoming':
            items = current_user.irods_session.query(DataObject.id).filter(\
                Criterion('=', Collection.name, '/rivmZone/system/runsheet/processing')).filter(\
                Criterion('=', DataObjectMeta.name, 'sys::runsheet::state')).filter(\
                Criterion('=', DataObjectMeta.value, q)).count(DataObject.id)
            count  = items.execute()[0][DataObject.id]
        else:
            items = current_user.irods_session.query(Collection.id).filter(\
                Criterion('=', Collection.name, '/rivmZone/system/runsheet/processing')).filter(\
                Criterion('=', CollectionMeta.name, 'sys::runsheet::state')).filter(\
                Criterion('=', CollectionMeta.value, q)).count(Collection.id)
            count  = items.execute()[0][Collection.id]
        queues[q] = {'enabled': enabled, 'count': count}
    return render_template('queues.html', queues=queues)

@login_required
@bp.route('/resources')
def resources():
    resources =  {}
    q = current_user.irods_session.query(Resource.name)
    for r in q:
        resources[r[Resource.name]] = {}
        resource = current_user.irods_session.resources.get(r[Resource.name])
        metadata = resource.metadata.items()
        metanames = [ m.name for m in metadata ]
        for property in RESOURCE_PROPS:
            meta_name = RESOURCE_PROPS[property].get('meta')
            if meta_name:
                if meta_name in metanames:
                    irods_meta = resource.metadata.get_one(meta_name)
                    if RESOURCE_PROPS[property].get('unit', False):
                        resources[r[Resource.name]][property] = irods_meta.units
                    else:
                        resources[r[Resource.name]][property] = irods_meta.value
    return render_template('resources.html', columns=RESOURCE_PROPS, resources=resources)

@login_required
@bp.route('/_update_resources', methods=['POST'])
def update_resources():

    data = request.form.to_dict()
    # Create a dict of the form data
    new_settings = {}
    for d in data:
        resource, attr = d.split('__')
        value = data[d]
        if not resource in new_settings:
            new_settings[resource] = {}
        new_settings[resource][attr] = value
    for resource in new_settings:
        res_obj = current_user.irods_session.resources.get(resource)
        for property in RESOURCE_PROPS:
            meta_name = RESOURCE_PROPS[property]['meta']
            if property in new_settings[resource]:
                if new_settings[resource][property]:
                    try:
                        current_meta = res_obj.metadata.get_one(meta_name)
                    except KeyError:
                        current_meta = iRODSMeta(meta_name, '')
                    new_meta = iRODSMeta(meta_name, current_meta.value, current_meta.units)
                    if RESOURCE_PROPS[property].get('unit', False):
                        new_meta.units = new_settings[resource][property]
                    else:
                        new_meta.value = new_settings[resource][property]
                    res_obj.metadata[meta_name] = new_meta
            else:
                del res_obj.metadata[meta_name]

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
