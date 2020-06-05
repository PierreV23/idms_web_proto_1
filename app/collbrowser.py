#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 10:54:56 2019

@author: wierinve
"""

import base64
import os
from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject
from irods.column import Criterion
from app.datafield import AVU2data
from graphviz import Digraph

bp = Blueprint('collbrowser', __name__, url_prefix='/collbrowser')

NAME_LENGTH = 20
MAX_GRAPH_LEVELS = 4
ATTR_DATASETID = 'sys::dataset_id'

COLL_SHAPES = {
    'valid':      ('box3d', 'springgreen1'),
    'invalid':    ('box3d', 'tomato'),
    'imported':   ('cylinder', 'skyblue1'),
    'temporary':  ('note',  'gold2'),
    'distributed':('box3d','springgreen1:gray'),
    'unknown'    :('ellipse', 'gray')}

PROCESS_SHAPE = 'cds'

@bp.route('_meta')
@login_required
def coll_meta():
    path = request.args.get('path','/', type=str)
    irods_session = current_user.irods_session
    avu = {}
# Query for collection metadata
    query = irods_session.query(CollectionMeta.name, CollectionMeta.value,
                                CollectionMeta.units).filter(
                                    Criterion('=', Collection.name, path))
    for coll_metadata in query:
        name = coll_metadata[CollectionMeta.name]
        value = coll_metadata[CollectionMeta.value]
        units = coll_metadata[CollectionMeta.units]
        avu_id = '{}_{}'.format(name, value)
        avu[avu_id] = AVU2data(name, value, units)
        
    return render_template('metadata.html', avu=avu)

@bp.route('_collist')
@login_required    
def collist():
    path = request.args.get('path','/', type=str)
    sortkey = request.args.get('sortkey', 'name', type=str)
    reverse = request.args.get('reverse', 'false', type=str)

    irods_session = current_user.irods_session

    cols = []
    objs = []

# Query for collection subcollections
    query = irods_session.query(Collection.id,
                                Collection.name,
                                Collection.create_time,
                                Collection.owner_name).filter( \
        Criterion('like', Collection.parent_name, path))
    for obj in query:
        objdict = {'name': obj[Collection.name].split('/')[-1], 'path': obj[Collection.name]}
        objdict['create_time'] = obj[Collection.create_time]
        objdict['owner_name'] = obj[Collection.owner_name]

        q1 = irods_session.query(CollectionMeta.value).filter( \
            Criterion('=', Collection.id, obj[Collection.id])).filter( \
            Criterion('=', CollectionMeta.name, 'coll_description'))
        objdict['coll_description'] = ''
        for m in q1:
            objdict['coll_description'] = m[CollectionMeta.value]

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
        objdict['create_time'] = obj[DataObject.create_time]
        objdict['owner_name'] = obj[DataObject.owner_name]
        objs.append(objdict)
        
    show_description = (max([0] + [len(i['coll_description']) for i in cols]) > 0)

    breverse = bool(reverse == 'true')
    if cols:
        if sortkey in cols[0]:
            cols.sort(key=lambda x: x[sortkey], reverse=breverse)
    if objs:
        if sortkey in objs[0]:
            objs.sort(key=lambda x: x[sortkey], reverse=breverse)

    return render_template('coll_contents.html', cols=cols, objs=objs, 
                           show=show_description, sortkey=sortkey, reverse=breverse)

def shortname(name,l):
    s = name
    if len(name)>l:
        s = '...' + name[-l+4:]
    return s


def coll_shape(coll_type):
    return COLL_SHAPES.get(coll_type, ('cylinder', 'white'))

@bp.route('/_graph')
@login_required
def generate_graph():
    coll = request.args.get('path', '/', type=str)
    irods_session = current_user.irods_session
    graph = Digraph('datagraph')

    def coll_node(coll, pre=None, center=None, levels=0):
        query = irods_session.query(CollectionMeta.name, CollectionMeta.value).filter(
                Criterion('=', Collection.name, coll))
        collmeta = {m[CollectionMeta.name]: m[CollectionMeta.value] for m in query}
        coll_type = collmeta.get('sys::data::type', 'unknown')
        shape, shape_color = coll_shape(coll_type)
        penwidth = '2' if coll == center else '1'
        projectid = collmeta.get('projectID', '') + '\n'
        graph.node(coll, projectid + shortname(coll,NAME_LENGTH), shape=shape, fillcolor=shape_color, style='filled', penwidth=penwidth,
                   URL=url_for('collbrowser.collbrowser') + '?path=' + coll, fontsize='8')
        if pre:
            git = collmeta.get('sys::pipeline::gitrepo')
            githash = collmeta.get('sys::pipeline::githash')
            if git:
                git_node = 'G-' + coll
                git_url = '{url}/tree/{hash}'.format(url=git[:-4] if git.endswith('.git') else git, hash=githash)
                graph.node(git_node, git.split('/')[-1], shape=PROCESS_SHAPE, URL=git_url, fontsize='8')
                graph.edge(pre, git_node)
                graph.edge(git_node, coll)
            else:
                graph.edge(pre, coll)
        if levels:
            dataset_id = collmeta.get('sys::dataset_id')
            if dataset_id:
                q = irods_session.query(Collection.name).filter(
                        Criterion('=', CollectionMeta.name, 'sys::pipeline::input_collection_id')).filter(
                        Criterion('=', CollectionMeta.value, dataset_id))
                for c in q:
                    coll_node(c[Collection.name], pre=coll, center=center, levels=levels-1)

    def parent(coll):
        coll_parent = None
        parent_id = None
        q = irods_session.query(CollectionMeta.value).filter(
            Criterion('=', Collection.name, coll)).filter(
            Criterion('=', CollectionMeta.name, 'sys::pipeline::input_collection_id'))
        for p in q:
            parent_id = p[CollectionMeta.value]
        if parent_id:
            q = irods_session.query(Collection.name).filter(
                Criterion('=', CollectionMeta.name, 'sys::dataset_id')).filter(
                Criterion('=', CollectionMeta.value, parent_id))
            for n in q:
                coll_parent = n[Collection.name]
        return coll_parent


    graph.graph_attr['rankdir'] = 'LR'
    graph.graph_attr['fontsize'] = '15'
    graph.graph_attr['size'] = '10,8'

    base_coll = coll
    levels = MAX_GRAPH_LEVELS
    level = levels-1
    while level:
        p = parent(base_coll)
        if p:
            base_coll = p
        level -= 1

    coll_node(base_coll, center=coll, levels=levels)

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
    path = request.args.get('path', '/rivmZone/projects', type=str)
    path_title = clickable_path(path) 
    

    # Find subcollections, objects
    # c, o = collist(path)

    # Find related collections
    rel_colls = []
    # if ATTR_DATASETID in a:
    #     print('Search related collections')
    #     query = irods_session.query(Collection.name).filter(
    #         Criterion('=', CollectionMeta.name, 'sys::pipeline::input_collection_id')).filter(
    #             Criterion('=', CollectionMeta.value, a[ATTR_DATASETID].value))
    #     rel_colls = [c[Collection.name] for c in query]


    # Generate the graph
    #graph_data = generate_graph(path)

    #graph_output = graph_data.pipe(format='png')
    #graph_imagemap = graph_data.pipe(format='cmapx').decode('utf-8')
    #data_graph = base64.b64encode(graph_output).decode('utf-8')

    return render_template('collbrowser.html', path_title=path_title,
                           path=path)


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
