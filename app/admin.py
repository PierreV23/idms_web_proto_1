#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 15 10:46:50 2020

@author: wierinve
"""
import json
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
from app.irodssessions import irods_manager

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
        'type' : 'text',
        'help' : 'The resource group that this resource belongs to'
    },
    'group_id': {
        'label': 'ID',
        'meta': 'sys::tiering::group',
        'type': 'number',
        'unit': True,
        'help': 'Unique id within a resource group'
    },
    'copies': {
        'label': 'Copies',
        'meta': 'sys::resource::copies',
        'type': 'number',
        'help': 'The number of copies that this resource provides'
    },
    'cost': {
        'label': 'Cost',
        'meta': 'sys::resource::cost',
        'type': 'number',
        'help': 'Number that indicates cost for storing data on this resource'
    },
    'maxcopies': {
        'label': 'Max copy actions',
        'meta': 'sys::resource::maxcopies',
        'type': 'number',
        'help': 'Maximum number of concurrent tiering actions that will copy data TO this resource'
    },
    'age_before_copy': {
        'label': 'Minimum age before copy (h)',
        'meta': 'sys::resource::min_age_before_copy',
        'type': 'number',
        'factor': 3600,
        'help': 'Data has to have this age before it will be copied to this resource'
    },
    'age_before_trim': {
        'label': 'Minimum age before trim (h)',
        'meta': 'sys::resource::min_age_before_trim',
        'type': 'number',
        'factor': 3600,
        'help': 'Data has to have this age before it will be removed from this resource'
    },
    'minfree': {
        'label': 'Minimum free space (GB)',
        'meta': 'sys::resource::spacelimit',
        'type': 'text',
        'factor': 1000000000,
        'help': 'No data will be copied (by tiering) to this resource once this limit is exceeded'
    },
    'targetfree': {
        'label': 'Target free space (GB)',
        'meta': 'sys::resource::spacetarget',
        'type': 'number',
        'factor': 1000000000,
        'help': 'Tiering process will remove data from this resource once this limit is exceeded'
    },
    'local': {
        'label': 'Local',
        'meta': 'sys::resource::local',
        'type': 'bool',
        'help': 'This resource is on-site'
    },
    'online': {
        'label': 'Online',
        'meta': 'sys::resource::online',
        'type': 'bool',
        'help': 'Data on this resoucre can be accessed directly'
    },
    'stage': {
        'label': 'Stage',
        'meta': 'sys::resource::stage',
        'type': 'bool',
        'help': 'Data is copied to this resource before a pipeline starts'
    },
    'keep': {
        'label': 'Keep',
        'meta': 'sys::resource::keep',
        'type': 'bool',
        'help': 'Once data is on this resource, it will not be removed (except when "local" is required)'
    },
    'surf': {
        'label': 'SURF',
        'meta': 'sys::resource::surf',
        'type': 'bool',
        'help': 'This resource is at SURF. Special dm functions will be used'
    },
    'tar': {
        'label': 'TAR',
        'meta': 'sys::resource::tar',
        'type': 'bool',
        'help': 'Datasets are archived in a TAR file before being moved to this resource'
    },
    'manifest': {
        'label': 'MANIFEST',
        'meta': 'sys::resource::manifest',
        'type': 'bool',
        'help': 'TAR manifest files are stored on this resource'
    },
    'available': {
        'label': 'Available',
        'meta': 'sys::resource::available',
        'type': 'bool',
        'help': 'This resource is found to be available by the automatic resource test script'
    },
    'enabled': {
        'label': 'Enabled',
        'meta': 'sys::resource::enabled',
        'type': 'bool',
        'help': 'This resource can be used'
    }
}


@bp.route('/_issues')
def query_issues():
    if not current_user.is_admin:
        return('<TR><TD COLSPAN=3>Access denied</TD></TR>')
    data = ''
    with irods_manager.session(name='issues') as session:
        query = SpecificQuery(session(name='issues'), alias='checksums_differ')
        for result in query:
            base, name = os.path.split(result[0])
            data = '{}<TR><TD COLSPAN=5><A HREF="{}?path={}">{}</A></TD></TR>'.format(data, url_for("collbrowser.collbrowser"), base, result[0])
            q = session(name='issue_obj').query(DataObject.path,
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

@bp.route('/_consistency')
def data_consistency():
    # Handy to have the resource hosts in the table:
    with irods_manager.session() as session:
        query = session.query(Resource)
        resources = { r[Resource.name]: r[Resource.location] for r in query }
        query = session.query(Collection.name, CollectionMeta.name, CollectionMeta.value).filter(
            Criterion('like', CollectionMeta.name, 'sys::consistency::%::errors'))
        results = [ 
            { 'collection': r[Collection.name],
            'collink'   : datafield('collection', r[Collection.name], 'irods_collection').htmlstring,
            'resource'  : r[CollectionMeta.name].split('::')[2],
            'location'  : resources.get(r[CollectionMeta.name].split('::')[2], 'UNKNOWN'),
            'issues'    : r[CollectionMeta.value]
            } for r in query ]
    return jsonify(results)

@bp.route('/_condetails', methods=["GET"])
def consistency_details():
    collection = request.args.get('collection')
    resource = request.args.get('resource')
    attr = f'sys::consistency::{resource}'
    criteria = [
        Criterion('=', Collection.name, collection),
        Criterion('like', Collection.name, f'{collection}/%')
    ]

    data = []
    if collection:
        for criterium in criteria:
            with irods_manager.session() as session:
                q = session.query(Collection.name, DataObject.name, DataObject.path, DataObjectMeta.value).filter(criterium).filter(
                    Criterion('=', DataObjectMeta.name, attr)).filter(
                    Criterion('=', DataObject.resource_name, resource)
                    )
                for r in q:
                    data.append({
                        'dataobject': os.path.relpath(os.path.join(r[Collection.name], r[DataObject.name]), start=collection),
                        'path': r[DataObject.path],
                        'error': r[DataObjectMeta.value]
                    })

    columns = [
        { "field": "dataobject", "title": "DataObject", "sortable": True },
        { "field": "path", "title": "Path", "sortable": True },
        { "field": "error", "title": "Error", "sortable": False }
    ]
    data = {
        'columnsJSON': json.dumps(columns),
        'dataJSON': json.dumps(data),
        'id': collection.replace('/', '_')
    }
    return render_template('bootstraptable.html', data=data)

@bp.route('/issues')
@login_required
def issues():
    return render_template('issues.html')

@bp.route('/_aract', methods=['POST'])
def archive_action():
    requestdata = request.form.to_dict()
    action = requestdata.get('action')
    collection = requestdata.get('collection')
    session = irods_manager.session()
    try:
        collobj = session.collections.get(collection)
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
                session.data_objects.unlink(filename)
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
    with irods_manager.session() as session:
        query = session.query(Collection.name, CollectionMeta.value).filter(
            Criterion('=', CollectionMeta.name, ATTR_ARCHIVE_STATUS)).filter(
            Criterion('!=', CollectionMeta.value, 'OK'))
        items = []
        for result in query:
            statusmsg = ""
            coll = session.collections.get(result[Collection.name])
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
    session = irods_manager.session()
    for q in ['incoming', 'depends', 'prepare', 'stage', 'queued', 'startup', 'active', 'finishing', 'postprocessing', 'waiting']:
        enabled = True
        path = f'/{current_user.irods_zone}/system/runsheet'
        metaquery = session.query(CollectionMeta.value).filter(
            Criterion('=', Collection.name, path)).filter(
            Criterion('=', CollectionMeta.name, f'sys::enable::{q}'))
        for meta in metaquery:
            enabled = meta[CollectionMeta.value] == 'true'
        if q == 'incoming':
            items = session.query(DataObject.id).filter(\
                Criterion('=', Collection.name, '/rivmZone/system/runsheet/processing')).filter(\
                Criterion('=', DataObjectMeta.name, 'sys::runsheet::state')).filter(\
                Criterion('=', DataObjectMeta.value, q)).count(DataObject.id)
            count  = items.execute()[0][DataObject.id]
        else:
            items = session.query(Collection.id).filter(\
                Criterion('=', CollectionMeta.name, 'sys::runsheet::state')).filter(\
                Criterion('=', CollectionMeta.value, q)).count(Collection.id)
            count  = items.execute()[0][Collection.id]
        queues[q] = {'enabled': enabled, 'count': count}
    return render_template('queues.html', queues=queues)

@login_required
@bp.route('/resources')
def resources():
    resources =  {}
    session = irods_manager.session()
    q = session.query(Resource.name)
    for r in q:
        resources[r[Resource.name]] = {}
        resource = session.resources.get(r[Resource.name])
        metadata = resource.metadata.items()
        metanames = [ m.name for m in metadata ]
        for property in RESOURCE_PROPS:
            meta_name = RESOURCE_PROPS[property].get('meta')
            if meta_name:
                if meta_name in metanames:
                    irods_meta = resource.metadata.get_one(meta_name)
                    if RESOURCE_PROPS[property].get('unit', False):
                        value = irods_meta.units
                    else:
                        value = irods_meta.value
                    factor = RESOURCE_PROPS[property].get('factor')
                    if factor:
                        resources[r[Resource.name]][property] = float(value) / factor
                    else:
                        resources[r[Resource.name]][property] = value
    return render_template('resources.html', columns=RESOURCE_PROPS, resources=resources)

@login_required
@bp.route('/_update_resources', methods=['POST'])
def update_resources():
    session = irods_manager.session()
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
        res_obj = session.resources.get(resource)
        for property in RESOURCE_PROPS:
            meta_name = RESOURCE_PROPS[property]['meta']
            if property in new_settings[resource]:
                if new_settings[resource][property]:
                    try:
                        current_meta = res_obj.metadata.get_one(meta_name)
                    except KeyError:
                        current_meta = iRODSMeta(meta_name, '')
                    new_meta = iRODSMeta(meta_name, current_meta.value, current_meta.units)
                    new_value = new_settings[resource][property]
                    if RESOURCE_PROPS[property].get('factor'):
                        new_value = str(int(float(new_value) * RESOURCE_PROPS[property].get('factor') // 1))
                    if RESOURCE_PROPS[property].get('unit', False):
                        new_meta.units = new_value
                    else:
                        new_meta.value = new_value
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
        with irods_manager.session() as session:
            collobj = session.collections.get(coll)
            collobj.metadata[new_meta.name] = new_meta

    return redirect(url_for('admin.admin'))
