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
from flask import Blueprint, render_template, redirect, request, url_for, session, current_app, flash
from flask import jsonify
from flask_login import current_user, login_required
import uuid
from app import projects, iqry
from app.datafield import datafield
from Bio import SeqIO
import pymssql
import openpyxl
import randomname
import json
import re
from irods.models import Collection, CollectionMeta
from irods.column import Criterion
from irods.meta import iRODSMeta
#from flask_session import Session
from app.irodssessions import irods_manager

from nonacris.web import NncWeb

ATTR_UPLOAD = 'user::upload'
ATTR_UPLOADNAME = f'{ATTR_UPLOAD}::name'
ATTR_DATASETID = 'sys::dataset_id'
ATTR_UPLOADSETTINGS = 'user::upload::settings::'
ATTR_UPLOADMETA = 'user::upload::meta::'

class UploadType:
    Pending = 'pending'
    Ready = 'ready'
    Done = 'done'

SAMPLEID = 'SendingOrganisationSampleId'
SEQUENCEID = 'SendingOrganisationSequenceId'

UPLOAD_DIR = '/tmp/upload' 

# FASTA_EXT = [ '.fasta', '.fa', '.fa.gz', '.fas', '.fas.gz', '.fasta.gz']

FASTA_EXT = [ '.fasta', '.fa', '.fas', '.gz' ]

UPLOAD_KEY = 'current_upload'
USER_DEFINED_VARIABLES = 'user_defined_variables'

DEFAULT_UPLOAD = {
    'directory': None,
    'project': None,
    'filelist': [],
    'use_case': 'UploadRivmSampleForm',
    USER_DEFINED_VARIABLES: {}
}

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
    current_app.logger.debug('upload/unique_coll(): mkdir "{}"'.format(collname))
    current_user.ifs.mkdir(collname)
    # TODO : add some metadata?
    return collname

def unique_projectcoll(project):
    """Generate a unique collection name for project
    and create the collection"""
    projectcoll = f'/{current_user.irods_zone}/projects/nonacris'

    if not project is None:
        pl, result = projects.rest_call('GET', 'projects/{}'.format(project))
        if 'default_collection' in pl:
            projectcoll = pl['default_collection']
    return unique_coll(projectcoll, prefix='', use_date=True)

def upload_data():
    if current_user.environment not in session:
        session[current_user.environment] = {}
        session.modified = True
    if not UPLOAD_KEY in session[current_user.environment]:
        session[current_user.environment][UPLOAD_KEY] = DEFAULT_UPLOAD
        update_setting('directory', f'{UPLOAD_DIR}/{uuid.uuid4()}')
        session.modified = True
    return session[current_user.environment][UPLOAD_KEY]

def update_setting(key, value):
    upload_data()
    session[current_user.environment][UPLOAD_KEY][key] = value
    session.modified = True

@bp.route('_clearupload')
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
#        session.clear()
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


@bp.route('_uploadfile', methods=['POST'])
def upload_file():
    f = request.files['file']
    directory = upload_data()['directory']
    os.makedirs(directory, exist_ok=True)
    # Generate file object
    filePath = os.path.join(directory, f.filename)
    f.save(filePath)
    return '', 204

@bp.route('_cancelupload', methods=['GET'])
def cancel_upload():
    clear_upload()
    return render_template('home.html')

@bp.route('_validate', methods=['POST'])
def validate():
    data = request.form.to_dict()
    use_case = data.get('usecase')
    settings = upload_data()
    if use_case:
        update_setting('use_case', use_case) # I guess a chnage of useCase means the userDefinedVariables have to be reset
        update_setting( USER_DEFINED_VARIABLES, {})
    if settings['directory'] is None:
        return redirect(url_for('upload.upload_page'))
    return render_template('validate_report.html', collection=settings['directory'])

def get_test_single_value_meta():
    missingVariables = { 'SendingOrganisationId': {
                        'is_required': False,
                        'schema': {'enum': ['RIVM', 'Meander MC', 'Atal-Medial BV - Local in blahblubb blubb very long name Amstelland', 'Streeklab - GGD Amsterdam', 'BovenIJ Ziekenhuis', 'OLVG - Locatie West ', 'Atal-Medial BV - Loc...rvaart MCS', 'OLVG Lab BV', 'Amsterdam UMC - Loca...robiologie'], 'type': 'string'},
                        'default': None
                        },
                'SamplingFrame': {
                        'is_required': False,
                        'schema': {'enum': ['ZORG', 'TESTSTRAAT', 'STUDIE', 'NIVEL', 'CLUSTER'], 'type': 'string'},
                        'default': None
                        },
                'SequencingProtocol': {
                        'is_required': False,
                        'schema': {"type": "string", "maxLength": 10},
                        'default': None
                        },
                'PangolinScorpioVersion': {
                        'is_required': True,
                        'schema': {"type": "string", "minLength": 2, "maxLength": 10},
                        'default': None
                    },
                'NextCladeVersion': {
                        'is_required': True,
                        'schema': {"type": "string", "enum": ["J", "N", "NA_VACCINATIE", "HERINFECTIE", "NA_VACCINATIE_1X", "NA_VACCINATIE_2X"]},
                        'default': None
                    },
                'RivmSequencingProtocol': {
                        'is_required': True,
                        "schema": {"type": "string", "maxLength": 10, "pattern": "^\\d\\d\\d\\d-\\d\\d-\\d\\d$"},
                        'default': "1234"
                    }
                }
    return missingVariables

