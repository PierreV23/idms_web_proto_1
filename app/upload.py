#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiemsurveilance data upload interface voor NGSweb
"""

import csv
import io
import os
import shutil
import sys
import time
from flask import Blueprint, render_template, redirect, request, url_for, session, current_app
from flask import jsonify
from flask_login import current_user, login_required
import uuid
from app import projects
from Bio import SeqIO
import pymssql
import openpyxl

from nonacris.web import NncWeb

SAMPLEID = 'SendingOrganisationSampleId'
SEQUENCEID = 'SendingOrganisationSequenceId'

UPLOAD_DIR = '/tmp/upload'

FASTA_EXT = [ '.fasta', '.fa', '.fa.gz', '.fas', '.fas.gz', '.fasta.gz']

UPLOAD_KEY = 'current_upload'
DEFAULT_UPLOAD = {
    'directory': None,
    'project': None,
    'filelist': [],
    'use_case': 'UploadRivmSampleForm'
}

bp = Blueprint('upload', __name__, url_prefix='/upload')


@login_required
def unique_coll(project):
    """Generate a unique collection name for project
    and create the collection"""
    projectcoll = f'/{current_user.irods_zone}/projects/nonacris'

    if not project is None:
        pl, result = projects.rest_call('GET', 'projects/{}'.format(project))
        if 'default_collection' in pl:
            projectcoll = pl['default_collection']
    datestr = time.strftime('%Y%m%d_%H%M%S')
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
        update_setting('directory', f'{UPLOAD_DIR}/{uuid.uuid4()}')
    return session[current_user.environment][UPLOAD_KEY]

def update_setting(key, value):
    settings = upload_data()
    session[current_user.environment][UPLOAD_KEY][key] = value
    session.modified = True

@bp.route('_clearupload')
@login_required
def remove_files():
    if current_user.environment in session:
        if UPLOAD_KEY in session[current_user.environment]:
            directory =  session[current_user.environment][UPLOAD_KEY].get('directory')
            if directory and directory.startswith(UPLOAD_DIR):
                if os.path.exists(directory):
                    for file in os.listdir(directory):
                        os.remove(os.path.join(directory, file))
    return redirect(url_for('upload.upload_page'))

def clear_upload():
    if current_user.environment in session:
        if UPLOAD_KEY in session[current_user.environment]:
            directory =  session[current_user.environment][UPLOAD_KEY].get('directory')
            if directory and directory.startswith(UPLOAD_DIR):
                if os.path.exists(directory):
                    shutil.rmtree(directory)
            del session[current_user.environment][UPLOAD_KEY]
    session.modified = True


@bp.errorhandler(413)
def too_large(e):
    return "File is too large", 413


@bp.route('upload')
def upload_page():
    use_cases = NncWeb.USE_CASE
    # Find out if an upload is still in progress
    return render_template('upload.html', upload_data=upload_data(), use_cases=use_cases)

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

def read_data(directory):
    data = {}
    headers = []
    for filename in os.listdir(directory):
        fullname = os.path.join(directory, filename)
        if os.path.isfile(fullname):
            _, extension = os.path.splitext(fullname)
            # if extension == '.fasta':
            #     with open(fullname, 'r') as fasta:
            #         for seq in SeqIO.parse(fasta, 'fasta'):
            #             data.setdefault(seq.id, {})['PassedQC'] = 'No' if HasTooManyN(seq.seq) else 'Yes'
            #             data.setdefault(seq.id, {})['LengthOK'] = 'Yes' if LengthWithinMargin(seq.seq) else 'No'
            if extension == '.xlsx':
                with open(fullname, 'rb') as xlsf:
                    workbook = openpyxl.load_workbook( xlsf )
                    sheet = workbook.active
                    headers = [ col.value for col in sheet[1] ]
                    try:
                        seqid_idx = headers.index(SEQUENCEID)
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
            if extension == '.csv':
                with open(fullname, 'r') as csvf:
#                    wrapper = io.TextIOWrapper(csvf, encoding='utf-8')
                    csvdata = csv.reader(csvf, delimiter='\t')
                    headers = next(csvdata)
                    try:
                        seqid_idx = headers.index(SEQUENCEID)
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

# @login_required
# @bp.route('_change_organisation', methods=['POST'])
# def change_organisation():
#     f = request.form.to_dict()
#     if 'organisation' in f:
#         update_setting('organisation', f['organisation'])
#     return jsonify(upload_data()['organisation'])

@login_required
@bp.route('_uploadfile', methods=['POST'])
def upload_file():
    f = request.files['file']
    directory = upload_data()['directory']
    os.makedirs(directory, exist_ok=True)
    # Generate file object
    filePath = os.path.join(directory, f.filename)
    f.save(filePath)
    return '', 204

@login_required
@bp.route('_cancelupload', methods=['GET'])
def cancel_upload():
    clear_upload()
    return render_template('home.html')

@login_required
@bp.route('_validate', methods=['POST'])
def validate():
    data = request.form.to_dict()
    use_case = data.get('usecase')
    settings = upload_data()
    if use_case:
        update_setting('use_case', use_case)
    if settings['directory'] is None:
        return redirect(url_for('upload.upload_page'))
    return render_template('validate_report.html', collection=settings['directory'])


@login_required
@bp.route('_uploadbatch', methods=['GET'])
def upload_batch():
    settings = upload_data()
    if settings['directory'] is None:
        return redirect(url_for('upload.upload_page'))
    directory = settings['directory']
    batch = get_batch(settings)
    batch.parse()
    result = not batch.data['Parse.Validation.HasError']
    upload_result = False
    if result:
        # Generate a collection name for storing upload
        # TODO: add project, for now use 'upload' project
        collname = unique_coll('upload')
        coll = current_user.irods_session.collections.get(collname)
        batch.setIrodsCollection(coll)
        try:
            batch.store()
            upload_result = not batch.data.get('Upload.Verify.HasDifference', False)
        except:
            pass
    # TODO: Evaluate upload result
    clear_upload()
    # TODO: Show some result
    return render_template('upload_result.html', upload_result=upload_result)

@login_required
@bp.route('filelist', methods=['GET'])
def filelist():
    settings = upload_data()
    if settings['directory']:
        files = os.listdir(settings['directory'])
    return render_template('upload_filelist.html', files=files)

@login_required
@bp.route('_validate_results', methods=['GET'])
def validate_results():
    settings = upload_data()
    if settings['directory'] is None:
        return redirect(url_for('upload.upload_page'))
    batch = None
    result = { 'Error': { '0': 'Unknown error' },
                'Description' : { '0' : 'Unknown validation error' },
                'Type': {'0': '' }
    }
    validation_passed = False
    try:
        batch = get_batch(settings)
    except Exception as ex:
        result = { 'Error': { '0': 'System error in validation module' },
                   'Description' : { '0' : ex },
                   'Type': {'0': type(ex) }
        }
    if batch:    
        try:
            batch.parse()
            result = batch.data['Parse.Validation.Table'].to_dict()
            validation_passed = not batch.data['Parse.Validation.HasError']
        except Exception as ex:
            result = { 'Error': { '0': 'System error in validation module' },
                    'Description' : { '0' : ex },
                    'Type': {'0': type(ex) }
            }
    if not validation_passed:
        clear_upload()
    content = { 'report': render_template('validate_results.html', data=result),
                'result': validation_passed }
    return content

def get_batch(settings):
    directory = settings.get('directory')
    dbparms = current_app.config["LABSURV_DB_CRED"].get(current_user.environment)
    dbconn = pymssql.connect(**dbparms)
    batch = NncWeb(dbconn, None)
    batch.setUseCase(settings.get('use_case'))
    for filepath in os.listdir(directory):
        fullpath = os.path.join(directory, filepath)
        if os.path.isfile(fullpath):
            _, extension = os.path.splitext(fullpath)
            if extension in FASTA_EXT:
                batch.setInputSequenceFile(fullpath)
            if extension in [ '.xlsx', '.csv', '.tsv']:
                batch.setInputDataFile(fullpath)
    return batch

@bp.route('_seq_list', methods=['GET'])
def seq_list():
    directory = request.args.get('directory')
    headers = []
    ids = []
    if directory:
        headers, ids =  read_data(directory)
    return render_template('seq_list.html', headers=headers, ids=ids)