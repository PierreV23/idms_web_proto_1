#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data upload interface voor NGSweb
"""

import os
from flask import Blueprint, render_template, redirect, request, url_for, session
from flask_login import current_user, login_required
import uuid
from app import projects

UPLOAD_KEY = 'current_upload'
DEFAULT_UPLOAD = {
    'collection': None,
    'project': None,
    'filelist': []
}

bp = Blueprint('upload', __name__, url_prefix='/upload')

@bp.errorhandler(413)
def too_large(e):
    return "File is too large", 413

@bp.route('upload')
def upload_page():
    # Find out if an upload is still in progress
    if UPLOAD_KEY not in session:
        session[UPLOAD_KEY] = DEFAULT_UPLOAD
        session[UPLOAD_KEY]['collection'] = f'/rivmZone/upload/{uuid.uuid4()}'
    projectlist = projects.get_projectlist()
    return render_template('upload.html', upload_data=session[UPLOAD_KEY], projectlist=projectlist)

@login_required
@bp.route('_uploadfile', methods=['POST'])
def upload_file():
    f = request.files['file']
    print(f'upload_file {f.filename}')
    collection = session[UPLOAD_KEY]['collection']
    if not current_user.ifs.folderexists(collection):
        current_user.ifs.mkdir(collection)
    # Generate irods file object
    iObjName = os.path.join(session[UPLOAD_KEY]['collection'], f.filename)
    iObj = current_user.ifs.open(iObjName, 'w')
    f.save(iObj)
    iObj.close()
    print('upload_file')
    return '', 204

@login_required
@bp.route('_cancelupload', methods=['GET'])
def cancel_upload():
    if UPLOAD_KEY in session:
        collection =  session[UPLOAD_KEY].get('collection')
        if collection:
            current_user.ifs.rmdir(collection)
    del session[UPLOAD_KEY]
    return render_template('home.html')

