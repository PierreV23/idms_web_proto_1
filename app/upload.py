#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data upload interface voor NGSweb
"""

import io
import os
from flask import Blueprint, render_template, redirect, request, url_for, session
from flask_login import current_user, login_required
import uuid
from app import projects
from Bio import SeqIO
import openpyxl


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
            print(f.path)
            if f.path.endswith('.fasta'):
                fasta = f.open('r')
                wrapper = io.TextIOWrapper(fasta, encoding='utf-8')
                for seq in SeqIO.parse(wrapper, 'fasta'):
                    print(LengthWithinMargin(seq.seq))
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
                for row in sheet.iter_rows(min_row=2,max_row=sheet.max_row):
                    seqid = row[6].value
                    for cell in row:
                        header = headers[cell.col_idx - 1]
                        data.setdefault(seqid, {})[header] = cell.value
                xlsf.close()
    print(data) 
    return headers, data

@login_required
@bp.route('_uploadfile', methods=['POST'])
def upload_file():
    f = request.files['file']
    print(f'upload_file {f.filename}')
    collection = session[UPLOAD_KEY]['collection']
    if not current_user.ifs.folderexists(collection):
        current_user.ifs.mkdir(collection)
    # Generate irods file object
    iObjName = os.path.join(collection, f.filename)
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

@bp.route('_seq_list', methods=['GET'])
def seq_list():
    collection = request.args.get('collection')
    ids = []
    print(collection)
    if collection:
        headers, ids =  read_data(collection)
    return render_template('seq_list.html', headers=headers, ids=ids)