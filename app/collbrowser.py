#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 10:54:56 2019

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user, current_user, login_required
from irods.models import Collection, CollectionMeta
from irods.column import Criterion
import fs_irods

bp = Blueprint('collbrowser', __name__, url_prefix='/collbrowser')

def collist(path):
    irods_session = current_user.irods_session
    ifs = current_user.ifs
    avu=[]
    query = irods_session.query(CollectionMeta.name, CollectionMeta.value, CollectionMeta.units).filter(Criterion('=', Collection.name, path))
    for result in query:
         name = result[CollectionMeta.name]
         value = result[CollectionMeta.value]
         units = result[CollectionMeta.units]
         avu.append({'name': name, 'value': value,'units': units})
         print('AVU',name,value,units)
    cols = []
    objs = []
    for obj in ifs.ls(path):
        objdict = {'name': obj.shortname(), 'path': obj.path}
        if obj.isdir():
            query = irods_session.query(Collection.create_time, Collection.owner_name).filter(Criterion('=', Collection.name, obj.path))
            for result in query:
                ct = result[Collection.create_time]
                on = result[Collection.owner_name]
                objdict['datetime'] = ct
                objdict['ownername'] = on
            cols.append(objdict)
            #print ("cols is nu:", cols)
        else:
            objdict['size'] = obj.filesize()
            objdict['create_time'] = obj.create_time()
            objdict['owner_name'] = obj.owner_name()
            objs.append(objdict)
    print("path: ", path)
    print("cols: ", cols)
    print("objs: ", objs)
    return cols, objs, avu

@bp.route('/')
@login_required
def collbrowser():
    print(current_user)
    path = request.args.get('path', '/rivmZone/projects', type=str)
    action = request.args.get('action', 'none', type=str)
    if action == "up":
        path = '/' + '/'.join(path.split('/')[1:-1])
        
    irods_session = current_user.irods_session       
    query = irods_session.query(Collection.name).filter(
            Criterion('=', CollectionMeta.name, 'sys::pipeline::input_collection')).filter(
                    Criterion('=', CollectionMeta.value, path))
    rel_colls = [ c[Collection.name] for c in query]
    print("rel_cols", rel_colls)

    c, o, a = collist(path)
    return render_template('collbrowser.html', cols = c, objs = o, avu = a, path=path, rel_colls = rel_colls)


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

