#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 10:54:56 2019

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject
from irods.column import Criterion
from app.formatting import AVU
from graphviz import Graph, Digraph
import base64

bp = Blueprint('collbrowser', __name__, url_prefix='/collbrowser')

NAME_LENGTH = 20

def collist(path):
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
        avu[name] = AVU(name, value, units)

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
            #print("m[CollectionMeta.value]:", m[CollectionMeta.value])

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
    return cols, objs, avu

def shortname(name,l):
    s = name
    if len(name)>l:
        s = '...' + name[-l+4:]
    return s

@login_required
def generate_graph(coll, related_colls, meta):
    irods_session = current_user.irods_session
    graph = Digraph('datagraph')
    graph.graph_attr['rankdir'] = 'LR'
    graph.graph_attr['fontsize'] = '15'
    projID = meta['projectID'].value + '\n' if 'projectID' in meta else '' 
    graph.node('A', projID + shortname(coll,NAME_LENGTH), style='filled')
    print(meta)
    parent = 'A'
    if 'sys::pipeline::gitrepo' in meta:
        git = str(meta['sys::pipeline::gitrepo'])
        graph.node('G', git.split('/')[-1], shape='box', URL=git, fontsize='8')
        graph.edge('G', 'A')
        parent = 'G'
    if 'sys::pipeline::input_collection' in meta:
        inp = str(meta['sys::pipeline::input_collection'])
        project = ''
        query = irods_session.query(CollectionMeta.value).filter(
                Criterion('=', Collection.name, inp)).filter(
                        Criterion('=', CollectionMeta.name, 'projectID'))
        for c in query:
            project = c[CollectionMeta.value] + ':\n'
        graph.node('S', project + shortname(inp, NAME_LENGTH), URL=url_for('collbrowser.collbrowser') + '?path=' + inp, fontsize='8')
        graph.edge('S', parent)
    elif 'sourceid' in meta:        
        inst = meta['Instrument'].value if 'Instrument' in meta else 'unknown'
        graph.node('SEQ', '{}\n{}'.format(meta['sourceid'].value, inst), shape='hexagon', fontsize='8')
        graph.edge('SEQ', parent)
    i=0
    for rc in related_colls:
        print(rc)
        parent = 'A'
        query = irods_session.query(CollectionMeta.value).filter(
                Criterion('=', Collection.name, rc)).filter(
                        Criterion('=', CollectionMeta.name, 'sys::pipeline::gitrepo'))
        for c in query:
            git = c[CollectionMeta.value]
            graph.node('G2', git.split('/')[-1], shape='box', URL=git, fontsize='8')
            graph.edge('A', 'G2')
            parent = 'G2'
        project = ''
        query = irods_session.query(CollectionMeta.value).filter(
                Criterion('=', Collection.name, rc)).filter(
                        Criterion('=', CollectionMeta.name, 'projectID'))
        for c in query:
            project = c[CollectionMeta.value] + ':\n'
        graph.node(str(i), project + shortname(rc, NAME_LENGTH), URL=url_for('collbrowser.collbrowser') + '?path=' + rc, fontsize='8')
        graph.edge(parent, str(i))
        i+=1
    return graph

@bp.route('/')
@login_required
def collbrowser():
    #print(current_user)
    path = request.args.get('path', '/rivmZone/projects', type=str)
    action = request.args.get('action', 'none', type=str)
    sortkey = request.args.get('sortkey', 'name', type=str)
    reverse = request.args.get('reverse', 'false', type=str)

    if action == "up":
        path = '/' + '/'.join(path.split('/')[1:-1])

    irods_session = current_user.irods_session
    
    # Find related collections
    query = irods_session.query(Collection.name).filter(
        Criterion('=', CollectionMeta.name, 'sys::pipeline::input_collection')).filter(
            Criterion('=', CollectionMeta.value, path))
    rel_colls = [c[Collection.name] for c in query]

    # Find subcollections, objects and metadata
    c, o, a = collist(path)

    show_description = (max([0] + [len(i['coll_description']) for i in c]) > 0)

    # Generate the graph
    graph_data = generate_graph(path, rel_colls, a)
    
    graph_output = graph_data.pipe(format='png')
    graph_imagemap = graph_data.pipe(format='cmapx').decode('utf-8')
    data_graph = base64.b64encode(graph_output).decode('utf-8')

    breverse = bool(reverse == 'true')
    if c:
        if sortkey in c[0]:
            c.sort(key=lambda x: x[sortkey], reverse=breverse)
    if o:
        if sortkey in o[0]:
            o.sort(key=lambda x: x[sortkey], reverse=breverse)
    return render_template('collbrowser.html', cols=c, objs=o, avu=a,
                           path=path, rel_colls=rel_colls,
                           show=show_description,
                           data_graph=data_graph, data_map=graph_imagemap)


@bp.route('upload_file', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        requestdata = request.form.to_dict()
        print('R ', requestdata)
        f = request.files['file']
        # Generate irods file object
        iObjName = requestdata['collection'] + '/' + f.filename
        iObj = current_user.ifs.open(iObjName, 'w')
        f.save(iObj)
        iObj.close()
    return redirect(url_for('collbrowser.collbrowser') + '?path=' + requestdata['collection'])
