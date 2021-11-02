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
from graphviz import Digraph
from irods.meta import iRODSMeta
from . import projects
#from irods_helper import getmetaitem

bp = Blueprint('collbrowser', __name__, url_prefix='/collbrowser')

NAME_LENGTH = 20
MAX_GRAPH_LEVELS = 3
ATTR_DATASETID = 'sys::dataset_id'
ATTR_PROJECTID = 'projectID'
ATTR_PROCESSID = 'processID'
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
def getmetaitem(irods_obj, attr, default=None): 
    try:
        value = irods_obj.metadata.get_one(attr).value
    except KeyError:
        value = default
    return value

def getmetatree(irods_obj, attr, default=None):
    return  _getmetatree(irods_obj, attr, irods_obj.path, default=None)

@login_required
def _getmetatree(irods_obj, attr, base, default=None):
    value = getmetaitem(irods_obj, attr, default=None)
    if value is not None:
        return value, datafield('collection', irods_obj.path, 'irods_collection'), irods_obj.path == base
    if irods_obj.path != '/':
        parent = current_user.irods_session.collections.get(os.path.dirname(irods_obj.path))
        return _getmetatree(parent, attr, base, default=None)
    return default, None, True

@bp.route('_meta')
@login_required
def coll_meta():
    path = request.args.get('path','/', type=str)
    object = request.args.get('object', '', type=str)
    irods_session = current_user.irods_session
# Query for collection metadata
    coll_avu = []
    query = irods_session.query(CollectionMeta.name, CollectionMeta.value,
                                CollectionMeta.units).filter(
                                    Criterion('=', Collection.name, path))
     # TODO: why not use a simple list of AVUs here? The template is not accessing the dictionary by key anyway...
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
    delta = relativedelta(days=0)
    if selectionStr == '1w':
        delta = relativedelta(days=7)
    elif selectionStr == '1M':
        delta = relativedelta(months=1)
    elif selectionStr == '6M':
        delta = relativedelta(months=6)
    else:
        print( f"unknown selection for _setKeepOnlineUntil: {selectionStr}")
        return('DONE')
    keepOnlineUntil = now + delta

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
def coll_actions():
    path = request.args.get('path','/', type=str)
    coll_name = path.split('/')[-1]
    irods_session = current_user.irods_session

    coll_obj = irods_session.collections.get(path)
    is_dataset = getmetaitem(coll_obj, ATTR_DATASETID, "") != ""
    keep_local = getmetatree(coll_obj, ATTR_ARCHIVE_LOCAL, False)
    online_percentage = int(getmetaitem(coll_obj, ATTR_ARCHIVE_ONLINEPERCENTAGE, 0 ))
    archive_state = getmetaitem(coll_obj, ATTR_ARCHIVE_STATE, "000")
    min_copies = getmetatree(coll_obj, ATTR_ARCHIVE_MINCOPIES, 2)
    keep_online = getmetatree(coll_obj, ATTR_ARCHIVE_KEEP_ONLINE, "false")
    is_archived = False 
    if archive_state[-1] == '1':
        is_archived = True 
    is_offline = False
    if archive_state[:2] == '00':
        is_offline = True

    projectid = getmetaitem(coll_obj, ATTR_PROJECTID, "")
    processid = getmetaitem(coll_obj, ATTR_PROCESSID, "")
    processes = projects.get_processlist(projectid)
    processrequest = getmetaitem(coll_obj, ATTR_PROCESSREQUEST, "false")
    start_next_process = getmetaitem(coll_obj, USER_PIPELINE_AUTOSTART, "true")

    archival_state = {
        "enabled": getmetaitem(coll_obj, ATTR_ARCHIVE_ENABLE, "false"),
        "is_dataset": is_dataset,
        "is_archived": is_archived,
        "is_offline": is_offline,
        "keep_local": keep_local,
        "online_percentage": online_percentage,
        "min_copies": min_copies,
        "keep_online": keep_online
    }

    #print( archival_state )
    return render_template('actions.html', collection=path, 
        name=coll_name, archival_state=archival_state,
        processes=processes, processid=processid, processrequest=processrequest, start_next_process=start_next_process )