def check_against_schema( value, schema ):
    message = ""
    #check if value in enum
    if 'enum' in schema:
        if value not in schema['enum']:
            message += f"Value not in allowed set. "
    else:
        #check min length
        if 'minLength' in schema:
            if len(value) < schema['minLength']:
                message += f"Must have {schema['minLength']} characters. "
        #check max length
        if 'maxLength' in schema:
            if len(value) > schema['maxLength']:
                message += f"Must not exceed {schema['maxLength']} characters. "

        #check if value matches pattern
        if 'pattern' in schema:
            regex = re.compile( schema['pattern'] )
            if not regex.match(value):
                message += f"Value doesn't conform to pattern \"{schema['pattern']}\". "
    return message

def check_variables( defined_vars, missing_vars_def ):
    all_ok = True
    response = {}
    #check for all missing vars, if they are set (if required) and correct...
    for key in missing_vars_def.keys():
        message = None
        if missing_vars_def[key]['is_required']:
            if key not in defined_vars:
                message = "Is required but not set."
                continue
        if key in defined_vars:
            value = defined_vars[key]
            schema = missing_vars_def[key]['schema']
            message = check_against_schema( value, schema )
        if message:
            response[key] = message
            all_ok=False
    return (all_ok, response)

@bp.route('_set_missing_variables', methods=['POST'])
def set_missing_variables():
    settings = upload_data()
    user_defined_variables = {}
    for dict in request.json:
        user_defined_variables[ dict['name'] ] = dict['value']
    #server side check of the variables

    #this is shit, we parse the same files now in three different requests...
    batch = get_batch(settings)
    #tried to get the missing variables from the session (as determined in a prior step)
    #but exceeded size-limit of cookie
    missingVariables = batch.getSingleValueVariableMetadata( filter_by_input=True )
    #missingVariables = get_test_single_value_meta()
    #store them....
    all_ok, response = check_variables( user_defined_variables, missingVariables )
    if all_ok:
        #TODO: probably its not necessary to set the SingleValueVariables here, since we gat a new batch in every request anyway...
        #for key, value in user_defined_variables.items():
        #    batch.setSingleValueVariable( key, value )
        update_setting(USER_DEFINED_VARIABLES,user_defined_variables)
    return jsonify(response)




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
        collname = unique_projectcoll('nonacris')
        coll = irods_manager.session().collections.get(collname)
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

@bp.route('filelist', methods=['GET'])
def filelist():
    settings = upload_data()
    if settings['directory']:
        files = []
        try:
            files = os.listdir(settings['directory'])
        except FileNotFoundError:
            # A likely thing to happen. Log and continue.
            current_app.logger.info('upload/filelist: dir not found: {}'.format(
                settings['directory']))
    return render_template('upload_filelist.html', files=files)

