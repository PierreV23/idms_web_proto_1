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
from functools import cached_property
from dateutil.relativedelta import relativedelta
from flask import Blueprint, render_template, redirect, request, url_for, jsonify, flash, current_app
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject, DataObjectMeta
from irods.exception import CAT_NO_ROWS_FOUND, CAT_NO_ACCESS_PERMISSION, CollectionDoesNotExist, DataObjectDoesNotExist
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
from app.auth import auth_endpoint
from . import constants
from .projectdb_api import rest_call

bp = Blueprint('collbrowser', __name__, url_prefix='/collbrowser')

# This is the maximum collection name length that is not
# abbreviated to ...<last part of name>
NAME_LENGTH_COLL = 20
NAME_LENGTH_OBJ = 40

# This is exactly what it suggests
DEFAULT_GRAPH_LEVELS = 3
# This is the maximum number of subcollections we will show
# in the treeview. If there are more, we will indicate that
# by ... above/below the list
DEFAULT_NODE_TYPE = 'data'
MAX_TREEVIEW_COLLS = 150

ATTR_DATASETID = 'sys::dataset_id'
ATTR_DATAOBJECTID = 'sys::object_id'
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
ATTR_ARCHIVE_CREATERETENTION = f'{ATTR_ARCHIVE_PREFIX}create_retention'
ATTR_ARCHIVE_LASTUSERETENTION = f'{ATTR_ARCHIVE_PREFIX}lastuse_retention'

ATTR_RULES_OBJECTIDS = 'sys::rules::object_ids'

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
    cache.delete_memoized(_generate_graph_coll)
    cache.delete_memoized(_generate_graph_dataobj)
    cache.delete_memoized(add_items)
    cache.delete_memoized(subitems, *args)

# TODO: use the irods_helper instead (role irods_cronjobs)

@bp.route('_propagate', methods=['POST'])
@auth_endpoint
def propagateDownstreamInvalid():
    irods_coll = request.form.get('collection', '/', type=str)
    try:
        downstream_collections = _propagateDownstreamInvalid(irods_coll, irods_coll)
    except Exception as e:
        logging.error(f"Propagation of user invalid state from {irods_coll} failed: {e}")
        return jsonify({'msg': 'Propagation unsuccessful',}), 500
    logging.info(f"Propagated user invalid state from {irods_coll} to {downstream_collections} successfully.")
    # Invalidate the cache for the next call to the graph function
    collections_changed()
    return jsonify({'msg': 'Propagation successful',}), 200

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
    return _getmetatree(irods_coll, attr, irods_coll, default=None)

def _getmetatree(irods_coll, attr, base, default=None):
    value = iqry.qcollmetaval(irods_coll, attr)
    if value is not None:
        return value, datafield('collection', irods_coll, 'irods_collection'), irods_coll == base
    if irods_coll != '/':
        parent = os.path.dirname(irods_coll)
        return _getmetatree(parent, attr, base, default=None)
    return default, None, False

@bp.route('_metatree')
def metatree():
    attr = request.args.get('attr')
    collection = request.args.get('collection')
    value, source, override = getmetatree(collection, attr)
    if source:
        source = source.htmlshort
    else:
        source = ''
    return { 'value': value, 'source': source, 'override': override}, 200

@bp.route('_meta')
def coll_meta():
    path = request.args.get('path', '/', type=str)
    selected_object = request.args.get('selected_object', '', type=str)

# Query for collection metadata
    coll_avu = []
    query = iqry.qcollmeta(path)
    for coll_metadata in query:
        name = coll_metadata[CollectionMeta.name]
        value = coll_metadata[CollectionMeta.value]
        units = coll_metadata[CollectionMeta.units]
        if current_user.settings.get('sysmeta', 'true') == "true" or not name.startswith('sys::'):
            coll_avu.append(AVU2data(name, value, units))
# Query for object metadata
    object_avu = []
    if selected_object:
        with irods_manager.session() as session:
            query = iqry.qdataobjmeta(selected_object)
            for object_metadata in query:
                name = object_metadata[DataObjectMeta.name]
                value = object_metadata[DataObjectMeta.value]
                units = object_metadata[DataObjectMeta.units]
                if current_user.settings.get('sysmeta', 'true') == "true" or not name.startswith('sys::'):
                    object_avu.append(AVU2data(name, value, units))
    return render_template('metadata.html', coll_avu=coll_avu, object_avu=object_avu)

@bp.route('_setKeepOnlineUntil', methods=['GET'])
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

@bp.route('_upstream', methods=['GET'])
def upstream():
    types = {
        'system': 'sys::pipeline::',
        'user': 'user::pipeline::'
    }
    collection = request.args.get('collection')
    parents = []
    for kind, prefix in types.items():
        inputs = iqry.qcollmetavals(collection, f'{prefix}input_collection')
        for i in inputs:
            parents.append({
                'collection': i[CollectionMeta.value],
                'colllink': datafield('collection', i[CollectionMeta.value], 'irods_collection').htmlshort,
                    'meta': {
                        'attr': f'{prefix}input_collection',
                        'value': i[CollectionMeta.value]
                    },
                'type': kind
            })
    for kind, prefix in types.items():
        inputs = iqry.qcollmetavals(collection, f'{prefix}input_collection_id')
        for i in inputs:
            c = iqry.qcollbymeta('sys::dataset_id', i[CollectionMeta.value])
            if len(c) == 1:
                parents.append({
                    'collection': c[0][Collection.name],
                    'colllink': datafield('collection', c[0][Collection.name], 'irods_collection').htmlshort,
                    'meta': {
                        'attr': f'{prefix}input_collection_id',
                        'value': i[CollectionMeta.value]
                    },
                    'type': kind
                })
    #add reference datasets used, there can be several
    kind, prefix = ('refdata', 'sys::pipeline::refdata::[0]::')
    inputs = iqry.qcollmetavals_with_placeholder(collection, f'{prefix}reference_version_dataset_id')
    for i in inputs:
        c = iqry.qcollbymeta('sys::dataset_id', i[CollectionMeta.value])
        if len(c) == 1:
            parents.append({
                'collection': c[0][Collection.name],
                'colllink': datafield('collection', c[0][Collection.name], 'irods_collection').htmlshort,
                'meta': {
                    'attr': f'{prefix}reference_version_dataset_id',
                    'value': i[CollectionMeta.value]
                },
                'type': kind
            })
    return jsonify(parents)

