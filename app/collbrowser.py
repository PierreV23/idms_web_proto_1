#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 10:54:56 2019

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user, current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject
from irods.column import Criterion
from app.formatting import format_value
import fs_irods

bp = Blueprint('collbrowser', __name__, url_prefix='/collbrowser')

def collist(path):
    irods_session = current_user.irods_session
    ifs = current_user.ifs
    avu=[]
# Query for collection metadata
    query = irods_session.query(CollectionMeta.name, CollectionMeta.value, CollectionMeta.units).filter(Criterion('=', Collection.name, path))
    for coll_metadata in query:
         name = coll_metadata[CollectionMeta.name]
         value = coll_metadata[CollectionMeta.value]
         units = coll_metadata[CollectionMeta.units]
         avu.append({'name': name, 'value': value,'units': units, 'formatted_value': format_value(name, value, units)})
         #print('AVU',name,value,units)
    
    cols = []
    objs = []

# Query for collection subcollections
    query = irods_session.query(Collection.id, Collection.name, Collection.create_time, Collection.owner_name).filter( \
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
    query = irods_session.query(Collection.name, DataObject.name, DataObject.owner_name, DataObject.size).min(DataObject.create_time).filter( \
        Criterion('like', Collection.name, path))
    for obj in query:
        objdict = {'name': obj[DataObject.name], 'path': '/'.join((obj[Collection.name], obj[DataObject.name])) }     
        objdict['size'] = obj[DataObject.size]
        objdict['create_time'] = obj[DataObject.create_time]
        objdict['owner_name'] = obj[DataObject.owner_name]
        objs.append(objdict)
    return cols, objs, avu

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
    query = irods_session.query(Collection.name).filter(
            Criterion('=', CollectionMeta.name, 'sys::pipeline::input_collection')).filter(
                    Criterion('=', CollectionMeta.value, path))
    rel_colls = [ c[Collection.name] for c in query]

    c, o, a = collist(path)
    
    show_description = (max([0] + [len(i['coll_description']) for i in c]) > 0)

    if reverse == 'true':
        breverse = True
    else:
        breverse = False
    if len(c)>0:
        if sortkey in c[0]:
            c.sort(key =  lambda x: x[sortkey], reverse = breverse)
    if len(o)>0:
        if sortkey in o[0]:
            o.sort(key =  lambda x: x[sortkey], reverse = breverse)
    return render_template('collbrowser.html', cols = c, objs = o, avu = a, path=path, rel_colls = rel_colls, show = show_description)


@bp.route('upload_file', methods = ['GET', 'POST'])
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
        iObj.close
    return redirect(url_for('collbrowser.collbrowser') + '?path=' + requestdata['collection'])