@bp.route('_startprocess')
@login_required
def startprocess():
    collection = request.args.get('collection')
    processid = request.args.get('processid')
    if current_user.ifs.folderexists(collection):
        c = current_user.irods_session.collections.get(collection)
        c.metadata[ATTR_PROCESSID] = iRODSMeta(ATTR_PROCESSID, processid)
        c.metadata[ATTR_PROCESSREQUEST] = iRODSMeta(ATTR_PROCESSREQUEST, current_user.username)
    return 'DONE'

@bp.route('_collist')
@login_required    
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
    q1 = irods_session.query(CollectionMeta.name, CollectionMeta.value).filter( \
        Criterion('=', Collection.name, path)).filter( \
        Criterion('like', CollectionMeta.name, 'ngsweb::%'))
    display_settings = { m[CollectionMeta.name][8:] : m[CollectionMeta.value] for m in q1 }

    display_field = display_settings.get('display_field')
    if new_path_str == 'true':
        sortkey = display_settings.get('sort_order', 'name')
        reverse = display_settings.get('sort_reverse', 'false') == 'true'
    else:
        reverse = reverse_str == 'true'

# Query for collection subcollections
    query = irods_session.query(Collection.id,
                                Collection.name,
                                Collection.create_time,
                                Collection.owner_name).filter( \
        Criterion('like', Collection.parent_name, path))
    for obj in query:
        objdict = {'name': obj[Collection.name].split('/')[-1], 'path': obj[Collection.name]}
        ctime = obj[Collection.create_time]
        ctime = ctime.replace(tzinfo=timezone.utc).astimezone()
        objdict['create_time'] = datafield('create_time', ctime.timestamp(), 'timestamp')
        objdict['owner_name'] = obj[Collection.owner_name]

        objdict['display_field'] = ''
        if display_field:
            q1 = irods_session.query(CollectionMeta.value).filter( \
                Criterion('=', Collection.id, obj[Collection.id])).filter( \
                Criterion('=', CollectionMeta.name, display_field))
            for m in q1:
                objdict['display_field'] = m[CollectionMeta.value]

        q2 = irods_session.query(CollectionMeta.value).filter( \
            Criterion('=', Collection.id, obj[Collection.id])).filter( \
            Criterion('=', CollectionMeta.name, 'sys::data::type'))
        objdict['type'] = 'unknown'
        for m in q2:
            objdict['type'] = m[CollectionMeta.value]
        cols.append(objdict)