@bp.route('_addmeta', methods=['GET'])
def addmeta():
    attr = request.args.get('attr')
    value = request.args.get('value')
    collection = request.args.get('collection')
    if attr and value and collection:
        iqry.addcollmetaval(collection, attr, value)
    collections_changed()
    return 'DONE', 200

@bp.route('_setmeta', methods=['GET'])
def setmeta():
    attr = request.args.get('attr')
    value = request.args.get('value')
    collection = request.args.get('collection')
    if attr and value and collection:
        iqry.scollmetaval(collection, attr, value)
    value = iqry.qcollmetaval(collection, attr)
    collections_changed()
    return { 'value': value, 'result': 'DONE'}, 200

@bp.route('_rmmeta', methods=['GET'])
def rmmeta():
    attr = request.args.get('attr')
    value = request.args.get('value')
    collection = request.args.get('collection')
    if attr and collection:
        iqry.delcollmeta(collection, attr, value)
    collections_changed()
    return 'DONE', 200


@bp.route('_setoverride', methods=['GET'])
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
            value = iqry.qcollmetaval(collection, attr)
            return { 'value': value , 'result': 'ACCESS DENIED'}, 401
    # Invalidate the cache for the next call to the graph function
    collections_changed(path=collection)
    value = iqry.qcollmetaval(collection, attr)
    return { 'value': value , 'result': 'DONE'}, 200

@cache.memoize(timeout=3600, make_name=dep_zone)
def tiers():
    return irods_objects.Tierlist('default')

class CollectionState():
    def __init__(self, collection):
        self.collection = collection
        self.__metadata = {}

    @cached_property
    def active_or_failed_pg(self):
        active_pg = False
        failed_pg = False
        if self.myprocessgroupguid:
            for coll in self.processgroupcolls:
                runsheet_state = iqry.qcollmetaval(coll[Collection.name], ATTR_RUNSHEET_STATE, 'OK')
                if runsheet_state == 'notrun':
                    failed_pg = True
                if runsheet_state not in ['done', 'error', 'notrun']:
                    active_pg = True
        return active_pg, failed_pg

    def _meta(self, attr, default=None):
        name = f'__meta__{attr}'
        if (attr in self.__metadata):
            result = self.__metadata.get(attr)
        else:
            result = iqry.qcollmetaval(self.collection, attr, '_MY_DEFAULT_STRING_')
            if result == '_MY_DEFAULT_STRING_':
                result = default
            else:
                self.__metadata[attr] = result
        return result

    @cached_property
    def active_pg(self):
        return self.active_or_failed_pg[0]

    @cached_property
    def available_processes(self):
        return projects.get_processlist(self.projectid)

    @cached_property
    def available_processgroups(self):
        return projects.get_processgrouplist(self.projectid)

    @property
    def complete(self):
        return self._meta("complete", "false")

    @cached_property
    def desired_state(self):
        return irods_objects.iState(self.tiers, self._meta(ATTR_ARCHIVE_DESIREDSTATE, "000"))

    @property
    def enabled(self):
        return getmetatree(self.collection, ATTR_ARCHIVE_ENABLE, "false")

    @property
    def failed_pg(self):
        return self.active_or_failed_pg[1]

    @property
    def is_dataset(self):
        return self._meta(ATTR_DATASETID, "") != ""

    @cached_property
    def is_offline(self):
        return not self.state.tag_present(ATTR_RESOURCE_ONLINE)

    @cached_property
    def keep_local(self):
        return getmetatree(self.collection, ATTR_ARCHIVE_LOCAL, False)

    @cached_property
    def keep_online(self):
        return getmetatree(self.collection, ATTR_ARCHIVE_KEEP_ONLINE, "false")

    @cached_property
    def keep_online_till(self):
        return datafield('keep_online', self.keep_online_time, 'timestamp')

    @cached_property
    def keep_online_time(self):
        kot = float(iqry.qcollmetaval(self.collection, ATTR_ARCHIVE_KEEP_ONLINE_TILL, default=0))
        if kot < time.time():
            kot = 0
        return kot

    @cached_property
    def min_copies(self):
        return getmetatree(self.collection, ATTR_ARCHIVE_MINCOPIES, 2)

    @cached_property
    def create_retention(self):
        return getmetatree(self.collection, ATTR_ARCHIVE_CREATERETENTION, 24)

    @cached_property
    def lastuse_retention(self):
        return getmetatree(self.collection, ATTR_ARCHIVE_LASTUSERETENTION, 24)

    @cached_property
    def object_ids(self):
        return getmetatree(self.collection, ATTR_RULES_OBJECTIDS, False)

    @property
    def myprocessgroupguid(self):
        return self._meta(ATTR_RUNSHEET_PROCESSGROUPGUID, "")

    @property
    def myrunsheetid(self):
        return self._meta(ATTR_RUNSHEET_ID, "")

    @cached_property
    def processgroupcolls(self):
        return iqry.qcollbymeta(ATTR_RUNSHEET_PROCESSGROUPGUID, self.myprocessgroupguid)

    @property
    def processgroupid(self):
        return self._meta(ATTR_PROCESSGROUPID, "")

    @property
    def processid(self):
        return self._meta(ATTR_PROCESSID, "")

    @property
    def processrequest(self):
        return self._meta(ATTR_PROCESSREQUEST, "false")

    @property
    def projectid(self):
        return self._meta(ATTR_PROJECTID, "")

    @cached_property
    def runsheetid(self):
        return datafield('runsheetid', self.myrunsheetid, 'runsheet')

    @cached_property
    def state(self):
        return irods_objects.iState(self.tiers, iqry.qcollmetaval(self.collection, ATTR_ARCHIVE_STATE, "000"))

    @cached_property
    def status(self):
        if not self.is_offline:
            status = 'ONLINE'
        elif self.state != self.desired_state and self.desired_state.tag_present(ATTR_RESOURCE_ONLINE):
            status = 'RETRIEVE_IN_PROGRESS'
        elif self.keep_online_time:
            status = 'RETRIEVE_REQUESTED'
        else:
            status = 'OFFLINE'
        return status

    @cached_property
    # This is now more of a proxy function: other member functions expect it
    def tiers(self):
        return tiers()

    @property
    def user_coll_state(self):
        return self._meta(ATTR_USER_STATE, "")

    @property
    def sys_coll_state(self):
        return self._meta(ATTR_SYS_STATE, "")

