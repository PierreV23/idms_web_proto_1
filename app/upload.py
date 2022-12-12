#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiemsurveilance data upload interface voor NGSweb
"""

import csv
import io
import os
import shutil
import sys
import logging
import time
from flask import Blueprint, render_template, redirect, request, url_for, session, current_app, flash
from flask import jsonify
from flask_login import current_user, login_required
import uuid
from app import projects, iqry
from app.datafield import datafield
import randomname
import json
import re
from irods.models import Collection, CollectionMeta
from irods.column import Criterion
from irods.meta import iRODSMeta
#from flask_session import Session
from app.irodssessions import irods_manager

ATTR_UPLOAD = 'user::upload'
ATTR_UPLOADNAME = f'{ATTR_UPLOAD}::name'
ATTR_DATASETID = 'sys::dataset_id'
ATTR_UPLOADSETTINGS = 'user::upload::settings::'
ATTR_UPLOADMETA = 'user::upload::meta::'

class UploadType:
    Pending = 'pending'
    Ready = 'ready'
    Done = 'done'

bp = Blueprint('upload', __name__, url_prefix='/upload')

def unique_coll(base_coll, prefix=None, use_date=False):
    """Create a collection with a unique collection name

    The unique name will consist of an optional prefix, an optional date and a number.

    Args:
        base_coll (string): Parent collection of collection name to create
        prefix (string): Prefix for the collection name. If the prefix name alone is unique, it
                        will become the new collection name. If none is supplied, a prefix will be generated
        use_date (boolean): Will append the current date to the suffix

    Returns:
        string: Full irods path to unique collection
    """
    if prefix is None:
        fullprefix = 'dataset' # TODO : generate name (randomname)
    elif prefix == '':
        fullprefix = ''
    else:
        fullprefix = f'{prefix}'

    if use_date:
        datestr = time.strftime('%Y%m%d_%H%M%S')
        if fullprefix:
            fullprefix = f'{fullprefix}_{datestr}'
        else:
            fullprefix = f'{datestr}'
    
    if not fullprefix:
        collname = os.path.join(base_coll,'0000')
    else:
        collname = os.path.join(base_coll, f'{fullprefix}')
        fullprefix = f'{fullprefix}_'
    i = 1
    with irods_manager.session() as session:
        while session.collections.exists(collname):
            collname = os.path.join(projectcoll, f'{fullprefix}{i:04}')
            i += 1
    logging.debug('upload/unique_coll(): mkdir "{}"'.format(collname))
    current_user.ifs.mkdir(collname)
    # TODO : add some metadata?
    return collname


@bp.errorhandler(413)
def too_large(e):
    return "File is too large", 413


@bp.route('show_uploads')
@login_required
def show_uploads():
    return render_template('uploads.html')


# TODO: use the irods_helper instead (role irods_cronjobs)
def getmetaitem(irods_obj, attr, default=None): 
    try:
        value = irods_obj.metadata.get_one(attr).value
    except KeyError:
        value = default
    return value

@bp.route('_pendinguploads')
def pending_uploads():
    state = request.args.get('state', UploadType.Pending)
    pending = []
    with irods_manager.session() as session:
        query = session.query(Collection).filter( \
            Criterion('=', Collection.owner_name, current_user.username)).filter( \
            Criterion('=', CollectionMeta.name, ATTR_UPLOAD)).filter( \
            Criterion('=', CollectionMeta.value, state))
        for c in query:
            coll = c[Collection.name]
            projectID = iqry.qcollmetaval(coll, f'{ATTR_UPLOADSETTINGS}projectID', default='')
            name = iqry.qcollmetaval(coll, ATTR_UPLOADNAME, default=coll)
            name_url = url_for('upload.upload_settings', coll=coll)
            if state == UploadType.Pending:
                namestr = f'<A HREF="{ name_url }">{name}</A>'
            else:
                namestr = name

            pending.append(
                { 'name': namestr,
                'collection':  datafield('collection', coll, 'irods_collection').htmlstring,
                'projectID': datafield('project', projectID, 'projectid').htmlstring
                }
            )
    response = {
        'rows': pending
    }
    return json.dumps(response)

def get_or_set_uid(coll_obj):
    """If the referred collection has no dataset_id, generate one
    Return the dataset_id
    """
    uid = getmetaitem(coll_obj, ATTR_DATASETID)
    if not uid:
        uid = str(uuid.uuid4())
        coll_obj.metadata[ATTR_DATASETID] = iRODSMeta(ATTR_DATASETID, uid)
    return uid

@bp.route('_uploadsettings', methods=['GET', 'POST'])
def upload_settings():
    FIELDS = {
        'projectID':   'Project',
        'collection':  'Collection name',
        'description': 'Description' 
    }
    if request.method == 'GET':
        coll = request.args.get('coll')
        if coll is None:
            return redirect(url_for('upload.show_uploads'))
        name = os.path.basename(coll)
        my_projects = current_user.projects()
        meta = iqry.qcollmetadict(coll)
        data = { k: meta.get(f'{ATTR_UPLOADSETTINGS}{k}', '') for k in FIELDS }
        return render_template('upload_settings.html', name=name, coll=coll, projects=my_projects, fields=FIELDS, data=data)
    if request.method == 'POST':
        data = request.form.to_dict()
        coll = data.get('coll')
        for k, v in data.items():
            if k in FIELDS and v:
                iqry.scollmetaval(coll, f'{ATTR_UPLOADSETTINGS}{k}', v)
        if data.get('submitbutton', 'save') == 'next':
            return redirect(url_for('upload.upload_meta', coll=coll))
        else:
            return redirect(url_for('upload.upload_settings', coll=coll))

@bp.route('_uploadmeta', methods=['GET', 'POST'])
def upload_meta():
    if request.method == 'GET':
        collection = request.args.get('coll')
        name = os.path.basename(collection)
        if collection is None:
            return redirect(url_for('upload.show_uploads'))
        with open('schema.json') as f:
            schema =  f.read()
        metadata = iqry.qcollmetadict(collection)
        data = { k[len(ATTR_UPLOADMETA):]: v for k, v in metadata.items() if k.startswith(ATTR_UPLOADMETA) }
        return render_template('upload_meta.html', coll=collection, name=name, schema=schema, data=data)
    if request.method == 'POST':
        record = request.json
        collection = record.get('coll')
        metadata = iqry.qcollmetadict(collection)
        for k, v in metadata.items():
            if k.startswith(ATTR_UPLOADMETA):
                iqry.delcollmeta(collection, k, v)
        for k, v in record.get('data', {}).items():
            iqry.scollmetaval(collection, f'{ATTR_UPLOADMETA}{k}', v)                
        return jsonify({'status': 'OK' }), 200


@bp.route('_uploaddata', methods=['GET', 'POST'])
def upload_data():
    if request.method == 'GET':
        coll = request.args.get('coll')
        name = os.path.basename(coll)
        return render_template('upload_data.html', name=name, coll=coll)
    if request.method == 'POST':
        f = request.files['file']
        data = request.form.to_dict()
        coll = data.get('coll', '/')
        fullPath = data.get('fullPath', f.filename)
        if fullPath == 'undefined':
            fullPath = f.filename
        filename = os.path.join(coll, fullPath)
        filepath = os.path.dirname(filename)
        if not current_user.ifs.folderexists(filepath):
            current_user.ifs.mkdir(filepath)
        with current_user.ifs.open(filename, 'w') as d:
            shutil.copyfileobj(f, d)
        iqry.invalidate(coll)
        return 'OK'

@bp.route('_actions', methods=['GET'])
def upload_actions():
    action = request.args.get('action')
    coll = request.args.get('coll')
    if action == 'finalize':
        iqry.scollmetaval(coll, ATTR_UPLOAD, UploadType.Ready)
        return redirect(url_for('upload.show_uploads'))
    elif action == 'cancel':
        current_user.ifs.rmdir(coll, recurse=True, force=True)
        return redirect(url_for('upload.show_uploads'))
    flash(f'Unknown request: {action}', 'error')
    return redirect(url_for('upload.upload_settings', coll=coll))




@bp.route('newupload')
def new_upload():
    # Create an upload-collection
    # First generate a unique upload name
    unique = False 
    while not unique:
        name = randomname.get_name()
        with irods_manager.session() as session:
            q = session.query(CollectionMeta.value).filter(\
                Criterion('=', CollectionMeta.name, ATTR_UPLOADNAME)).filter(\
                Criterion('=', CollectionMeta.value, name))
            unique = q.execute().length == 0

    # Now generate a collection for the upload
    coll = unique_coll(os.path.join('/', current_user.irods_zone, 'home', current_user.username), prefix=name)
    with irods_manager.session() as session:
        collobj = session.collections.get(coll)   
        get_or_set_uid(collobj)
        iqry.scollmetaval(coll, ATTR_UPLOADNAME, name)
        iqry.scollmetaval(coll, ATTR_UPLOAD, UploadType.Pending)

    return redirect(url_for('upload.upload_settings', coll=coll ))

@bp.route('_posttest', methods=['POST'])
def posttest():
    return 'OK', 200

