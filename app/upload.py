#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiemsurveilance data upload interface voor NGSweb
"""

import csv
import io
import os
import time
from flask import Blueprint, render_template, redirect, request, url_for, session, current_app
from flask import jsonify
from flask_login import current_user, login_required
import uuid
from app import projects
from Bio import SeqIO
import openpyxl

from labsurv import KSUpload, KSUploadType, connect

SAMPLEID = 'SendingOrganisationSampleId'

UPLOAD_KEY = 'current_upload'
DEFAULT_UPLOAD = {
    'collection': None,
    'project': None,
    'filelist': []
}

bp = Blueprint('upload', __name__, url_prefix='/upload')

@login_required
def unique_coll(project):
    """Generate a unique collection name for project
    and create the collection"""
    projectcoll = f'/{current_user.irods_zone}/upload/data'

    if not project is None:
        pl, result = projects.rest_call('GET', 'projects/{}'.format(project))
        if 'default_collection' in pl:
            projectcoll = pl['default_collection']
    datestr = time.strftime('%Y%m%d_%H%M')
    collname = os.path.join(projectcoll, datestr)
    i = 0
    while current_user.irods_session.collections.exists(collname):
        collname = os.path.join(projectcoll, f'{datestr}_{i:04}')
        i += 1
    current_user.ifs.mkdir(collname)
    # TODO : add some metadata?
    return collname

def upload_data():
    if current_user.environment not in session:
        session[current_user.environment] = {}
    if not UPLOAD_KEY in session[current_user.environment]:
        session[current_user.environment][UPLOAD_KEY] = DEFAULT_UPLOAD
        update_setting('collection', f'/{current_user.irods_zone}/upload/{uuid.uuid4()}')
    return session[current_user.environment][UPLOAD_KEY]

def update_setting(key, value):
    settings = upload_data()
    session[current_user.environment][UPLOAD_KEY][key] = value
    session.modified = True

def clear_upload():
    if current_user.environment in session:
        if UPLOAD_KEY in session[current_user.environment]:
            collection =  session[current_user.environment][UPLOAD_KEY].get('collection')
            if collection:
                current_user.ifs.rmdir(collection, recurse=True, force=True)
            del session[current_user.environment][UPLOAD_KEY]
    session.modified = True


@bp.errorhandler(413)
def too_large(e):
    return "File is too large", 413

@bp.route('upload')
def upload_page():
    # Find out if an upload is still in progress
    projectlist = projects.get_projectlist()
    return render_template('upload.html', upload_data=upload_data(), projectlist=projectlist)

def LengthWithinMargin(seq):

    MinLength = 29603
    MaxLength = 30203
    return MinLength < len(seq) < MaxLength


def HasTooManyN(seq):
    count = seq.lower().count("n")
    if count >= 2990:
        return True
    if count < 2990:
        return False

def read_data(coll):
    data = {}
    headers = []
    for f in current_user.ifs.ls(coll):
        if f.isfile():
            if f.path.endswith('.fasta'):
                fasta = f.open('r')
                wrapper = io.TextIOWrapper(fasta, encoding='utf-8')
                for seq in SeqIO.parse(wrapper, 'fasta'):
                    data.setdefault(seq.id, { 
                        'PassedQC': 'No' if HasTooManyN(seq.seq) else 'Yes',
                        'LengthOK': 'Yes' if LengthWithinMargin(seq.seq) else 'No'
                        })
                fasta.close()
            if f.path.endswith('.xlsx'):
                xlsf = f.open('r')
                workbook = openpyxl.load_workbook( xlsf )
                sheet = workbook.active
                headers = [ col.value for col in sheet[1] ]
                try:
                    seqid_idx = headers.index(SAMPLEID)
                except ValueError:
                    seqid_idx = None
                i=0
                for row in sheet.iter_rows(min_row=2,max_row=sheet.max_row):
                    if seqid_idx:
                        seqid = row[seqid_idx].value
                    else:
                        seqid = i
                    i += 1
                    for cell in row:
                        header = headers[cell.col_idx - 1]
                        data.setdefault(seqid, {})[header] = cell.value
                xlsf.close()
            if f.path.endswith('.csv'):
                with f.open('r') as csvf:
                    wrapper = io.TextIOWrapper(csvf, encoding='utf-8')
                    csvdata = csv.reader(wrapper, delimiter='\t')
                    headers = next(csvdata)
                    try:
                        seqid_idx = headers.index(SAMPLEID)
                    except ValueError:
                        seqid_idx = None
                    i=0
                    for row in csvdata:
                        if seqid_idx:
                            seqid = row[seqid_idx]
                        else:
                            seqid = i
                        i += 1
                        for j, cell in enumerate(row):
                            header = headers[j]
                            data.setdefault(seqid, {})[header] = cell

    return headers, data

@login_required
@bp.route('_change_project', methods=['POST'])
def change_project():
    f = request.form.to_dict()
    if 'project' in f:
        update_setting('project', f['project'])
    return jsonify(upload_data()['project'])

@login_required
@bp.route('_uploadfile', methods=['POST'])
def upload_file():
    f = request.files['file']
    collection = upload_data()['collection']
    if not current_user.ifs.folderexists(collection):
        current_user.ifs.mkdir(collection)
    # Generate irods file object
    iObjName = os.path.join(collection, f.filename)
    iObj = current_user.ifs.open(iObjName, 'w')
    f.save(iObj)
    iObj.close()
    return '', 204

@login_required
@bp.route('_cancelupload', methods=['GET'])
def cancel_upload():
    clear_upload()
    return render_template('home.html')

@login_required
@bp.route('_validate', methods=['GET'])
def validate():
    settings = upload_data()
    if settings['collection'] is None:
        return redirect(url_for('upload.upload_page'))
    return render_template('validate_report.html', collection=settings['collection'])


@login_required
@bp.route('_uploadbatch', methods=['GET'])
def upload_batch():
    settings = upload_data()
    if settings['collection'] is None:
        return redirect(url_for('upload.upload_page'))
    collection = settings['collection']
    batch = get_batch(collection)
    batch.validate()
    result = batch.result()
    if result in  ('Ok', 'Warning', 'Error'):
        # Generate a collection name for storing upload
        # TODO: add project
        collname = unique_coll(settings['project'])
        coll = current_user.irods_session.collections.get(collname)
        upload_result = batch.upload(coll, force=True)
    # TODO: Evaluate upload result
    # TODO: Remove current upload session vars
    clear_upload()
    # TODO: Show some result
    return render_template('upload_result.html', upload_result=upload_result)



@login_required
@bp.route('_validate_results', methods=['GET'])
def validate_results():
    settings = upload_data()
    if settings['collection'] is None:
        return redirect(url_for('upload.upload_page'))
    collection = settings['collection']
    batch = get_batch(collection)
    batch.validate()
    data = batch.validate_results()
    result = batch.result()
    content = { 'report': render_template('validate_results.html', data=data),
                'result': result }
    return content

def get_batch(collection):
    dbcred = current_app.config["LABSURV_DB_CRED"].get(current_user.environment)
    if dbcred is None:
        # TODO : show some error
        return False
    connect(*dbcred) 
    batch = KSUpload(KSUploadType.EXTERNAL, sending_organisation_id=1)
    for f in current_user.ifs.ls(collection):
        if f.isfile():
            if f.path.endswith('.fasta'):
                fasta = f.open('r')
                wrapper = io.TextIOWrapper(fasta, encoding='utf-8')
                batch.load_fasta(wrapper)
                fasta.close()
            if f.path.endswith('.xlsx'):
                xlsf = f.open('r')
                batch.load_data(xlsf, 'xlsx', transform_file=current_app.config.get("LABSURV_TRANSFORM"))
                xlsf.close()
            if f.path.endswith('.csv'):
                csvf = f.open('r')
                wrapper = io.TextIOWrapper(csvf, encoding='utf-8')
                batch.load_data(wrapper, 'csv', transform_file=current_app.config.get("LABSURV_TRANSFORM"))
    return batch

@bp.route('_seq_list', methods=['GET'])
def seq_list():
    collection = request.args.get('collection')
    ids = []
    if collection:
        headers, ids =  read_data(collection)
    return render_template('seq_list.html', headers=headers, ids=ids)