def generate_external_url(dataset_id, ticket):
    """Create URL to external data collection

    Args:
        dataset_id (str): UUID of the shared dataset
        ticket (str): shared dataset access ticket

    Returns:
        str: External data URL
    """
    base = current_user.irods_env.get('external_url', '')
    url = f'{base}/{dataset_id}-{ticket}'
    return url

@bp.route('_actions_tabs')
def actions_tabs():
    collection = request.args.get('collection', type=str)
    tabname = request.args.get('tabname', type=str)
    coll_state = CollectionState(collection)
    TABS = ['archive', 'settings', 'pipeline', 'validity', 'provenance', 'sharing']
    if tabname in TABS:
        return render_template(f'actions_{tabname}.html', coll_state=coll_state)
    else:
        return f'Unknown tab name {tabname}'

@bp.route('_actions')
def coll_actions():
    collection = request.args.get('path','/', type=str)
    coll_state = CollectionState(collection)
    return render_template('actions.html', coll_state=coll_state, collection=collection, admin=current_user.is_admin)

@bp.route('_sharetable')
def sharetable():
    collection = request.args.get('collection')
    coll_id = iqry.qcollproperty(collection, 'id')
    shares, status = rest_call('GET', f'collections/{ coll_id }/shares', prefix='/external', user=current_user.username, passwd=current_user.password)
    if status != 200:
        return {}
    # User-friendly endtime formatting:
    for share in shares:
        if share.get('endtime', 0) == 0:
            share['endtime'] = 'Indefinite'
        else:
            share['endtime'] = datafield('endtime', share['endtime'], 'timestamp' ).htmlstring
    return jsonify(shares)

@bp.route('_actions_newshare', methods=['POST'])
def actions_newshare():
    NEW_SHARE_FIELDS = [ 'description', 'endtime' ]
    formdata = request.form.to_dict()
    coll_id = iqry.qcollproperty(formdata.get('collection'), 'id')
    requestdata = { k: v for k, v in formdata.items() if k in NEW_SHARE_FIELDS }
    if 'enddate' in formdata:
        try:
            requestdata['endtime'] = int(time.mktime(datetime.strptime(formdata['enddate'], '%d/%m/%Y').timetuple()))
        except:
            data['result'] = 'Invalid time value'
            return data
    data, result = rest_call('POST', f'collections/{coll_id}/shares', prefix='/external', data=requestdata, user=current_user.username, passwd=current_user.password)
    data['result'] = result
    data['url'] = generate_external_url(data.get('dataset_id', ''), data.get('string', ''))
    return data

@bp.route('_actions_deleteshare', methods=['POST'])
def actions_deleteshare():
    data = request.form.to_dict()
    collection_id = data.get('collection_id')
    ticket_id = data.get('ticket_id')
    data, result = rest_call('DELETE', f'collections/{collection_id}/shares/{ticket_id}', prefix='/external', user=current_user.username, passwd=current_user.password)
    return data, result

@bp.route('shared')
def shared_collections():
    return render_template('shared.html')

@bp.route('_shared_colls')
def shared_collections_table():
    colls, result = rest_call('GET', 'collections', prefix='/external', user=current_user.username, passwd=current_user.password)
    data = [ {'collection': datafield('collection', r.get('path'), 'irods_collection').htmlstring} for r in colls ]
    columns = [
        { "field": "collection", "title": "Collection", "sortable": True }
    ]
    tabledata = {
        'columnsJSON': json.dumps(columns),
        'dataJSON': json.dumps(data),
        'id': 'shared_colls'
    }
    return render_template('bootstraptable.html', data=tabledata)

@bp.route('_startprocess')
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
def collist():
    path = request.args.get('path', '/', type=str)
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
    path = request.args.get('path', '/', type=str)
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

    results = {'total': coll_count + data_count , 'rows': []}

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
                    'path': os.path.join(path, do[DataObject.name]),
                    'object': 'dataobject',
                    'size': do[DataObject.size],
                    'create_time': datafield('create_time', do[DataObject.create_time], 'timestamp').htmlstring,
                    'owner_name': do[DataObject.owner_name]
                }
                results['rows'].append(objdict)
        except CAT_NO_ROWS_FOUND:
            pass
    return jsonify(results)

# helper functions used for labeling, and layout
def shortname(name, l):
    s = name
    if len(name)>l:
        s = '...' + name[-l+4:]
    return s

def node_shape(node_type):
    '''
    depending the node_type determine the shape, fillcolor and style of the node
    '''
    layout = constants.LAYOUT.get(node_type, constants.DEFAULT_SHAPE)
    return layout[constants.SHAPE1], layout[constants.COLOR1], layout[constants.STYLE]