# Query for dataobjects in collection
    query = irods_session.query(Collection.name,
                                DataObject.name,
                                DataObject.owner_name,
                                DataObject.size).min(
                                    DataObject.create_time).filter( \
                                        Criterion('like', Collection.name, path))
    for obj in query:
        objdict = {'name': obj[DataObject.name], 'path': '/'.join(
            (obj[Collection.name], obj[DataObject.name]))}
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
def generate_graph():
    coll = request.args.get('path', '/', type=str)
    irods_session = current_user.irods_session
    graph = Digraph('datagraph')

    def coll_node(coll, pre=None, post=None, center=None, levels=0, history=[], linestyle='solid'):
        if coll in history:
            return True
        history.append(coll)
        collmeta = Dictlist()
        query = irods_session.query(CollectionMeta.name, CollectionMeta.value).filter(
                Criterion('=', Collection.name, coll))
        for m in query:
            collmeta[m[CollectionMeta.name]] = m[CollectionMeta.value]

        # create the collection graph node
        coll_type = collmeta.get('sys::data::type', 'unknown')
        coll_type = collmeta.get('user::data::type', coll_type)
        shape, shape_color = coll_shape(coll_type)
        penwidth = '3' if coll == center else '1'
    
        projectid = collmeta.get('projectID', '') + '\n'
        graph.node(coll, projectid + shortname(coll,NAME_LENGTH), shape=shape, fillcolor=shape_color, style='filled', penwidth=penwidth,
                   URL=url_for('collbrowser.collbrowser') + '?path=' + coll, fontsize='8')
        if post:
            graph.edge(coll, post, style=linestyle)
        # Create the GIT node if present
        left_edge = coll
        git = collmeta.get('sys::pipeline::gitrepo')
        githash = collmeta.get('sys::pipeline::githash')
        if git:
            git_node = 'G-' + coll
            git_url = '{url}/tree/{hash}'.format(url=git[:-4] if git.endswith('.git') else git, hash=githash)
            graph.node(git_node, git.split('/')[-1], shape=PROCESS_SHAPE, URL=git_url, fontsize='8')
            graph.edge(git_node, coll)
            left_edge = git_node

        if pre:
            graph.edge(pre, left_edge, style=linestyle)

            # FIND MY INPUT
        input_id =  collmeta.get('sys::pipeline::input_collection_id')
        if input_id:
            q = irods_session.query(Collection.name).filter(
                    Criterion('=', CollectionMeta.name, ATTR_DATASETID)).filter(
                    Criterion('=', CollectionMeta.value, input_id))
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
            q = irods_session.query(Collection.name).filter(
                    Criterion('=', CollectionMeta.name, 'sys::pipeline::input_collection_id')).filter(
                    Criterion('=', CollectionMeta.value, dataset_id))
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
                q = irods_session.query(Collection.name).filter(
                    Criterion('=', CollectionMeta.name, ATTR_DATASETID)).filter(
                    Criterion('=', CollectionMeta.value, extra_coll_id))
                extra_colls |= { c[Collection.name] for c in q } 
            for extra_coll in extra_colls:
                coll_node(extra_coll, levels=levels-1, post=coll, linestyle='dashed')
            # FIND collections that refer to this collection bij name or id
            q = irods_session.query(Collection.name).filter(\
                    Criterion('=', CollectionMeta.name, 'user::pipeline::input_collection_id')).filter( \
                    Criterion('=', CollectionMeta.value, dataset_id))
            ref_colls = { c[Collection.name] for c in q }
            q = irods_session.query(Collection.name).filter(\
                    Criterion('=', CollectionMeta.name, 'user::pipeline::input_collection')).filter( \
                    Criterion('=', CollectionMeta.value, coll))
            ref_colls |= { c[Collection.name] for c in q } 
            for ref_coll in ref_colls:
                coll_node(ref_coll, levels=levels-1, pre=coll, linestyle='dashed')




    graph.graph_attr['rankdir'] = 'LR'
    graph.graph_attr['fontsize'] = '15'
    graph.graph_attr['size'] = '10,8'

    coll_node(coll, center=coll, levels=MAX_GRAPH_LEVELS)

    graph_output = graph.pipe(format='png')
    graph_imagemap = graph.pipe(format='cmapx').decode('utf-8')
    data_graph = base64.b64encode(graph_output).decode('utf-8')
    result = {}
    result['graph'] = data_graph
    result['map'] = graph_imagemap
    return result

@login_required
def add_items(path, level, active):
    
    def subitems(path):
        count = 0
        query = irods_session.query(Collection.id).filter(
            Criterion('=',Collection.parent_name, path)).count(Collection.id)
        for a in query:
            count = a[Collection.id]
        return count
        
    
    result = ''
    print(path, level, active)
    parts = active.split('/')
    irods_session = current_user.irods_session
    query = irods_session.query(Collection.name).filter(
        Criterion('=', Collection.parent_name, path))
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
    path_title = clickable_path(path) 

    return render_template('collbrowser.html', path_title=path_title,
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
        print(f'DELETE {path}')
        current_user.ifs.deletefile(path)
    return '', 201
