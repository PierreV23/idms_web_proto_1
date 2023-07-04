#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 10:54:56 2019

@author: wierinve
"""

import base64
import logging
import os
import time
import logging
from datetime import datetime, timezone
from turtle import down
from dateutil.relativedelta import relativedelta
from flask import Blueprint, render_template, redirect, request, url_for, jsonify, make_response, flash, current_app
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject, DataObjectMeta
from irods.exception import CAT_NO_ROWS_FOUND, CAT_NO_ACCESS_PERMISSION
from irods.column import Criterion
from app.datafield import AVU2data, datafield
from app.irods_helper import getmetaitem
from app.irodssessions import irods_manager
from graphviz import Digraph
from irods.meta import iRODSMeta
from urllib.parse import urlparse
from . import projects
from . import iqry
from . import irods_objects
from .flaskcache import cache, key_zone, key_userzone, dep_zone, dep_userzone
import json
from app.constants import COLL_KEY_MAP, DATA_KEY_MAP, ATTR_RESOURCE_ONLINE
from . import constants

bp = Blueprint('collbrowser', __name__, url_prefix='/collbrowser')

NAME_LENGTH = 20
DEFAULT_GRAPH_LEVELS = 3

ATTR_DATASETID = 'sys::dataset_id'
ATTR_PROJECTID = 'projectID'
ATTR_PROCESSID = 'processID'
ATTR_PROCESSGROUPID = 'processgroupID'
ATTR_USER_STATE = 'user::data::state'
ATTR_SYS_STATE = 'sys::data::state'
ATTR_RUNSHEET_PROCESSGROUPGUID = 'sys::runsheet::processgroupid'
ATTR_RUNSHEET_STATE = 'sys::runsheet::state'
ATTR_RUNSHEET_ID = 'sys::runsheet::id'

#TODO: use constants.py (role irods_cronjobs)
ATTR_ARCHIVE_PREFIX = 'sys::archive::'
ATTR_PIPELINE_PREFIX = 'sys::pipeline::'
ATTR_PIPELINE_INPUT_COLLECTION_ID = f'{ATTR_PIPELINE_PREFIX}input_collection_id'
ATTR_ARCHIVE_USR_PREFIX = 'user::archive::'
ATTR_ARCHIVE_ENABLE = f'{ATTR_ARCHIVE_PREFIX}enable'
ATTR_ARCHIVE_DESIREDSTATE = f'{ATTR_ARCHIVE_PREFIX}desired_state'
ATTR_ARCHIVE_KEEP_ONLINE = f'{ATTR_ARCHIVE_PREFIX}keep_online'
ATTR_ARCHIVE_KEEP_ONLINE_TILL = f'{ATTR_ARCHIVE_USR_PREFIX}keep_online_till'
ATTR_ARCHIVE_LOCAL = f'{ATTR_ARCHIVE_PREFIX}local'
ATTR_PROCESSREQUEST = 'processrequest'
ATTR_ARCHIVE_STATE = f'{ATTR_ARCHIVE_PREFIX}state'
ATTR_ARCHIVE_MINCOPIES = f'{ATTR_ARCHIVE_PREFIX}min_copies'


COLL_KEY_MAP = {
    'displayname': Collection.name,
    'create_time': Collection.create_time,
    'size': Collection.name, # Collections do not have a size property
    'owner_name': Collection.owner_name
}

DATA_KEY_MAP = {
    'displayname': DataObject.name,
    'create_time': DataObject.create_time,
    'size': DataObject.size,
    'owner_name': DataObject.owner_name
}

PROCESS_SHAPE = 'cds'

# CACHE CONTROL FUNCTIONS
def contents_changed():
    '''Function should be called if collection contents change
    to invalidate cache entries
    '''
    cache.delete_memoized(_collcontents)

def collections_changed(path=None):
    '''Invalidates cache entries for collections and graph
    Should be called when collection structure or metadata changes and
    immediate representation of changes in the interface is required 
    '''
    args = [path] if path else []
    cache.delete_memoized(_generate_graph)
    cache.delete_memoized(add_items)
    cache.delete_memoized(subitems, *args)
    cache.delete_memoized(_generate_graph)

# TODO: use the irods_helper instead (role irods_cronjobs)

@bp.route('_propagate', methods=['POST'])
@login_required
def propagateDownstreamInvalid():
    irods_coll = request.form.get('collection', '/', type=str)
    try:
        downstream_collections = _propagateDownstreamInvalid(irods_coll, irods_coll)
    except Exception as e:
        logging.error(f"Propagation of user invalid state from {irods_coll} failed: {e}")
        response =  make_response(
            'Propagation unsuccessful',
            500,
        )
        return response
    logging.info(f"Propagated user invalid state from {irods_coll} to {downstream_collections} successfully.")
    response =  make_response(
        'Propagation successful',
        200,
    )
    # Invalidate the cache for the next call to the graph function
    collections_changed()
    return response

def _propagateDownstreamInvalid(base_irods_coll, irods_coll):
    iqry.scollmetaval(irods_coll, ATTR_USER_STATE, "invalid")
    logging.info(f"Invalid state propagated from {base_irods_coll} to {irods_coll}")

    irods_coll_id = iqry.qcollmetadict(irods_coll)[ATTR_DATASETID]
    next_collections = [c[Collection.name] for c in iqry.qcollbymeta(ATTR_PIPELINE_INPUT_COLLECTION_ID, irods_coll_id)]

    downstream_collections = [irods_coll]
    for coll in next_collections:
        downstream_collections += _propagateDownstreamInvalid(base_irods_coll, coll)
    return downstream_collections

def getmetatree(irods_coll, attr, default=None):
    return  _getmetatree(irods_coll, attr, irods_coll, default=None)

@login_required
def _getmetatree(irods_coll, attr, base, default=None):
    value = iqry.qcollmetaval(irods_coll, attr)
    if value is not None:
        return value, datafield('collection', irods_coll, 'irods_collection'), irods_coll == base
    if irods_coll != '/':
        parent = os.path.dirname(irods_coll)
        return _getmetatree(parent, attr, base, default=None)
    return default, None, True

@bp.route('_meta')
@login_required
def coll_meta():
    path = request.args.get('path','/', type=str)
    selected_object = request.args.get('object', '', type=str)

# Query for collection metadata
    coll_avu = []
    query = iqry.qcollmeta(path)
    for coll_metadata in query:
        name = coll_metadata[CollectionMeta.name]
        value = coll_metadata[CollectionMeta.value]
        units = coll_metadata[CollectionMeta.units]
        coll_avu.append(AVU2data(name, value, units))

# Query for object metadata
    object_avu = None
    if selected_object:
        object_avu = []
        with irods_manager.session() as session:
            query = session.query(DataObjectMeta.name, DataObjectMeta.value,
                                        DataObjectMeta.units).filter(
                                            Criterion('=', Collection.name, path)).filter(
                                            Criterion('=', DataObject.name, selected_object)
                                        )
            for object_metadata in query:
                name = object_metadata[DataObjectMeta.name]
                value = object_metadata[DataObjectMeta.value]
                units = object_metadata[DataObjectMeta.units]
                object_avu.append(AVU2data(name, value, units))
    return render_template('metadata.html', coll_avu=coll_avu, object_avu=object_avu)

@bp.route('_setKeepOnlineUntil', methods=['GET'])
@login_required
def setKeepOnlineUntil():
    irods_session = irods_manager.session()

    selectionStr = request.args.get('selection','None', type=str)
    collection = request.args.get('collection','None', type=str)

    now = datetime.today()
    days = 0
    try:
        days = int(selectionStr)
    except ValueError:
        logging.warning( f"unknown selection for _setKeepOnlineUntil: {selectionStr}")
        return('DONE')
    keepOnlineUntil = now + relativedelta(days=days)

    iqry.scollmetaval(collection, ATTR_ARCHIVE_KEEP_ONLINE_TILL, str(int(datetime.timestamp(keepOnlineUntil))), 'timestamp')
    return('DONE')


@bp.route('_setmeta', methods=['GET'])
@login_required
def setmeta():
    attr = request.args.get('attr')
    value = request.args.get('value')
    collection = request.args.get('collection')
    if attr and value and collection:
        iqry.scollmetaval(collection, attr, value)
    return('DONE')


@bp.route('_setoverride', methods=['GET'])
@login_required
def setoverride():
    attr = request.args.get('attr')
    value = request.args.get('value')
    overrideStr = request.args.get('override','false', type=str)
    collection = request.args.get('collection')
    if attr and value and collection:
        if overrideStr not in ['true', 'false']:
            logging.warning( f"unknown selection for _setKeepLocal: {overrideStr}" )
            return('DONE')
        try:
            if overrideStr == 'false':
                iqry.rmallcollmetaattr(collection, attr)
            else:
                iqry.scollmetaval(collection, attr, value)
        except CAT_NO_ACCESS_PERMISSION:
            return 'ACCESS DENIED', 401
    # Invalidate the cache for the next call to the graph function
    collections_changed(path=collection)
    return 'DONE', 200


@bp.route('_actions')
def coll_actions():
    path = request.args.get('path','/', type=str)
    coll_name = path.split('/')[-1]

    tiers = irods_objects.Tierlist('default')

    is_dataset = iqry.qcollmetavalstatic(path, ATTR_DATASETID, "") != ""
    keep_local = getmetatree(path, ATTR_ARCHIVE_LOCAL, False)
    state = irods_objects.iState(tiers, iqry.qcollmetaval(path, ATTR_ARCHIVE_STATE, "000"))
    desired_state = irods_objects.iState(tiers, iqry.qcollmetaval(path, ATTR_ARCHIVE_DESIREDSTATE, "000"))
    min_copies = getmetatree(path, ATTR_ARCHIVE_MINCOPIES, 2)
    keep_online = getmetatree(path, ATTR_ARCHIVE_KEEP_ONLINE, "false")
    keep_online_time = float(iqry.qcollmetaval(path, ATTR_ARCHIVE_KEEP_ONLINE_TILL, default=0))
    if keep_online_time < time.time():
        keep_online_time = 0
    keep_online_till = datafield('keep_online', keep_online_time, 'timestamp')

    # TODO: This should use the sys::resource::online property of a resource to determine
    # if a collection is online
    is_offline = not state.tag_present(ATTR_RESOURCE_ONLINE)
      
    # define status:
    # OFFLINE
    # RETRIEVE_REQUEST
    # RETRIEVE_IN_PROGRESS
    # ONLINE
    #
    if not is_offline:
        status = 'ONLINE'
    elif state != desired_state and desired_state.tag_present(ATTR_RESOURCE_ONLINE):
        status = 'RETRIEVE_IN_PROGRESS'
    elif keep_online_time:
        status = 'RETRIEVE_REQUESTED'
    else:
        status = 'OFFLINE'

    projectid = iqry.qcollmetavalstatic(path, ATTR_PROJECTID, "")
    processid = iqry.qcollmetaval(path, ATTR_PROCESSID, "")
    processgroupid = iqry.qcollmetaval(path, ATTR_PROCESSGROUPID, "")
    processes = projects.get_processlist(projectid)
    processgroups = projects.get_processgrouplist(projectid)
    processrequest = iqry.qcollmetaval(path, ATTR_PROCESSREQUEST, "false")
    myprocessgroupguid = iqry.qcollmetaval(path, ATTR_RUNSHEET_PROCESSGROUPGUID, "")
    myrunsheetid = iqry.qcollmetaval(path, ATTR_RUNSHEET_ID, "")

    # Try to detect if this collection is part of a failed/incomplete processgroup
    # This is true if one of the processes in the group has state NOTRUN
    active_pg = False
    failed_pg = False
    if myprocessgroupguid:
        colls = iqry.qcollbymeta(ATTR_RUNSHEET_PROCESSGROUPGUID, myprocessgroupguid)
        for coll in colls:
            runsheet_state = iqry.qcollmetaval(coll[Collection.name], ATTR_RUNSHEET_STATE, 'OK')
            if runsheet_state == 'notrun':
                failed_pg = True
            if runsheet_state not in ['done', 'error', 'notrun']:
                active_pg = True

    archival_state = {
        "complete": iqry.qcollmetaval(path, "complete", "false"),
        "enabled": iqry.qcollmetaval(path, ATTR_ARCHIVE_ENABLE, "false"),
        "is_dataset": is_dataset,
        "is_offline": is_offline,
        "keep_local": keep_local,
        "status": status,
        "min_copies": min_copies,
        "keep_online": keep_online,
        "keep_online_till": keep_online_till,
        "active_pg": active_pg,
        "failed_pg": failed_pg,
        "runsheetid": datafield('runsheetid', myrunsheetid, 'runsheet'),
        "processgroupguid": myprocessgroupguid
    }

    user_coll_state = iqry.qcollmetaval(path, ATTR_USER_STATE, "")
    sys_coll_state = iqry.qcollmetaval(path, ATTR_SYS_STATE, "")

    state_metadata = {
        "user": user_coll_state,
        "sys": sys_coll_state,
    }

    return render_template('actions.html', collection=path, 
        name=coll_name, archival_state=archival_state, state_metadata=state_metadata,
        processes=processes, processid=processid, processrequest=processrequest,
        processgroups=processgroups, processgroupid=processgroupid,
        admin=current_user.is_admin)


@bp.route('_startprocess')
@login_required
def startprocess():
    collection = request.args.get('collection')

    processid = request.args.get('processid')
    processgroupid = request.args.get('processgroupid')
    processgroupguid = request.args.get('processgroupguid')
    if processid:
        iqry.scollmetaval(collection, ATTR_PROCESSID, processid)
        iqry.scollmetaval(collection, ATTR_PROCESSREQUEST, current_user.username)
    elif processgroupid:
        iqry.rmallcollmetaattr(collection, ATTR_PROCESSID)
        iqry.scollmetaval(collection, ATTR_PROCESSGROUPID, processgroupid)
        iqry.scollmetaval(collection, ATTR_PROCESSREQUEST, current_user.username)
    elif processgroupguid:
        # Restart all NOTRUN tasks of current processgroup
        pg_collections = iqry.qcollbymeta(ATTR_RUNSHEET_PROCESSGROUPGUID, processgroupguid)
        for coll in pg_collections:
            if iqry.qcollmetaval(coll[Collection.name], ATTR_RUNSHEET_STATE) == 'notrun':
                iqry.scollmetaval(coll[Collection.name], ATTR_RUNSHEET_STATE, 'depends')
        flash('RESTART', 'action_panel')
    else:
        return 'FAILED'
    return 'DONE'

@bp.route('_collist')
@login_required
def collist():
    path = request.args.get('path','/', type=str)
    display_field = iqry.qcollmetaval(path, 'ngsweb::display_field')
    refresh = request.args.get('refresh', 0, type=int)
    if refresh:
        contents_changed()   
    options = {
        'download_btn': request.args.get('download_btn', 'true', type=str) == 'true',
        'view_btn': request.args.get('view_btn', 'true', type=str) == 'true',
        'delete_btn': request.args.get('delete_btn', 'false', type=str) == 'true'
    }
    return render_template('colltable.html', path=path, display_field=display_field, options=options)

@bp.route('collcontents')
def collcontents():
    path = request.args.get('path','/', type=str)
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 999, type=int)
    filterstr = request.args.get('filter', '{}')
    order = request.args.get('order')  
    key = request.args.get('sort')
    return _collcontents(path, offset, limit, filterstr, key, order)

# We use dep_userzone here to prevent performance degradation
# when a user uses the upload facility (and invalidates the cache in that way)
@cache.memoize(timeout=60, make_name=dep_userzone)
def _collcontents(path, offset, limit, filterstr, key, order):
    irods_session = irods_manager.session()

# Look for metadate attrs starting with ngsweb:: on the collection
    q1 = iqry.qcollmeta(path)
    display_settings = { m[CollectionMeta.name][8:] : m[CollectionMeta.value] for m in q1 if m[CollectionMeta.name].startswith('ngsweb::') }

    display_field = display_settings.get('display_field', '')
    sortkey = key if key else display_settings.get('sort_order', 'displayname')
    stored_sort_order = 'desc' if display_settings.get('sort_reverse', 'false') == 'true' else 'asc'
    sort_order = order if order else stored_sort_order

    c_sortkey = COLL_KEY_MAP.get(sortkey, 'displayname')
    d_sortkey = DATA_KEY_MAP.get(sortkey, 'displayname')
  
# Create collection and data filters
    filters = json.loads(filterstr)
    qc_filters = [Criterion('=', Collection.parent_name, path)]
    qd_filters = [Criterion('=', Collection.name, path)]
    if 'displayname' in filters:
        qc_filters.append(Criterion('like', Collection.name, f'%{filters["displayname"]}%'))
        qd_filters.append(Criterion('like', DataObject.name, f'%{filters["displayname"]}%'))

# Get item counts 
    qc_count = irods_session.query(Collection.id)
    for qc_filter in qc_filters:
        qc_count = qc_count.filter(qc_filter)
    coll_count = next(qc_count.count(Collection.id).get_results())[Collection.id]

    qd_count = irods_session.query(DataObject.id)
    for qd_filter in qd_filters:
        qd_count = qd_count.filter(qd_filter)
    data_count = len(list(qd_count))

# Determine offset and limits
    min_coll = min(offset, coll_count)
    max_coll = min(offset + limit, coll_count)
    min_data = min(max(offset - coll_count, 0), data_count)
    max_data = min(max(offset + limit - coll_count, 0), data_count)

    results = { 'total': coll_count + data_count , 'rows': []}
# Query for collection subcollections

    if min_coll < max_coll:
        q1 = irods_session.query(Collection)
        for qc_filter in qc_filters:
            q1 = q1.filter(qc_filter)
        q1 = q1.order_by(c_sortkey, order=sort_order).offset(offset).limit(limit)
        try:
            colls = q1.execute()
            for coll in colls:
                objdict = { 
                    'displayname': datafield('irods_collection', coll[Collection.name], 'irods_collection').collentry,
                    'path': coll[Collection.name],
                    'object': 'collection',
                    'size': 'DIR',
                    'create_time': datafield('create_time', coll[Collection.create_time], 'timestamp').htmlstring,
                    'owner_name': coll[Collection.owner_name]
                }
                objdict['type'] = iqry.qcollmetaval(coll[Collection.name], 'sys::data::type', default='')
                objdict['state'] = iqry.qcollmetaval(coll[Collection.name], 'sys::data::state', default='')
                if objdict['state'] != 'valid':
                    objdict['tableclass'] = constants.LAYOUT.get(objdict['state'], constants.DEFAULT_SHAPE)['tableclass']
                else:
                    objdict['tableclass'] = constants.LAYOUT.get(objdict['type'], constants.DEFAULT_SHAPE)['tableclass']
                objdict['display_field'] = iqry.qcollmetaval(coll[Collection.name], display_field, default='')
                results['rows'].append(objdict)
        except CAT_NO_ROWS_FOUND:
            pass

# Query irods for dataobjects
    if min_data < max_data:
        qd = irods_session.query(DataObject.name, DataObject.create_time, DataObject.size, DataObject.owner_name)
        for qd_filter in qd_filters:
            qd = qd.filter(qd_filter)
        qd = qd.min(DataObject.create_time)
        qd = qd.order_by(d_sortkey, order=sort_order).offset(min_data).limit(max_data - min_data)      
        try:
            dataobjects = qd.execute()
            for do in dataobjects:
                objdict = { 
                    'displayname': do[DataObject.name],
                    'object': 'dataobject',
                    'path': os.path.join(path, do[DataObject.name]),
                    'size': do[DataObject.size],
                    'create_time': datafield('create_time', do[DataObject.create_time], 'timestamp').htmlstring,
                    'owner_name': do[DataObject.owner_name]
                }
                results['rows'].append(objdict)
        except CAT_NO_ROWS_FOUND:
            pass
    return jsonify(results)


def shortname(name,l):
    s = name
    if len(name)>l:
        s = '...' + name[-l+4:]
    return s


def coll_shape(coll_type):
    layout = constants.LAYOUT.get(coll_type, constants.DEFAULT_SHAPE)
    return layout[constants.SHAPE1], layout[constants.COLOR1]

class Dictlist(dict):
    """ Custom dict class that allos storing multiple values under one key
    get method will return fisrt value, so can be used as in-place dict replacement
    get_all returns a list of all values
    """
    def __setitem__(self, key, value):
        if not key in self:
            super(Dictlist, self).__setitem__(key, [])
        self[key].append(value)

    def get(self, key, default=None):
        if key in self:
            return self[key][0]
        return default

    def get_all(self, key, default=None):
        if key in self:
            return self[key]
        return default

@bp.route('_related')
def multi_list():
    # Create a small HTML page with a list of related collections
    # 
    PARAMSETS = {
        'U':[
            ('user::pipeline::input_collection', True),
            ('user::pipeline::input_collection_id', False)
        ],
        'S':[
            ('sys::pipeline::input_collection_id', False)
        ]
    }
    # param has format
    # q = IU|IS|OU|OS
    # collection = collection
    query_type = request.args.get('q', 'OS')
    coll = request.args.get('collection')
    forward = query_type[0] == 'O'
    params = PARAMSETS.get(query_type[1], ())
    resultnames = []
    for attr, byname in params:
        resultnames += related(coll, attr, forward=forward, byname=byname)
    results = [ (iqry.qcollmetaval(r, ATTR_PROJECTID, default=''), datafield('coll', r, 'irods_collection')) for r in resultnames ]
    return render_template('small_collist.html', results = results)

def related(coll, attr, forward=True, byname=True):
    # Find collections related to <coll> 
    # In case forward=True
    #   Search for collections that have metadata attribute <attr> with the name or dataset_id of coll in the value
    # In case forward=False
    #   Search for collections that have a name or datasetid equal to the value of <attr> on <coll>
    
    # Find metadata of <coll>
    collmeta = Dictlist()
    q = iqry.qcollmeta(coll)
    for m in q:
        collmeta[m[CollectionMeta.name]] = m[CollectionMeta.value]
    
    if forward:
        search_value = coll if byname else collmeta.get(ATTR_DATASETID)
        q = iqry.qcollbymeta(attr, search_value)
        result = { c[Collection.name] for c in q }
    else:
        if byname:
            result = set(collmeta.get_all(attr, []))
        else:
            result = set()
            values =  collmeta.get_all(attr, [])
            for value in values:
                q = iqry.qcollbymeta(ATTR_DATASETID, value)
                result.update([ c[Collection.name] for c in q ])
    return result


@bp.route('/_graph')
@login_required
def generate_graph():
    coll = request.args.get('path', '/', type=str)
    maxlevels = request.args.get('levels', DEFAULT_GRAPH_LEVELS, type=int)
    graph_simplify = request.args.get('graph_simplify', 0, type=int)
    return _generate_graph(coll, maxlevels, graph_simplify)


@cache.memoize(timeout=60, make_name=dep_userzone)
def _generate_graph(coll, maxlevels, graph_simplify):

    multinodes = []
    nodes = set()
    processes = set()
    edges = set()
    dashed_edges = set()
    multi_edges = set()

    def destnode(node):
        # Determine if destination node is a collection node, 
        # or the associated process node
        if node in processes:
            return f'G-{node}'
        else:
            return node

    def traverse(coll, levels=DEFAULT_GRAPH_LEVELS):
        if coll in nodes:
            return

        nodes.add(coll)

        MAX_INPUTS = current_app.config.get('GRAPH_MAX_INPUTS', 3)
        MAX_OUTPUTS = current_app.config.get('GRAPH_MAX_OUTPUTS', 11)

        def handle_neighbours(node, neighbours, edgelist, levels, inputs=True, relation_type='S'):
            multi = False
            if graph_simplify:
                max_nodes = MAX_INPUTS if inputs else MAX_OUTPUTS
                max_nodes -= (maxlevels - levels) * 1
                prefix = 'I' if inputs else 'O'
                if len(neighbours) > max_nodes and len(neighbours) > 1:
                    multi = True
                    label = f'{prefix}{relation_type}-{node}'
                    multinodes.append((label, node, neighbours))
                    if inputs:
                        multi_edges.add((label, node))
                    else:
                        multi_edges.add((node, label))
            for neighbour in neighbours:
                if inputs:
                    vect = (neighbour, node)
                else:
                    vect = (node, neighbour)
                if not multi:
                    if levels:
                        traverse(neighbour, levels=levels-1)
                        edgelist.add(vect)
                    else:
                        dashed_edges.add(vect)
                elif neighbour in nodes:
                    edgelist.add(vect)            

        # FIND INPUTS
        input_colls = related(coll, 'sys::pipeline::input_collection_id', forward=False, byname=False)
        handle_neighbours(coll, input_colls, edges, levels, inputs=True)

        # FIND  OUTPUTS
        output_colls = related(coll, 'sys::pipeline::input_collection_id', forward=True, byname=False)
        handle_neighbours(coll, output_colls, edges, levels, inputs=False)

        # FIND EXTRA INPUTS
        extra_colls = set(related(coll, 'user::pipeline::input_collection', forward=False, byname=True))
        extra_colls |= set(related(coll, 'user::pipeline::input_collection_id', forward=False, byname=False))
        handle_neighbours(coll, extra_colls, dashed_edges, levels, inputs=True, relation_type='U')

        # FIND EXTRA OUTPUTS
        ref_colls = set(related(coll, 'user::pipeline::input_collection', forward=True, byname=True))
        ref_colls |= set(related(coll, 'user::pipeline::input_collection_id', forward=True, byname=False))
        handle_neighbours(coll, ref_colls, dashed_edges, levels, inputs=False, relation_type='U')

    traverse(coll, levels=maxlevels)

    # Remove multinodes when all items in multinode are in the graph
    # and combine equal multinodes
    for n, (multinode, related_node, neighbours) in reversed(list(enumerate(multinodes))):
        input_node = multinode[0] == 'I'
        if set(neighbours).issubset(nodes):
            # Remove the multinode and the edge
            if input_node:
                vect = (multinode, related_node)
            else:
                vect = (related_node, multinode)
            for neighbour in neighbours:
                if input_node:
                    edges.add((neighbour, related_node))
                else:
                    edges.add((related_node, neighbour))
            # Remove the multinode and the edge
            multi_edges.remove(vect)
            del multinodes[n]
        else:
            # Combine equal multinodes:
            for other_multinode, _ , other_neighbours in multinodes[:n]:
                if other_neighbours == neighbours:
                    # Move the edges:
                    if input_node:
                        vect = (multinode, related_node)
                        new_vect = (other_multinode, related_node)
                    else:
                        vect = (related_node, multinode)
                        new_vect = (related_node, other_multinode)
                    multi_edges.remove(vect)
                    multi_edges.add(new_vect)
                    del multinodes[n]
                    break


    #######################################
    # Draw the graph

    graph = Digraph('datagraph')
    graph.graph_attr['rankdir'] = 'LR'
    graph.graph_attr['fontsize'] = '15'

    # Start with all the nodes
    for node in nodes:
        collmeta = Dictlist()
        q = iqry.qcollmeta(node)
        for m in q:
            collmeta[m[CollectionMeta.name]] = m[CollectionMeta.value]

        # create the collection graph node
        git = collmeta.get('sys::pipeline::gitrepo')
        githash = collmeta.get('sys::pipeline::githash')
        if git:
            repo_url = urlparse(git)
            # Strip credentials from repo url and add commit hash.
            repo_url = repo_url._replace(netloc=repo_url.hostname)
            link = repo_url._replace(path='{}/tree/{}'.format(repo_url.path.replace('.git', ''), githash))
            processid = f"{collmeta.get('sys::runsheet::processID', '')}\n{git.split('/')[-1]}"
            git_node = f'G-{node}'
            graph.node(git_node, processid, shape=PROCESS_SHAPE, URL=link.geturl(), fontsize='8')
            graph.edge(git_node, node)
            processes.add(node)
        coll_type = collmeta.get('sys::runsheet::state', 'unknown')
        coll_type = collmeta.get('sys::data::type', coll_type)
        coll_type = collmeta.get('user::data::type', coll_type)
        shape, shape_color = coll_shape(coll_type)

        # set border/fill colors for invalid collections
        border_color = "black"
        if collmeta.get('sys::data::state') == "invalid":
            # shape_color += f":{constants.SYS_INVALID_COLOR}"
            # shape_color += f";0.9:{constants.SYS_INVALID_COLOR}"
            border_color = constants.SYS_INVALID_COLOR
        elif collmeta.get('user::data::state') == "invalid":
            # shape_color += f":{constants.USER_INVALID_COLOR}"
            # shape_color += f";0.9:{constants.USER_INVALID_COLOR}"
            border_color = constants.USER_INVALID_COLOR
    
        projectid = collmeta.get('projectID', '') + '\n'
        if node == coll:
            penwidth = '3'
            clss = { 'class' : 'path-change center-coll'}
        else:
            penwidth = '1'
            clss = { 'class' : 'path-change' }

        graph.node(node, projectid + shortname(node,NAME_LENGTH), shape=shape, color=border_color, 
            fillcolor=shape_color, style='filled', penwidth=penwidth,
            fontsize='8', setting='extra', **clss, id=node)

    # multi-nodes
    for multinode, related_node, neighbours in multinodes:
        clss = { 'class' : 'collist' }
        graph.node(multinode, '.. multiple ..', shape="rarrow", style='filled', setting='extra', **clss, id=multinode)

    # draw the solid lines
    for s, d in edges:
        graph.edge(s, destnode(d))

    # draw the dashed lines
    dash_counter = 1
    for vt in dashed_edges - edges:
        vect = list(vt)
        for i, v in enumerate(vect):
            if not v in nodes:
                vect[i] = f'NODE{dash_counter}'
                dash_counter += 1
                graph.node(vect[i], '', shape='none', width='0', height='0')
        graph.edge(vect[0], destnode(vect[1]), style='dashed')

    for s, d in multi_edges:
        graph.edge(s, destnode(d), style='dotted')

    return graph.pipe(format='svg').decode('utf-8')

@cache.memoize(timeout=300, make_name=dep_zone)
def subitems(path):
    count = 0
    with irods_manager.session() as session:
        query = session.query(Collection.id).filter(
            Criterion('=',Collection.parent_name, path)).count(Collection.id)
        try:
            for a in query:
                count = a[Collection.id]
        except:
            count = 0
        return count

@cache.memoize(timeout=60, make_name=dep_zone)
def add_items(path, level, active):
           
    result = ''
    parts = active.split('/')
    colls = [ c[Collection.name] for c in iqry.qcollchildren(path)]
    for collpath in colls:
        collname = collpath.split('/')[-1]
        if collname:
            c1=' path-active' if collpath == active else '';
            link='<span class="tree-label path-change{}" data-path="{}">{}</span>'.format(c1, collpath, collname)
            subtree=''
            dummy=0
            if len(parts)>level:
                # Not the whole tree is expanded yet
                if parts[level] == collname:
                    # active path
                    subtree = add_items(os.path.join(path, collname), level + 1, active)
                else:
                    dummy = subitems(os.path.join(path, collname))
            if len(parts)==level:
                dummy = subitems(os.path.join(path, collname))
            if subtree:
                result = '{0}<li><span class="caret caret-down list-open" data-path="{1}" id="TT{1}">{2}</span></li>'.format(result, collpath, link)
            elif dummy:
                result = '{0}<li><span class="caret list-close" data-path="{1}" id="TT{1}">{2}</span></li>'.format(result, collpath, link)
            else:
                result = '{}<li><span class="caret-nosub">{}</span></li>'.format(result, link)
            if subtree:
                result = '{}<ul id="{}">{}</ul>'.format(result, collpath, subtree)
    return(result)
    

@bp.route('/_tree')
@login_required
@cache.cached(timeout=60, key_prefix=key_zone)
def colltree():
    active = request.args.get('active', '', type=str)
    current = request.args.get('root', '/', type=str)
    level = 1
    rs = add_items(current, level, active)
    return('<ul id="{}">{}</ul>'.format(current, rs))


@bp.route('/')
@login_required
def collbrowser():
    path = request.args.get('path', None)
    if path:
        current_user.settings['path'] = path
    else:
        path = current_user.settings.get('path', f'/{current_user.irods_zone}/projects')
    graph_levels = current_user.settings.setdefault('graph_levels', DEFAULT_GRAPH_LEVELS)
    graph_simplify = current_user.settings.setdefault('graph_simplify', 1)

    return render_template('collbrowser.html',  path=path, graph_levels=graph_levels, graph_simplify=graph_simplify)


@bp.route('upload_file', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        requestdata = request.form.to_dict()
        f = request.files['file']
        # Generate irods file object
        iObjName = requestdata['collection'] + '/' + f.filename
        iObj = current_user.ifs.open(iObjName, 'w')
        f.save(iObj)
        iObj.close()
        contents_changed()
    return redirect(url_for('collbrowser.collbrowser') + '?path=' + requestdata['collection'])

@login_required
@bp.route('_deletefile', methods=['POST'])
def delete_file():
    requestdata = request.form.to_dict()
    if 'path' in requestdata:
        path = requestdata['path']
        current_user.ifs.deletefile(path)
        contents_changed()
    return '', 201


@bp.route('search')
def search():
    return render_template('search.html')

OBJECT_TYPES = {
    "collection": (Collection, ),
    "dataset": (Collection, ),
    "dataobject": (DataObject, Collection),
}
DEFAULT_OBJECT_TYPE = "dataset"

def get_projectlist_as_filter():
    project_dict = projects.get_projectlist()
    return {project: props["name"] for project, props in project_dict.items()}

# TODO: Perhaps make one for each OBJECT_TYPE, so that we don't have to build the columns json each time.

# Each column of the search table must be defined here
#  - css_name: name as used in the css of the table, should not contain colons (:).
#  - irods_object: an iRODS model or column. Used in the search Criterion.
#  - meta_name: the name of the metadata field if irods_object=CollectionMeta.name.
#  - default_on: a subset of OBJECT_TYPES. 
#       Indicates whether the columns shown by default when loading the table.
#  - used_for: a subset of OBJECT_TYPES. 
#       Indicates whether the can be made visible in the table for each OBJECT_TYPE.
#  - filter_control: the data-filter-control field of the bootstrap tables for this column. 
#  - filter_data: dict format which is parsed to json in the code.
#       the data-filter-data field of the bootstrap tables for this column. 
#  - sortable: the data-sortable field of the bootstrap tables for this column.
#  - switchable: the data-switchable field of the bootstrap tables for this column.
COLUMNS = {
    "projectID": {
        "css_name": "projectID",
        "irods_object": CollectionMeta.name,
        "meta_name": "projectID",
        "default_on": OBJECT_TYPES,
        "used_for": OBJECT_TYPES,
        "filter_control": "select",
        "filter_data": get_projectlist_as_filter,
        "sortable": False,
        "switchable": False,
    },
    "collection": {
        "irods_object": Collection.name,
        "default_on": OBJECT_TYPES,
        "used_for": OBJECT_TYPES,
        "filter_control": "input",
        "sortable": True,
        "switchable": False,
    },
    "object": {
        "irods_object": DataObject.name,
        "default_on": {"dataobject", },
        "used_for": {"dataobject", },
        "filter_control": "input",
        "sortable": True,
        "switchable": False,
    },
    "sys::data::type": {
        "css_name": "sys--data--type",
        "irods_object": CollectionMeta.name,
        "meta_name": "sys::data::type",
        "default_on": {"collection", "dataset"},
        "used_for": OBJECT_TYPES,
        "filter_control": "select",
        "filter_data": {"valid": "valid" , "temporary": "temporary", "imported": "imported", "invalid": "invalid", "distributed": "distributed", "uploaded": "uploaded"},
        "sortable": False,
    },
    "sys::runsheet::repo": {
        "css_name": "sys--runsheet--repo",
        "irods_object": CollectionMeta.name,
        "meta_name": "sys::runsheet::repo",
        "default_on": set(),
        "used_for": OBJECT_TYPES,
        "filter_control": "input",
        "sortable": False,
    },
    "sys::runsheet::description": {
        "css_name": "sys--runsheet--description",
        "irods_object": CollectionMeta.name,
        "meta_name": "sys::runsheet::description",
        "default_on": set(),
        "used_for": OBJECT_TYPES,
        "filter_control": "input",
        "sortable": False,
    },
    "sys::runsheet::processID": {
        "css_name": "sys--runsheet--processID",
        "irods_object": CollectionMeta.name,
        "meta_name": "sys::runsheet::processID",
        "default_on": set(),
        "used_for": OBJECT_TYPES,
        "filter_control": "input",
        "sortable": False,
    },
    "sys::dataset_id": {
        "css_name": "sys--dataset_id",
        "irods_object": CollectionMeta.name,
        "meta_name": "sys::dataset_id",
        "default_on": set(),
        "used_for": OBJECT_TYPES,
        "filter_control": "input",
        "sortable": False,
    }
}

# The names of the columns are used in the css when filtering, which doesn't handle colons very well
CSS_NAME_TO_COLUMN = {
    props.get("css_name", column): column
    for column, props in COLUMNS.items()
}

def search_result_query(object_type, filter_dict, search_dict):
    irods_session = irods_manager.session()
    query = irods_session.query(*OBJECT_TYPES.get(object_type, (Collection, )))

    # initial search
    SEARCH_PATTERN = '%{}%'
    SEARCH_OPTION = 'like'
    if search_dict["useExactMatch"] == 'True':
        SEARCH_PATTERN = '{}'
        SEARCH_OPTION = '='

    SEARCH_IN_OPTIONS = {
        "collection_metadata": CollectionMeta.value,
        "collection_name": Collection.name,
        "object_name": DataObject.name,
    }
    SEARCH_IN_DEFAULT = Collection.name

    if search_dict["searchtext"]:
        search_in_type = search_dict.get("searchIn")
        if search_in_type == "collection_metadata":
            # To reliably search for metadata values in all metadata fields, iRODS still needs the field to be 'specified'.
            query = query.filter(Criterion(
                "like",
                CollectionMeta.name,
                "%")
            )
        query = query.filter(Criterion(
            SEARCH_OPTION,
            SEARCH_IN_OPTIONS.get(search_in_type, SEARCH_IN_DEFAULT),
            SEARCH_PATTERN.format(search_dict["searchtext"])
        ))

    # filter by columns.

    # Searching for datasets by checking if the collection has a sys::dataset_id metadata field.
    if object_type == "dataset" and "sys::dataset_id" not in filter_dict:
        filter_dict["sys::dataset_id"] = ""

    for name, value in filter_dict.items():
        if "meta_name" in COLUMNS[name]:
            query = query.filter(CollectionMeta.name == COLUMNS[name]["meta_name"]).filter(Criterion( "like", CollectionMeta.value, '%{}%'.format(value)))
            continue
        query = query.filter(Criterion( "like", COLUMNS[name]["irods_object"], '%{}%'.format(value)))
    return query

def search_result_count(object_type, filter_dict, search_dict, searchId):
    @cache.memoize(timeout=120, make_name=dep_zone)
    def _search_result_count(object_type, filter_dict, search_dict):
        logging.debug(f"Search {searchId}: Calculating count")
        query = search_result_query(object_type, filter_dict, search_dict)
        count = len(list(query)) 
        logging.debug(f"Search {searchId}: Calculating count DONE; found {count} objects")
        return count
    return _search_result_count(object_type, filter_dict, search_dict)

@bp.route('_search/<object_type>/', methods=['GET'])
@login_required
def search_result(object_type):
    limit = request.args.get('limit', -1, type=int)
    offset = request.args.get('offset', 0, type=int)
    sort = request.args.get('sort', "", type=str)
    order = request.args.get('order', "", type=str)
    filter = request.args.get('filter', "{}", type=str)
    searchId = request.args.get('searchId', "", type=str)

    search_dict = {
        "searchIn": request.args.get('searchIn', "", type=str),
        "useExactMatch": request.args.get('useExactMatch', "", type=str),
        "searchtext": request.args.get('searchtext', "", type=str),
    }

    if object_type not in OBJECT_TYPES:
        logging.error(f"Search {searchId}: non-existent object type {object_type}, using {DEFAULT_OBJECT_TYPE} instead")
        object_type = DEFAULT_OBJECT_TYPE

    filter_dict = json.loads(filter)
    # Change the column names as used in the css to the column names as used in iRODS
    # Necessary because CSS doesn't handle the colons in the column names very well 
    filter_dict = {
        CSS_NAME_TO_COLUMN[key]: value
        for key, value in filter_dict.items()
    }

    logging.info(f"Search {searchId}: object_type='{object_type}', search={search_dict} and filters={filter_dict}.")
    query = search_result_query(object_type, filter_dict, search_dict)
    count = search_result_count(object_type, filter_dict, search_dict, searchId)

    # Execute paginated query and parse for use in bootstrap tables
    query = query.limit(limit).offset(offset)
    # TODO sort (and limit/offset) by metadata by getting the complete query results and sorting manually
    if sort:
        query = query.order_by(COLUMNS[sort]["irods_object"], order=order)

    logging.debug(f"Search {searchId}: Retrieving column values")
    rows = []
    for obj in query.execute():
        row = dict()
        obj_meta = iqry.qcollmetadict(obj[Collection.name])
        for col, props in COLUMNS.items():
            if "meta_name" in props:
                # Use the iRODS name instead of the CSS name of the column
                row[props.get("css_name", col)] = obj_meta.get(props["meta_name"])
                continue
            if col == "collection":
                row[col] = datafield('collection', obj[Collection.name], 'irods_collection').htmlstring
                continue
            row[col] = obj.get(props["irods_object"])
        rows.append(row) 
    logging.debug(f"Search {searchId}: Retrieving column values DONE")

    data = {
        "total": count,
        "rows": rows,
    }
    return json.dumps(data)

@bp.route('_search_table', methods=['GET'])
@login_required
def search_result_table():
    searchtext = (request.args.get('txt', '', type=str).strip())
    objectType = (request.args.get('objectType', 'dataset', type=str).strip())
    searchIn = (request.args.get('searchIn', '', type=str).strip())
    useExactMatch = (request.args.get('exactMatch', 'false', type=str).strip() == 'true')
    tableId = (request.args.get('tableId', '', type=str).strip())

    # Convert COLUMNS to format used by bootstrap tables
    columns = []
    for col, props in COLUMNS.items():
        if objectType not in props["used_for"]:
            continue

        column_data = { 
            "field": props.get("css_name", col),
            "title": col,
            "sortable": props["sortable"],
            "filterControl": props["filter_control"],
        }
        if objectType not in props["default_on"]:
            column_data["visible"] = False

        if props["filter_control"] == "select":
            filterData = props['filter_data']
            # Option to use a function here, so we can dynamically fill the filter options:
            if callable(filterData):
                filterData = filterData()
            column_data["filterData"] = f"json:{json.dumps(filterData)}"
        column_data["switchable"] = props.get("switchable", True)

        columns.append(column_data)

    # Collect data used for initial search
    search_dict = {
        "searchIn": searchIn,
        "useExactMatch": useExactMatch,
        "searchtext": searchtext,
    }

    # Render the bootstrap table. Information about the initial search (i.e. object type & search_dict)
    # is included in the rendered template in the bootstrap-tables data-url field and in the queryParams function
    content = { 
        'searchResults': render_template(
            'searchresults.html', 
            columns=json.dumps(columns), 
            objectType=objectType,
            searchDict=search_dict,
            tableId=tableId,
        ),
        "tableId": tableId,
    }
    return content

@bp.route('search_old')
def search_old():
    return render_template('search_old.html')

@bp.route('_search_old', methods=['GET'])
@login_required
def search_result_old():
    searchtext = (request.args.get('txt', '', type=str).strip())
    searchid = request.args.get('searchId', 0)
    useExactMatch = (request.args.get('exactMatch', 'false', type=str).strip() == 'true')
    useSearchMeta = (request.args.get('searchMeta', 'true', type=str).strip() == 'true')
    useSearchDatasetNames = (request.args.get('searchDatasetNames', 'true', type=str).strip() == 'true')
    useSearchObjectNames = (request.args.get('searchObjectNames', 'true', type=str).strip() == 'true')

    SEARCH_PATTERN = '%{}%'
    SEARCH_OPTION = 'like'
    if useExactMatch:
        SEARCH_PATTERN = '{}'
        SEARCH_OPTION = '='

    irods_session = irods_manager.session()
    data = list()

    if useSearchDatasetNames:
        #search for datasets
        query = irods_session.query(Collection.name).filter(
            Criterion( '=', CollectionMeta.name, ATTR_DATASETID ) ).filter(
            #EVEN IN AN EXACT SEARCH WE NEED TO DO A LIKE SEARCH ON A PATTERN, BECAUSE
            #THE ACTUAL COLLECTION_NAME CONTAINS THE COMPLETE PATH, INCL. PARENT COLLECTION!
            Criterion( 'like', Collection.name, ('%'+SEARCH_PATTERN).format(searchtext) ) 
        )
        for coll in query:
            basename = os.path.basename(coll[Collection.name])
            if useExactMatch:
                if searchtext != basename:
                    continue
            else:
                #this would happen by searching part of the parent path, e.g. 'minion' 
                if searchtext not in basename:
                    continue
            data.append( { 'collection': datafield('collection', coll[Collection.name], 'irods_collection').htmlstring , 
                           'dataobject': '', 
                           'metaattribute': '', 
                           'metavalue':'' } )
                
    if useSearchObjectNames:        
        #search for data objects
        query = irods_session.query(Collection.name, DataObject.name).filter(
            Criterion( SEARCH_OPTION, DataObject.name, SEARCH_PATTERN.format(searchtext) )
        )
        for obj in query:
            data.append( { 'collection': datafield('collection', obj[Collection.name], 'irods_collection').htmlstring ,
                           'dataobject': obj[DataObject.name],
                           'metaattribute': '',
                           'metavalue':'' } )

    if useSearchMeta:
        query = irods_session.query(Collection.name, CollectionMeta.name, CollectionMeta.value).filter(
            Criterion( SEARCH_OPTION, CollectionMeta.value, SEARCH_PATTERN.format(searchtext) )
        )
        for coll in query:
            data.append({ 'collection':  datafield('collection', coll[Collection.name], 'irods_collection').htmlstring ,
                          'dataobject': '',
                          'metaattribute': coll[CollectionMeta.name],
                          'metavalue': coll[CollectionMeta.value] })

        #iquest "SELECT COLL_NAME, DATA_NAME, META_DATA_ATTR_NAME, META_DATA_ATTR_VALUE where META_DATA_ATTR_VALUE like 'a55f0cd5-79cf-4b27-91e8-ce10f055e817'"
        query = irods_session.query(Collection.name, DataObject.name, DataObjectMeta.name, DataObjectMeta.value, DataObjectMeta.units).filter(
                Criterion( SEARCH_OPTION, DataObjectMeta.value, SEARCH_PATTERN.format(searchtext)) )
        for obj in query:
            data.append({ 'collection':  datafield('collection', obj[Collection.name], 'irods_collection').htmlstring ,
                          'dataobject': obj[DataObject.name],
                          'metaattribute': obj[DataObjectMeta.name],
                          'metavalue': obj[DataObjectMeta.value]})


    data2 = sorted(data, key = lambda e: (e['collection'], e['dataobject'], e['metaattribute'] ) ) 
    columns = [ { "field": "collection",    "title": "Collection", "sortable": True }, 
                { "field": "dataobject",    "title": "File", "sortable": True  }, 
                { "field": "metaattribute", "title": "Attr", "sortable": True  },
                { "field": "metavalue",     "title": "Value", "sortable": True  } ]
    searchResultsData = {
                    'id': 'searchResult',
                    'columnsJSON': json.dumps(columns),
                    'dataJSON': json.dumps(data2)
    }
    content = { 'searchResults': render_template('bootstraptable.html', data=searchResultsData), 'searchId': searchid }
    return content