def graph_shape(graph_type):
    '''
    depending the graph_type determine the fillcolor and style of the node
    '''
    layout = constants.LAYOUT.get(graph_type, constants.DEFAULT_SHAPE)
    return layout[constants.COLOR1], layout[constants.STYLE]

class Dictlist(dict):
    """ Custom dict class that allows storing multiple values under one key
    get method will return first value, so can be used as in-place dict replacement
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

# if 'byname' is not set, check both name and id
PROVATTR = [
    {'type': 'entity', 'attr': 'sys::pipeline::input_collection_id', 'byname': False},
    {'type': 'entity', 'attr': 'user::pipeline::input_collection_id', 'byname': False},
    {'type': 'entity', 'attr': 'sys::pipeline::input_collection', 'byname': True},
    {'type': 'entity', 'attr': 'user::pipeline::input_collection', 'byname': True},
    {'type': 'entity', 'attr': 'prov:wasDerivedFrom'},
    {'type': 'entity', 'attr': 'prov::wasDerivedFrom'},
    {'type': 'activity', 'attr': 'prov:wasGeneratedBy'},
    {'type': 'activity', 'attr': 'prov::wasGeneratedBy'},
    {'type': 'git', 'attr': 'mdma::git::remote'},
    {'type': 'githash', 'attr': 'mdma::git::sha'},
    {'type': 'git', 'attr': 'sys::pipeline::gitrepo'},
    {'type': 'githash', 'attr': 'sys::pipeline::githash'},
]

@bp.route('_related')
def multi_list_coll():
    # Create a small HTML page with a list of related collections
    #
    PARAMSETS = {
        'U':[
            ('user::pipeline::input_collection', True),
            ('user::pipeline::input_collection_id', False),
            ('prov:wasDerivedFrom', True)
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
        resultnames += related_coll(coll, attr, forward=forward, byname=byname)
    results = [(iqry.qcollmetaval(r, ATTR_PROJECTID, default=''), datafield('coll', r, 'irods_collection')) for r in resultnames]
    return render_template('small_collist.html', results = results)

def related_coll(coll, attr, forward=True, byname=True):
    '''Find collections related to <coll>
    In case forward=True
       Search for collections that have metadata attribute <attr> with the name or dataset_id of coll in the value
    In case forward=False
       Search for collections that have a name or datasetid equal to the value of <attr> on <coll>

    returns: list of related collections
    '''
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

# Generate Collection Graph
@bp.route('/_graph_coll')
def generate_graph_coll():
    coll = request.args.get('path', '/', type=str)
    maxlevels = request.args.get('graph_levels_coll', DEFAULT_GRAPH_LEVELS, type=int)
    graph_simplify = request.args.get('graph_simplify_coll', 0, type=int)
    provenance_labels = request.args.get('provenance_labels_coll', 0, type=int)
    show_upstream = request.args.get('show_upstream_coll', 0, type=int)
    show_downstream = request.args.get('show_downstream_coll', 0, type=int)
    return _generate_graph_coll(coll, maxlevels, graph_simplify, provenance_labels, show_upstream, show_downstream)

@cache.memoize(timeout=60, make_name=dep_userzone)
def _generate_graph_coll(coll, maxlevels, graph_simplify, provenance_labels, show_upstream, show_downstream):

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
            return f'GITNODE-{node}'
        else:
            return node

    def prov(label, d = ''):
        '''
        Toggle the labels for provenance
        '''
        if provenance_labels == 1:
            # check for destination = git
            if d[:8] == 'GITNODE-':
                label = 'used'
            return label
        else:
            return ''

    def traverse(coll, levels=maxlevels):
        if coll in nodes:
            return

        nodes.add(coll)

        MAX_INPUTS = current_app.config.get('GRAPH_MAX_INPUTS', 3)
        MAX_OUTPUTS = current_app.config.get('GRAPH_MAX_OUTPUTS', 11)

        def handle_neighbours(node, neighbours, edgelist, levels, inputs=True, relation_type='S'):
            '''
            '''
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
                        multi_edges.add((label, node, 'wasDerivedFrom'))
                    else:
                        multi_edges.add((node, label, 'wasDerivedFrom'))
            for neighbour in neighbours:
                if inputs:
                    vect = (neighbour, node, 'wasDerivedFrom')
                else:
                    vect = (node, neighbour, 'wasDerivedFrom')
                if not multi:
                    if levels:
                        traverse(neighbour, levels=levels-1)
                        edgelist.add(vect)
                    else:
                        dashed_edges.add(vect)
                elif neighbour in nodes:
                    edgelist.add(vect)

        # FIND INPUTS
        if show_upstream == 1:
            input_colls = related_coll(coll, 'sys::pipeline::input_collection_id', forward=False, byname=False)
            handle_neighbours(coll, input_colls, edges, levels, inputs=True)

        # FIND OUTPUTS
        if show_downstream == 1:
            output_colls = related_coll(coll, 'sys::pipeline::input_collection_id', forward=True, byname=False)
            handle_neighbours(coll, output_colls, edges, levels, inputs=False)

        # FIND EXTRA INPUTS
        if show_upstream == 1:
            extra_colls = set(related_coll(coll, 'user::pipeline::input_collection', forward=False, byname=True))
            extra_colls |= set(related_coll(coll, 'user::pipeline::input_collection_id', forward=False, byname=False))
            handle_neighbours(coll, extra_colls, dashed_edges, levels, inputs=True, relation_type='U')

        # FIND PROV COLLECTIONS (files)
        if show_upstream == 1:
            prov_colls_i = set(related_coll(coll, 'prov:wasDerivedFrom', forward=False, byname=True))
            prov_colls_i |= set(related_coll(coll, 'prov::wasDerivedFrom', forward=False, byname=True))
            handle_neighbours(coll, prov_colls_i, edges, levels, inputs=True, relation_type='S')

        if show_downstream == 1:
            prov_colls_o = set(related_coll(coll, 'prov:wasDerivedFrom', forward=True, byname=True))
            prov_colls_o |= set(related_coll(coll, 'prov::wasDerivedFrom', forward=True, byname=True))
            handle_neighbours(coll, prov_colls_o, edges, levels, inputs=False, relation_type='S')

        # FIND EXTRA INPUTS OF REFERENCE_DATA
        if show_upstream == 1:
            reference_data_colls = set()
            for i in range(1000): #just an arbitrary but large number
                temp = set(related_coll(coll, f'sys::pipeline::refdata::{i}::reference_version_dataset_id', forward=False, byname=False))
                if temp == set():
                    #we couldn't find any more reference_versions
                    break
                reference_data_colls |= temp
            handle_neighbours(coll, reference_data_colls, dashed_edges, levels, inputs=True, relation_type='S')

        # FIND EXTRA OUTPUTS
        if show_downstream == 1:
            ref_colls = set(related_coll(coll, 'user::pipeline::input_collection', forward=True, byname=True))
            ref_colls |= set(related_coll(coll, 'user::pipeline::input_collection_id', forward=True, byname=False))
            handle_neighbours(coll, ref_colls, dashed_edges, levels, inputs=False, relation_type='U')

    traverse(coll, levels=maxlevels)

    # Remove multinodes when all items in multinode are in the graph
    # and combine equal multinodes
    for n, (multinode, related_node, neighbours) in reversed(list(enumerate(multinodes))):
        input_node = multinode[0] == 'I'
        if set(neighbours).issubset(nodes):
            # Remove the multinode and the edge
            if input_node:
                vect = (multinode, related_node, 'wasDerivedFrom')
            else:
                vect = (related_node, multinode, 'wasDerivedFrom')
            for neighbour in neighbours:
                if input_node:
                    edges.add((neighbour, related_node, 'wasDerivedFrom'))
                else:
                    edges.add((related_node, neighbour, 'wasDerivedFrom'))
            # Remove the multinode and the edge
            multi_edges.remove(vect)
            del multinodes[n]
        else:
            # Combine equal multinodes:
            for other_multinode, _ , other_neighbours in multinodes[:n]:
                if other_neighbours == neighbours:
                    # Move the edges:
                    if input_node:
                        vect = (multinode, related_node, 'wasDerivedFrom')
                        new_vect = (other_multinode, related_node, 'wasDerivedFrom')
                    else:
                        vect = (related_node, multinode, 'wasDerivedFrom')
                        new_vect = (related_node, other_multinode, 'wasDerivedFrom')
                    multi_edges.remove(vect)
                    multi_edges.add(new_vect)
                    del multinodes[n]
                    break


    #######################################
    # Draw the Collection Graph

    graph = Digraph('Collections')
    graph.graph_attr['rankdir'] = 'LR'
    graph.graph_attr['fontsize'] = '15'

    # Start with all the nodes
    for node in sorted(nodes):
        collmeta = Dictlist()
        q = iqry.qcollmeta(node)
        for m in q:
            collmeta[m[CollectionMeta.name]] = m[CollectionMeta.value]
        
        # list of activity attribute labels to check for:
        activity_attrs = [item['attr'] for item in PROVATTR if item['type'] == 'activity']
        
        # combine activity metadata in list
        code_nodes = [collmeta.get(a) for a in activity_attrs if collmeta.get(a)]

        for cn in code_nodes:
            code_node = f'GITNODE-{node}'
            shape, shape_color, shape_style = node_shape('activity')
            graph.node(code_node, cn, shape=shape, fillcolor = shape_color, style = shape_style, tooltip = cn, target = "_blank", fontsize = '8')
            graph.edge(code_node, node, prov('wasGeneratedBy'))
            processes.add(node)
            
        # create the collection graph node
        git = collmeta.get('sys::pipeline::gitrepo')
        githash = collmeta.get('sys::pipeline::githash')
        shape, shape_color, shape_style = node_shape('process')
        if git:
            repo_url = urlparse(git)
            # Strip credentials from repo url and add commit hash.
            repo_url = repo_url._replace(netloc=repo_url.hostname)
            link = repo_url._replace(path='{}/tree/{}'.format(repo_url.path.replace('.git', ''), githash))
            label = f"{collmeta.get('sys::runsheet::processID', '')}  \n{git.split('/')[-1]}  " #2 spaces to avoid overlap label text and node border
            git_node = f'GITNODE-{node}'
            graph.node(git_node, label, shape=shape, fillcolor = shape_color, style = shape_style, URL=link.geturl(), target = "_blank", fontsize='8')
            graph.edge(git_node, node, prov('wasGeneratedBy'))
            processes.add(node)

        # TODO dit logischer maken
        node_type = collmeta.get('sys::runsheet::state', 'unknown')
        if node_type in ('unknown'):
            node_type = collmeta.get('sys::data::type', DEFAULT_NODE_TYPE)
        if node_type in ('unknown'):
            node_type = collmeta.get('user::data::type', DEFAULT_NODE_TYPE)
        if node_type in ('done'):
            node_type = collmeta.get('sys::data::type', node_type)
            node_type = collmeta.get('user::data::type', node_type)

        shape, shape_color, shape_style = node_shape(node_type)

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

        # determine whether the object type is a collection or dataobject
        obj_type = iqry.qpathobjecttype(node)

        if obj_type != 'path':
            shape, shape_color, shape_style = node_shape('file')
            # make label (show filename in separate line, and maximized path length accordingly)
            split_parts = node.split("/")
            filename = split_parts[-1]
            project_path = os.path.join(*split_parts[:4])
            filepath = node[len(project_path) + 1:len(node) - len(filename)]
            label = shortname(filepath, max(NAME_LENGTH_COLL, len(filename) + 2)) + '\n' + filename
        else:
            label = projectid + shortname(node, NAME_LENGTH_COLL)

        # focus on this object
        if node == coll:
            penwidth = '3'
            clss = { 'class' : f'{obj_type}-change center-coll' }
        else:
            penwidth = '1'
            clss = { 'class' : f'{obj_type}-change' }

        graph.node(node, label, shape=shape, color=border_color,
            fillcolor=shape_color, style=shape_style, penwidth=penwidth,
            fontsize='8', setting='extra', **clss, id=node)

    # multi-nodes
    for multinode, related_node, neighbours in multinodes:
        clss = { 'class' : 'collist' }
        graph.node(multinode, '.. multiple ..', shape="rarrow", style='filled', setting='extra', **clss, id=multinode)

    # draw the solid lines
    for s, d, label in edges:
        graph.edge(s, destnode(d), label = prov(label, destnode(d)))

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

    for s, d, label in multi_edges:
        graph.edge(s, destnode(d), style='dotted', label = prov(label))

    return graph.pipe(format='svg').decode('utf-8')

@cache.memoize(timeout=300, make_name=dep_zone)
def subitems(path):
    count = 0
    with irods_manager.session() as session:
        query = session.query(Collection.id).filter(
            Criterion('=', Collection.parent_name, path)).count(Collection.id)
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
    colls = [c[Collection.name] for c in iqry.qcollchildren(path)]

    #
    # Handle very long list of collections
    #
    colls_length = len(colls)
    if colls_length > MAX_TREEVIEW_COLLS:
        # Find the index of the active path in colls
        active_index_list = [ i for i, c in enumerate(colls) if active.startswith(c) ]
        if active_index_list == []: ## This is not a path to the active path
            colls = colls[:MAX_TREEVIEW_COLLS]
            if colls_length > MAX_TREEVIEW_COLLS:
                colls = colls + ['...']
        elif len(active_index_list) == 1:
            # This is a path to the active collection
            # For example: active coll could be /rivmZone/projects/s-mrsa/241004_VH01799_133_AAG5MWVM5_0008
            # while this node is /rivmZone/projects/s-mrsa
            # make sure it is in the list
            lower = max(active_index_list[0] - MAX_TREEVIEW_COLLS // 2, 0)
            colls = colls[lower:lower+MAX_TREEVIEW_COLLS]
            if lower > 0:
                colls = ['...'] + colls
            if lower + MAX_TREEVIEW_COLLS < colls_length:
                colls = colls + ['...']
        elif len(active_index_list) > 1:
            # This cannot happen!
            colls = [ 'ERROR' ]
    for collpath in colls:
        collname = collpath.split('/')[-1]
        if collname:
            if collpath == '...':
                result = '{0}<li><span class="caret-nosub">...</span></li>'.format(result)
            else:
                c1=' path-active' if collpath == active else ''
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

# Generate Dataobject Graph
def related_dataobj(dataobj, attr, forward=True, byname=True):
    # Find data objects related to <dataobj>
    # In case forward=True
    #   Search for data objects that have metadata attribute <attr> with the name in the metadata value
    # In case forward=False
    #   Search for data objects that have a name equal to the value of <attr> on <dataobj>

    # Find metadata of <dataobj>
    dataobjmeta = Dictlist()
    q = iqry.qdataobjmeta(dataobj)
    for m in q:
        dataobjmeta[m[DataObjectMeta.name]] = m[DataObjectMeta.value]

    if forward:
        search_value = dataobj if byname else dataobjmeta.get(ATTR_DATAOBJECTID)
        q = iqry.qdataobjbymeta(attr, search_value)
        result = { c[Collection.name] + '/' + c[DataObject.name] for c in q }
    else:
        if byname:
            result = set(dataobjmeta.get_all(attr, []))
        else:
            result = set()
            values =  dataobjmeta.get_all(attr, [])
            for value in values:
                q = iqry.qdataobjbymeta(ATTR_DATAOBJECTID, value)
                result.update([ c[Collection.name] + '/' + c[DataObject.name] for c in q ])
    return result

@bp.route('/_graph_dataobj')
def generate_graph_dataobj():
    coll = request.args.get('path', '/', type=str)
    dataobj = request.args.get('selected_object', '', type=str)
    maxlevels = request.args.get('graph_levels_obj', DEFAULT_GRAPH_LEVELS, type=int)
    graph_simplify = request.args.get('graph_simplify_obj', 0, type=int)
    provenance_labels = request.args.get('provenance_labels_obj', 0, type=int)
    include_all_from_coll = request.args.get('include_all_from_coll', 0, type=int)
    show_collections = request.args.get('show_collections', 0, type=int)
    show_upstream = request.args.get('show_upstream_obj', 0, type=int)
    show_downstream = request.args.get('show_downstream_obj', 0, type=int)
    graph_direction_tb = request.args.get('graph_direction_tb_obj', 0, type=int)
    return _generate_graph_dataobj(coll, dataobj, maxlevels, graph_simplify, provenance_labels, include_all_from_coll, show_collections, show_upstream, show_downstream, graph_direction_tb)

@cache.memoize(timeout=60, make_name=dep_userzone)
def _generate_graph_dataobj(coll, dataobj, maxlevels, graph_simplify, provenance_labels, include_all_from_coll, show_collections, show_upstream, show_downstream, graph_direction_tb):

    nodes = set()
    processes = set()
    edges = set()
    dashed_edges = set()

    def destnode(node):
        # Determine if destination node is a collection node or the associated process node
        if node in processes:
            return f'GITNODE-{node}'
        else:
            return node

    def prov(label, d = ''):
        # Toggle the labels for provenance
        if provenance_labels == 1:
            # check for destination = git
            if d[:8] == 'GITNODE-':
                label = 'used'
            return label
        else:
            return ''

    def traverse(dataobj, levels=maxlevels):
        '''
        '''
        if dataobj in nodes:
            return
                
        # if dataobj is not a path, but plain text (contains blanks or no initial '/')
        if ' ' in dataobj or dataobj[:1] != '/':
            return
        
        nodes.add(dataobj)
        
        MAX_INPUTS = current_app.config.get('GRAPH_MAX_INPUTS', 3)
        MAX_OUTPUTS = current_app.config.get('GRAPH_MAX_OUTPUTS', 11)

        def handle_neighbours(node, neighbours, edgelist, levels, inputs=True):

            for neighbour in neighbours:
                # if neighbour is not a path, but plain text (contains blanks or no initial '/')
                if ' ' in neighbour or neighbour[:1] != '/':
                    continue
                
                if inputs:
                    vect = (neighbour, node, 'wasDerivedFrom')
                else:
                    vect = (node, neighbour, 'wasDerivedFrom')
                    
                if levels:
                    traverse(neighbour, levels=levels-1)
                    edgelist.add(vect)
                else:
                    dashed_edges.add(vect)
                        
        # FIND INPUTS
        if show_upstream == 1:
            input_dataobjects = related_dataobj(dataobj, 'prov:wasDerivedFrom', forward=False, byname=True)
            input_dataobjects |= related_dataobj(dataobj, 'prov::wasDerivedFrom', forward=False, byname=True)
            handle_neighbours(dataobj, input_dataobjects, edges, levels, inputs=True)

        # FIND OUTPUTS
        if show_downstream == 1:
            output_dataobjects = related_dataobj(dataobj, 'prov:wasDerivedFrom', forward=True, byname=True)
            output_dataobjects |= related_dataobj(dataobj, 'prov::wasDerivedFrom', forward=True, byname=True)
            handle_neighbours(dataobj, output_dataobjects, edges, levels, inputs=False)

        return nodes

    if include_all_from_coll == 1:
        dataobjs = iqry.qcolldataobjectpaths(coll)
        for do in dataobjs:
            traverse(do, levels=maxlevels)
    else:
        if dataobj:
            traverse(dataobj, levels=maxlevels)
        else:
            return

    #######################################
    # Draw the Data Object graph

    graph = Digraph('Data Objects')
    graph.graph_attr['rankdir'] = 'LR' if graph_direction_tb == 0 else 'TB' # Graph direction
    graph.graph_attr['fontsize'] = '15'
    graph.attr(compound='true') # allow edges between collections
    
    # longer path_names in top_bottom representation
    NAME_LENGTH_OBJ = 40 if graph_direction_tb == 0 else 100

    # Start with all the nodes
    for node in sorted(nodes):
        dataobjmeta = Dictlist()
        q = iqry.qdataobjmeta(node)
        for m in q:
            dataobjmeta[m[DataObjectMeta.name]] = m[DataObjectMeta.value]
            
        # list of activity attribute labels to check for:
        activity_attrs = [item['attr'] for item in PROVATTR if item['type'] == 'activity']
        
        # combine activity metadata (avoid None in list)
        code_nodes = [dataobjmeta.get(a) for a in activity_attrs if dataobjmeta.get(a)]
       
        # TODO check if node is Collection (https://gitlab.rivm.nl/bioinformatics/ngsweb/-/issues/145)
        
        # set class to enable clicking in graph
        clss = { 'class' : 'dataobject-change' }
        # default node_shape is file
        shape, shape_color, shape_style = node_shape('file')         
        
        # if include all files make all files in the collection bold
        if node == dataobj:
            penwidth = '4'
            fontsize = '10'
            clss['class'] += ' center-obj' # class to centralize object
            sub = True if include_all_from_coll == 1 else False
        elif include_all_from_coll == 1 and node[:len(node) - len(node.split('/')[-1])] == dataobj[:len(dataobj) - len(dataobj.split('/')[-1])]:
            penwidth = '3'
            fontsize = '10'
            sub = True
        else:
            penwidth = '1'
            fontsize = '8'
            sub = False

        # make label (show complete filename, and path length accordingly 3x...)
        split_parts = node.split("/")
        filename = split_parts[-1]
        project_path = os.path.join(*split_parts[:2])
        filepath = node[len(project_path)+1:len(node) - len(filename)]
        # show only filename in node, if collections are shown
        label = filename if show_collections == 1 else shortname(filepath, max(len(filename) + 2, NAME_LENGTH_OBJ)) + '\n' + filename 
    
        if sub:
            # generate 1 subgraph, styled as collection for selected collection
            with graph.subgraph(name=f'cluster_{coll}') as c:
                graph_color, graph_style = graph_shape('collection')
                c.attr(style=graph_style, color=graph_color, tooltip=f'Collection: {coll}', label=coll)
                c.node(node, label, shape=shape, fillcolor=shape_color, style=shape_style, penwidth=penwidth,
                    fontsize=fontsize, setting='extra', **clss, id=node)
        elif show_collections == 1:
            # generate subgraphs, styled as collections for all collections
            with graph.subgraph(name=f'cluster_{filepath}') as c:
                graph_color, graph_style = graph_shape('collection')
                c.attr(style=graph_style, color=graph_color, tooltip=f'Collection: {filepath}', label=filepath)
                c.node(node, label, shape=shape, fillcolor=shape_color, style=shape_style, penwidth=penwidth,
                    fontsize=fontsize, setting='extra', **clss, id=node)  
        else:
            # no subgraphs
            graph.node(node, label, shape=shape, fillcolor=shape_color, style=shape_style, penwidth=penwidth,
                    fontsize=fontsize, setting='extra', **clss, id=node)
                    
        # list of activity attribute labels to check for:
        activity_attrs = [item['attr'] for item in PROVATTR if item['type'] == 'activity']
        
        # combine activity metadata (avoid None in list)
        code_nodes = [dataobjmeta.get(a) for a in activity_attrs if dataobjmeta.get(a)]

        for cn in code_nodes:
            code_node = f'GITNODE-{node}'
            shape, shape_color, shape_style = node_shape('activity')
            if sub:
                # add nodes and edge to the selected collection subgraph
                with graph.subgraph(name=f'cluster_{coll}') as c:
                    c.node(code_node, cn, shape=shape, fillcolor = shape_color, style = shape_style, tooltip = cn, target = "_blank", fontsize = '8')
                    c.edge(code_node, node, prov('wasGeneratedBy'))
            elif show_collections == 1:
                # add nodes and edge to all the subgraphs
                with graph.subgraph(name=f'cluster_{filepath}') as c:
                    c.node(code_node, cn, shape=shape, fillcolor = shape_color, style = shape_style, tooltip = cn, target = "_blank", fontsize = '8')
                    c.edge(code_node, node, prov('wasGeneratedBy'))
            else:
                graph.node(code_node, cn, shape=shape, fillcolor = shape_color, style = shape_style, tooltip = cn, target = "_blank", fontsize = '8')
                graph.edge(code_node, node, prov('wasGeneratedBy'))
            processes.add(node)

    # draw the solid lines ( destnode determines GITNODES)

    for s, d, label in edges:
        graph.edge(s, destnode(d), prov(label, destnode(d)))

    # draw the dashed lines
    dash_counter = 1
    for vt in dashed_edges - edges:
        vect = list(vt)
        for i, v in enumerate(vect):
            if not v in nodes:
                # create a blank node, to point to
                vect[i] = f'NODE{dash_counter}'
                dash_counter += 1
                graph.node(vect[i], '', shape='none', width='0', height='0')
        graph.edge(vect[0], destnode(vect[1]), prov(label, destnode(vect[1])), style='dashed')

    return graph.pipe(format='svg').decode('utf-8')

# Collection tree
@bp.route('/_tree')
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
    path = request.args.get('path', None, type=str)
    selected_object = request.args.get('selected_object', '', type=str)

    # Check supplied path for collection or object
    obj_type = iqry.qpathobjecttype(path) if path else 'not_found'

    # Get path from user settings or default, revert to collection when dataobject is selected
    if obj_type in ['not_found', 'dataobject']:
        path = current_user.settings.get('path', f'/{current_user.irods_zone}/projects')

    # Store path in user settings
    current_user.settings['path'] = path

    graph_levels_coll = current_user.settings.setdefault('graph_levels_coll', DEFAULT_GRAPH_LEVELS)
    graph_simplify_coll = current_user.settings.setdefault('graph_simplify_coll', 0)
    provenance_labels_coll = current_user.settings.setdefault('provenance_labels_coll', 0)
    zoomlevel_coll = current_user.settings.setdefault('zoomlevel_coll', 50)
    graph_levels_obj = current_user.settings.setdefault('graph_levels_obj', DEFAULT_GRAPH_LEVELS)
    graph_simplify_obj = current_user.settings.setdefault('graph_simplify_obj', 0)
    provenance_labels_obj = current_user.settings.setdefault('provenance_labels_obj', 0)
    zoomlevel_obj = current_user.settings.setdefault('zoomlevel_obj', 50)
    include_all_from_coll=current_user.settings.setdefault('include_all_from_coll', 0)
    show_collections=current_user.settings.setdefault('show_collections', "0")
    show_upstream_obj=current_user.settings.setdefault('show_upstream_obj', "1")
    show_upstream_coll=current_user.settings.setdefault('show_upstream_coll', "1")
    show_downstream_obj=current_user.settings.setdefault('show_downstream_obj', "1")
    show_downstream_coll=current_user.settings.setdefault('show_downstream_coll', "1")
    graph_direction_tb_obj=current_user.settings.setdefault('graph_direction_tb_obj', "0")
    vertical_pos = current_user.settings.setdefault('vertical_pos', "40")

    return render_template('collbrowser.html', path=path, selected_object=selected_object,
                           graph_levels_coll=graph_levels_coll, graph_levels_obj=graph_levels_obj,
                           graph_simplify_coll=graph_simplify_coll, graph_simplify_obj=graph_simplify_obj,
                           zoomlevel_coll=zoomlevel_coll, zoomlevel_obj=zoomlevel_obj,
                           provenance_labels_coll=provenance_labels_coll, provenance_labels_obj=provenance_labels_obj,
                           include_all_from_coll=include_all_from_coll, show_collections=show_collections,
                           show_upstream_obj=show_upstream_obj, show_upstream_coll=show_upstream_coll,
                           show_downstream_obj=show_downstream_obj, show_downstream_coll=show_downstream_coll,
                           graph_direction_tb_obj=graph_direction_tb_obj, vertical_pos=vertical_pos)


@bp.route('upload_file', methods=['GET', 'POST'])
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

@bp.route('_deletefile', methods=['POST'])
def delete_file():
    requestdata = request.form.to_dict()
    if 'path' in requestdata:
        path = requestdata['path']
        current_user.ifs.deletefile(path)
        contents_changed()
    return '', 201


@bp.route('search')
@login_required
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
        "dataobject_metadata": DataObjectMeta.value,
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
        if search_in_type == "dataobject_metadata":
            # To reliably search for metadata values in all metadata fields, iRODS still needs the field to be 'specified'.
            query = query.filter(Criterion(
                "like",
                DataObjectMeta.name,
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
@login_required
def search_old():
    return render_template('search_old.html')

@bp.route('_search_old', methods=['GET'])
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

@bp.route('_mydatasets')
def mydatasets():
    with irods_manager.session() as session:
        q = session.query(Collection.name).filter(
            Criterion('=', Collection.owner_name, current_user.username)).filter(
            Criterion('=', CollectionMeta.name, ATTR_DATASETID)
            )
        result = [{ 'collection': datafield('collection', r[Collection.name], 'irods_collection').htmlstring } for r in q]
    print (result)
    return jsonify(result)