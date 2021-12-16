#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 10:54:56 2019

@author: wierinve
"""

import base64
import os
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject, DataObjectMeta
from irods.column import Criterion
from app.datafield import AVU2data, datafield
from app.irods_helper import getmetaitem
from graphviz import Digraph
from irods.meta import iRODSMeta
from . import projects
from . import iqry
from .flaskcache import cache, makekey, makename
import json

bp = Blueprint('collbrowser', __name__, url_prefix='/collbrowser')

NAME_LENGTH = 20
MAX_GRAPH_LEVELS = 3
SEARCHPAGE_SIZE = 1000

ATTR_DATASETID = 'sys::dataset_id'
ATTR_PROJECTID = 'projectID'
ATTR_PROCESSID = 'processID'
ATTR_PROCESSGROUPID = 'processgroupID'
#TODO: use constants.py (role irods_cronjobs)
ATTR_ARCHIVE_PREFIX = 'sys::archive::'
ATTR_ARCHIVE_ENABLE = f'{ATTR_ARCHIVE_PREFIX}enable'
ATTR_ARCHIVE_DEFAULT_STATE = f'{ATTR_ARCHIVE_PREFIX}default_state'
ATTR_ARCHIVE_DESIREDSTATE = f'{ATTR_ARCHIVE_PREFIX}desired_state'
ATTR_ARCHIVE_KEEP_ONLINE = f'{ATTR_ARCHIVE_PREFIX}keep_online'
ATTR_ARCHIVE_KEEP_ONLINE_TILL = f'{ATTR_ARCHIVE_PREFIX}keep_online_till'
ATTR_ARCHIVE_LOCAL = f'{ATTR_ARCHIVE_PREFIX}local'
ATTR_PROCESSREQUEST = 'processrequest'
ATTR_ARCHIVE_STAGE = f'{ATTR_ARCHIVE_PREFIX}stage'
ATTR_ARCHIVE_STATE = f'{ATTR_ARCHIVE_PREFIX}state'
ATTR_ARCHIVE_LASTRUN = f'{ATTR_ARCHIVE_PREFIX}lastrun'
ATTR_ARCHIVE_MINSTABLE = f'{ATTR_ARCHIVE_PREFIX}min_stable'
ATTR_ARCHIVE_ONLINEPERCENTAGE = f'{ATTR_ARCHIVE_PREFIX}online_percentage'
ATTR_ARCHIVE_MINCOPIES = f'{ATTR_ARCHIVE_PREFIX}min_copies'
USER_PIPELINE_AUTOSTART = 'user::pipeline::autostart'


COLL_SHAPES = {
    'valid':      ('box3d', 'springgreen1'),
    'invalid':    ('box3d', 'tomato'),
    'imported':   ('cylinder', 'skyblue1'),
    'temporary':  ('note',  'gold2'),
    'distributed':('box3d','springgreen1:gray'),
    'unknown'    :('ellipse', 'gray'),
    'qc_report'  :('box3d', 'yellow'),
    'refsamp_report'  :('box3d', 'yellow')}

PROCESS_SHAPE = 'cds'

# TODO: use the irods_helper instead (role irods_cronjobs)


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
@cache.cached(timeout=60, key_prefix=makekey)
def coll_meta():
    path = request.args.get('path','/', type=str)
    object = request.args.get('object', '', type=str)
    irods_session = current_user.irods_session
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
    if object:
        object_avu = []
        query = irods_session.query(DataObjectMeta.name, DataObjectMeta.value,
                                    DataObjectMeta.units).filter(
                                        Criterion('=', Collection.name, path)).filter(
                                        Criterion('=', DataObject.name, object)
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
    irods_session = current_user.irods_session

    selectionStr = request.args.get('selection','None', type=str)
    collection = request.args.get('collection','None', type=str)

    now = datetime.today()
    days = 0
    try:
        days = int(selectionStr)
    except ValueError:
        print( f"unknown selection for _setKeepOnlineUntil: {selectionStr}")
        return('DONE')
    keepOnlineUntil = now + relativedelta(days=days)

    coll_obj = irods_session.collections.get(collection)
    new_meta = iRODSMeta(ATTR_ARCHIVE_KEEP_ONLINE_TILL, str(int(datetime.timestamp(keepOnlineUntil))), 'timestamp' )
    coll_obj.metadata[ATTR_ARCHIVE_KEEP_ONLINE_TILL] = new_meta
    return('DONE')


@bp.route('_setmeta', methods=['GET'])
@login_required
def setmeta():
    attr = request.args.get('attr')
    value = request.args.get('value')
    collection = request.args.get('collection')
    if attr and value and collection:
        coll_obj = current_user.irods_session.collections.get(collection)
        coll_obj.metadata[attr] = iRODSMeta(attr, value)
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
            print( f"unknown selection for _setKeepLocal: {overrideStr}" )
            return('DONE')
        coll_obj = current_user.irods_session.collections.get(collection)
        if overrideStr == 'false':
            coll_obj.metadata._delete_all_values(attr)
        else:
            new_meta = iRODSMeta(attr, value)
            coll_obj.metadata[attr] = new_meta
    return('DONE')    


@bp.route('_actions')
@login_required
@cache.cached(timeout=60, key_prefix=makekey)
def coll_actions():
    path = request.args.get('path','/', type=str)
    coll_name = path.split('/')[-1]

    is_dataset = iqry.qcollmetavalstatic(path, ATTR_DATASETID, "") != ""
    keep_local = getmetatree(path, ATTR_ARCHIVE_LOCAL, False)
    online_percentage = int(iqry.qcollmetaval(path, ATTR_ARCHIVE_ONLINEPERCENTAGE, 0 ))
    archive_state = iqry.qcollmetaval(path, ATTR_ARCHIVE_STATE, "000")
    min_copies = getmetatree(path, ATTR_ARCHIVE_MINCOPIES, 2)
    keep_online = getmetatree(path, ATTR_ARCHIVE_KEEP_ONLINE, "false")
    is_archived = False
    # TODO: This should use the sys::resource::online property of a resource to determine
    # if a collection is online
    if archive_state[-1] == '1':
        is_archived = True 
    is_offline = False
    if archive_state[:2] == '00' and archive_state[-1] == '0':
        is_offline = True

    projectid = iqry.qcollmetavalstatic(path, ATTR_PROJECTID, "")
    processid = iqry.qcollmetaval(path, ATTR_PROCESSID, "")
    processgroupid = iqry.qcollmetaval(path, ATTR_PROCESSGROUPID, "")
    processes = projects.get_processlist(projectid)
    processgroups = projects.get_processgrouplist(projectid)
    processrequest = iqry.qcollmetaval(path, ATTR_PROCESSREQUEST, "false")
    start_next_process = iqry.qcollmetaval(path, USER_PIPELINE_AUTOSTART, "true")

    archival_state = {
        "enabled": iqry.qcollmetaval(path, ATTR_ARCHIVE_ENABLE, "false"),
        "is_dataset": is_dataset,
        "is_archived": is_archived,
        "is_offline": is_offline,
        "keep_local": keep_local,
        "online_percentage": online_percentage,
        "min_copies": min_copies,
        "keep_online": keep_online
    }

    return render_template('actions.html', collection=path, 
        name=coll_name, archival_state=archival_state,
        processes=processes, processid=processid, processrequest=processrequest,
        processgroups=processgroups, processgroupid=processgroupid,
        admin=current_user.is_admin, start_next_process=start_next_process)


@bp.route('_startprocess')
@login_required
def startprocess():
    collection = request.args.get('collection')
    if current_user.ifs.folderexists(collection):
        c = current_user.irods_session.collections.get(collection)
    else:
        return 'FAILED'

    processid = request.args.get('processid')
    processgroupid = request.args.get('processgroupid')
    if processid:
        c.metadata[ATTR_PROCESSID] = iRODSMeta(ATTR_PROCESSID, processid)
    elif processgroupid:
        c.metadata._delete_all_values(ATTR_PROCESSID)
        c.metadata[ATTR_PROCESSGROUPID] = iRODSMeta(ATTR_PROCESSGROUPID, processgroupid)
    else:
        return 'FAILED'
    c.metadata[ATTR_PROCESSREQUEST] = iRODSMeta(ATTR_PROCESSREQUEST, current_user.username)

    return 'DONE'

@bp.route('_collist')
@login_required
@cache.cached(timeout=60, key_prefix=makekey)
def collist():
    path = request.args.get('path','/', type=str)
    sortkey = request.args.get('sortkey', None, type=str)
    reverse_str = request.args.get('reverse', 'false', type=str)
    new_path_str = request.args.get('new_path', 'true', type=str)
    options = {
        'download_btn': request.args.get('btn_download', 'true', type=str) == 'true',
        'view_btn': request.args.get('btn_view', 'true', type=str) == 'true',
        'delete_btn': request.args.get('btn_del', 'false', type=str) == 'true'
    }

    irods_session = current_user.irods_session

    cols = []
    objs = []

# Look for metadate attrs starting with ngsweb:: on the collection
    q1 = iqry.qcollmeta(path)
    display_settings = { m[CollectionMeta.name][8:] : m[CollectionMeta.value] for m in q1 if m[CollectionMeta.name].startswith('ngsweb::') }

    display_field = display_settings.get('display_field')
    if new_path_str == 'true':
        sortkey = display_settings.get('sort_order', 'name')
        reverse = display_settings.get('sort_reverse', 'false') == 'true'
    else:
        reverse = reverse_str == 'true'

# Query for collection subcollections
    query = iqry.qcollchildren(path)
    for obj in query:
        objdict = {'name': obj[Collection.name].split('/')[-1], 'path': obj[Collection.name]}
        ctime = obj[Collection.create_time]
        ctime = ctime.replace(tzinfo=timezone.utc).astimezone()
        objdict['create_time'] = datafield('create_time', ctime.timestamp(), 'timestamp')
        objdict['owner_name'] = obj[Collection.owner_name]

        objdict['display_field'] = ''
        if display_field:
            df = iqry.qcollmetaval(obj[Collection.name], display_field)
            if df:
                objdict['display_field'] = df

        objdict['type'] = 'unknown'
        dt = iqry.qcollmetaval(obj[Collection.name], 'sys::data::type')
        if dt:
            objdict['type'] = dt
        cols.append(objdict)


# Query for dataobjects in collection
    query = iqry.qcolldataobjects(path)
    for obj in query:
        objdict = {'name': obj[DataObject.name], 'path': '/'.join(
            (path, obj[DataObject.name]))}
        objdict['size'] = obj[DataObject.size]
        ctime = obj[DataObject.create_time]
        ctime = ctime.replace(tzinfo=timezone.utc).astimezone()
        objdict['create_time'] = datafield('create_time', ctime.timestamp(), 'timestamp')
        objdict['owner_name'] = obj[DataObject.owner_name]
        objs.append(objdict)
    
    show_display_field = False
    for i in cols:
        if i['display_field']:
            show_display_field = True

    if cols:
        if sortkey in cols[0]:
            cols.sort(key=lambda x: x[sortkey], reverse=reverse)
    if objs:
        if sortkey in objs[0]:
            objs.sort(key=lambda x: x[sortkey], reverse=reverse)

    return render_template('coll_contents.html', cols=cols, objs=objs, 
                           show=show_display_field, sortkey=sortkey, reverse=reverse,
                           options=options)

def shortname(name,l):
    s = name
    if len(name)>l:
        s = '...' + name[-l+4:]
    return s


def coll_shape(coll_type):
    return COLL_SHAPES.get(coll_type, ('cylinder', 'white'))

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

@bp.route('/_graph')
@login_required
@cache.cached(timeout=60, key_prefix=makekey)
def generate_graph():
    coll = request.args.get('path', '/', type=str)
    graph = Digraph('datagraph')

    def coll_node(coll, pre=None, post=None, center=None, levels=0, history=[], linestyle='solid'):
        if coll in history:
            return True
        history.append(coll)
        collmeta = Dictlist()
        q = iqry.qcollmetadict(coll)
        for m in q:
            collmeta[m] = q[m]

        # create the collection graph node
        coll_type = collmeta.get('sys::data::type', 'unknown')
        coll_type = collmeta.get('user::data::type', coll_type)
        shape, shape_color = coll_shape(coll_type)
        penwidth = '3' if coll == center else '1'
    
        projectid = collmeta.get('projectID', '') + '\n'
        if coll == center:
            penwidth = '3'
            clss = { 'class' : 'path-change center-coll'}
        else:
            penwidth = '1'
            clss = { 'class' : 'path-change' }

        graph.node(coll, projectid + shortname(coll,NAME_LENGTH), shape=shape, fillcolor=shape_color, style='filled', penwidth=penwidth,
                   fontsize='8', setting='extra', **clss, id=coll)
        if post:
            graph.edge(coll, post, style=linestyle)
        # Create the GIT node if present
        left_edge = coll
        git = collmeta.get('sys::pipeline::gitrepo')
        githash = collmeta.get('sys::pipeline::githash')
        if git:
            git_node = 'G-' + coll
            git_url = '{url}/-/tree/{hash}'.format(url=git[:-4] if git.endswith('.git') else git, hash=githash)
            graph.node(git_node, git.split('/')[-1], shape=PROCESS_SHAPE, URL=git_url, fontsize='8')
            graph.edge(git_node, coll)
            left_edge = git_node

        if pre:
            graph.edge(pre, left_edge, style=linestyle)

            # FIND MY INPUT
        input_id =  collmeta.get('sys::pipeline::input_collection_id')
        if input_id:
            q = iqry.qcollbystaticmeta(ATTR_DATASETID, input_id)
            for c in q:
                input_coll = c[Collection.name]
                if levels:
                    coll_node(input_coll, center=center, post=left_edge, levels=levels-1)
                elif not input_coll in history:
                    placeholder = '{}-b'.format(input_coll)
                    graph.node(placeholder, '', shape='none', width='0', height='0')
                    graph.edge(placeholder, left_edge, style='dotted', arrowhead='none')


        # FIND  OUTPUTS
        dataset_id = collmeta.get(ATTR_DATASETID)
        if dataset_id:
            q = iqry.qcollbystaticmeta('sys::pipeline::input_collection_id', dataset_id)
            for c in q:
                output_coll = c[Collection.name]
                if levels:
                    coll_node(output_coll, pre=coll, center=center, levels=levels-1)
                elif not output_coll in history:
                    placeholder = '{}-b'.format(output_coll)
                    graph.node(placeholder, '', shape='none', width='0', height='0')
                    graph.edge(coll, placeholder, style='dotted', arrowhead='none')
        
        if levels:            
            extra_colls = set(collmeta.get_all('user::pipeline::input_collection', []))
            extra_coll_ids = collmeta.get_all('user::pipeline::input_collection_id', [])
            for extra_coll_id in extra_coll_ids:
                q = iqry.qcollbystaticmeta(ATTR_DATASETID, extra_coll_id)
                extra_colls |= { c[Collection.name] for c in q } 
            for extra_coll in extra_colls:
                coll_node(extra_coll, levels=levels-1, post=coll, linestyle='dashed')
            # FIND collections that refer to this collection bij name or id
            q = iqry.qcollbystaticmeta('user::pipeline::input_collection_id', dataset_id)
            ref_colls = { c[Collection.name] for c in q }
            q = iqry.qcollbystaticmeta('user::pipeline::input_collection', coll)
            ref_colls |= { c[Collection.name] for c in q } 
            for ref_coll in ref_colls:
                coll_node(ref_coll, levels=levels-1, pre=coll, linestyle='dashed')




    graph.graph_attr['rankdir'] = 'LR'
    graph.graph_attr['fontsize'] = '15'
    #graph.graph_attr['size'] = '8,10'

    coll_node(coll, center=coll, levels=MAX_GRAPH_LEVELS)

    return graph.pipe(format='svg').decode('utf-8')

@login_required
@cache.memoize(timeout=60)
def add_items(path, level, active):
    
    @cache.memoize(timeout=300)
    def subitems(path):
        count = 0
        query = irods_session.query(Collection.id).filter(
            Criterion('=',Collection.parent_name, path)).count(Collection.id)
        for a in query:
            count = a[Collection.id]
        return count
        
    
    result = ''
    parts = active.split('/')
    irods_session = current_user.irods_session
    query = iqry.qcollchildren(path)
    for coll in query:
        collpath = coll[Collection.name]
        collname = collpath.split('/')[-1]
        if collname:
            c1=' path-active' if collpath == active else '';
            link='<span class="tree-label path-change{}" data-path={}>{}</span>'.format(c1, collpath, collname)
            subtree=''
            dummy=0
            collid=''.join(collpath.split('/'))
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
@cache.cached(timeout=60, key_prefix=makekey)
def colltree():
    active = request.args.get('active', '', type=str)
    current = request.args.get('root', '/', type=str)
    level = 1
    rs = add_items(current, level, active)
    return('<ul id="{}">{}</ul>'.format(current, rs))

def clickable_path(path):
    p = path[1:].split('/')
    cp = ''
    subpath = ''
    for pe in p:
        subpath = '{}/{}'.format(subpath, pe)
        cp = '{}/<a href="{}?path={}">{}</a>'.format(cp, 
                                                     url_for('collbrowser.collbrowser'),
                                                     subpath,
                                                     pe)
    return cp

@bp.route('/')
@login_required
def collbrowser():
    path = request.args.get('path', f'/{current_user.irods_zone}/projects', type=str)
    #path_title = clickable_path(path) 

    return render_template('collbrowser.html', path_title='',
                           path=path, archived=True)


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
    return redirect(url_for('collbrowser.collbrowser') + '?path=' + requestdata['collection'])

@login_required
@bp.route('_deletefile', methods=['POST'])
def delete_file():
    requestdata = request.form.to_dict()
    if 'path' in requestdata:
        path = requestdata['path']
        current_user.ifs.deletefile(path)
    return '', 201


@bp.route('search')
def search():
    return render_template('search.html')


@bp.route('_search', methods=['GET'])
@login_required
def search_result():
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

    #print( f"useExactMatch: {useExactMatch}, useSearchMeta: {useSearchMeta}, useSearchObjectNames: {useSearchObjectNames}" )
    irods_session = current_user.irods_session
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