@bp.route('_missing_variables', methods=['GET'])
def missing_variables():
    settings = upload_data()
    if settings['directory'] is None:
        return redirect(url_for('upload.upload_page'))
    directory = settings['directory']
    batch = get_batch(settings)
    content = {}
    missingVariables = batch.getSingleValueVariableMetadata( filter_by_input=True)
    #missingVariables = get_test_single_value_meta()
    if not missingVariables:
        return { 'hasMissingVariables': False }
    else:
        #TODO: apparently the size of the session cookie might  exceed the limit of 4093 bytes, and is ignored by the browser...
        #      instead of storing the missingvars here we have to parse the files again in _set_missing_variables!
        #update_setting(MISSING_VARIABLES,missingVariables)
        content = { 'hasMissingVariables': len(missingVariables.keys())>0,
                    'missingVariablesForm': render_template( 'missing_variables.html', data=missingVariables) }
    return content


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
    parsedDataContext = {
                        'dataJSON': "{}",
                        'columnsJSON': "[]"
    }
    parsedData = {}
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
            # here an error because of missing variables should not occure anymore!
            batch.parse()  
            result = batch.data['Parse.Validation.Table'].to_dict()
            #The bootstrap-table component has problems whith column names in format "Teststraat of Siekenhaus -> \"\""
            #Here we get the title with the mapping, but use the fieldname without mapping
            #- for thetable data, use the original fieldnames (without mapping)
            #  e.g. Sex: "Vrouw -> V"
            parsedDataWithMapping = batch.getParsedDataForDisplay( add_variable_mapping=True)
            #- for the column headers we use the data with mapping
            #  e.g. geslacht -> Sex: "Vrouw -> V"
            parsedDataWithoutMapping = batch.getParsedDataForDisplay( add_variable_mapping=False)
            # - then we create columns, with the unmapped value as field-value, and the mapped one as title:
            columns=[]
            for col in parsedDataWithMapping.columns:
                #5 possibilities:
                #  -  SampleId
                #  -  Teststraat of Ziekenhuis -> ""
                #  -  4 cijferige postcode -> ResidencePostalCode
                #  -  geboortedatum -> ""
                #  -  "" -> SendingOrganisationId
                split = col.split( " -> " )
                f = split[-1]
                if f == '""':
                    f = split[0]
                columns.append( { 'field': f, 'title': col } )

            parsedDataJson = parsedDataWithoutMapping.to_json(orient='records')  
            parsedDataContext = {
                    'columnsJSON': json.dumps(columns),
                    'dataJSON': parsedDataJson
            }
            validation_passed = not batch.data['Parse.Validation.HasError']
        except Exception as ex:
            result = { 'Error': { '0': 'System error in validation module' },
                    'Description' : { '0' : ex },
                    'Type': {'0': type(ex) }
            }
    if not validation_passed:
        clear_upload()
    content = { 'parsedData': render_template('parsed_data.html', data=parsedDataContext),
                'report': render_template('validate_results.html', data=result),
                'result': validation_passed }
    return content

def get_batch(settings):
    directory = settings.get('directory')
    dbparms = current_app.config["LABSURV_DB_CRED"].get(current_user.environment)
    dbconn = pymssql.connect(**dbparms)
    #tried to store the stateful batch-object in a server-session, didn't work. (can't be pickled because it contains the SQL-Connection)
    #the_batch = settings.get(BATCH)
    #if not the_batch:
    #    the_batch = NncWeb(dbconn, None)
    #    settings[BATCH]=the_batch
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
    #set all user defined variables from session
    #this is kind of a hack, since the batch/NncWeb is stateful, and we store the state 
    #in the client session and have to reproduce the state if needed...
    if settings.get(USER_DEFINED_VARIABLES):
       user_defined_variables = settings.get(USER_DEFINED_VARIABLES)
       for key, value in user_defined_variables.items():
            batch.setSingleValueVariable( key, value )
    return batch

@bp.route('_seq_list', methods=['GET'])
def seq_list():
    directory = request.args.get('directory')
    headers = []
    ids = []
    if directory:
        try:
            headers, ids =  read_data(directory)
        except FileNotFoundError:
            # A likely thing to happen. Log and continue.
            current_app.logger.info('upload/_seq_list: dir not found: {}'.format(directory))
        
    return render_template('seq_list.html', headers=headers, ids=ids)


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
        print(coll)
        for k, v in data.items():
            if k in FIELDS and v:
                iqry.scollmetaval(coll, f'{ATTR_UPLOADSETTINGS}{k}', v)
        if data.get('submitbutton', 'save') == 'next':
            return redirect(url_for('upload.upload_meta', coll=coll))
        else:
            return redirect(url_for('upload.upload_settings', coll=coll))

@bp.route('_uploadmeta', methods=['GET', 'POST'])
def upload_meta():
    print('META UPLOAD')
    print(f'Method is {request.method}')
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
        print('HANDLE POST REQUEST')
        print(f'METHOD {request.method}')
        print(f'JSON: {request.json}')
        print(request.form.to_dict())
        return jsonify({'status': 'OK' }), 200


@bp.route('_uploaddata', methods=['GET', 'POST'])
def upload_data():
    if request.method == 'GET':
        print('GET DATA')
        coll = request.args.get('coll')
        name = os.path.basename(coll)
        return render_template('upload_data.html', name=name, coll=coll)
    if request.method == 'POST':
        print('POST DATA')
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
        print(f, data, filename, filepath)
        with current_user.ifs.open(filename, 'w') as d:
            shutil.copyfileobj(f, d)
        iqry.invalidate(coll)
        return 'OK'

@bp.route('_actions', methods=['GET'])
def upload_actions():
    action = request.args.get('action')
    coll = request.args.get('coll')
    print(action)
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

    #return redirect(url_for('upload.upload_settings', coll=coll ))

@bp.route('_posttest', methods=['POST'])
def posttest():
    print('POST test')
    print(f'METHOD {request.method}')
    print(f'JSON: {request.json}')
    return 'OK', 200

