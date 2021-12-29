from flask import Flask, Blueprint, render_template, request, jsonify, redirect, url_for, session
from flask_login import current_user, login_required
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from marshmallow import Schema, fields, validate
from sqlalchemy.orm import relationship, remote, foreign
from sqlalchemy import ForeignKey, distinct
from irods.models import Collection, CollectionMeta
from irods.column import Criterion
from app.datafield import datafield
import json
import requests
from requests.auth import HTTPBasicAuth

db = SQLAlchemy()

bp = Blueprint('ngsruns', __name__, url_prefix='/ngsruns')
ma = Marshmallow(bp)

REQUESTS_METHODS = {
    'GET':   requests.get,
    'PUT':   requests.put,
    'POST':  requests.post,
    'DELETE':requests.delete
}

class NGSRun(db.Model):
    __tablename__ = 'ngsruns'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable = False)
    flowcell = db.Column(db.String(30), default='', nullable = False)
    creation_date = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), nullable=False)
    description = db.Column(db.String(250), default='', nullable = False)
    project = db.Column(db.String(32))
    owner = db.Column(db.String(32))

    def __init__(self, flowcell):
        self.flowcell = flowcell


class NGSBarcode(db.Model):
    __tablename__ = 'ngsbarcodes'
    id = db.Column(db.Integer, primary_key=True)
    ngsrun = db.Column(db.Integer, db.ForeignKey('ngsruns.id'))
    barcode = db.Column(db.String(128), nullable = False)
    sampleid = db.Column(db.String(30), nullable = False)
    primer_set = db.Column(db.String(128), nullable = True)
    virus_target = db.Column(db.String(128), nullable = True)
    description = db.Column(db.String(256), nullable = True)
    creation_date = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), nullable=False)

    def __init__(self, ngsrun, barcode):
        self.ngsrun = ngsrun
        self.barcode = barcode

class NGSRunsSchema(ma.Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(1))
    flowcell = fields.String(required=True)

class NGSRunSchema(ma.Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(1))
    flowcell = fields.String(required=True)
    description = fields.String()
    project = fields.String()

class NGSBarcodesSchema(ma.Schema):
    barcode = fields.String()
    primer_set = fields.String()
    sampleid = fields.String()
    virus_target = fields.String()
    description = fields.String()


ngsrun_schema = NGSRunSchema()
ngsruns_schema = NGSRunsSchema(many=True)
barcode_schema = NGSBarcodesSchema()
barcodes_schema = NGSBarcodesSchema(many=True)

barcodes = [ 'barcode{:02d}'.format(bar) for bar in range(1,97) ]

FIELDS = {
    'virus_target': NGSBarcode.virus_target,
    'primer_set': NGSBarcode.primer_set
}

@login_required
def rest_call(request_type, endpoint, data={}):    
    url = 'http://{}/api/1.0/{}'.format(current_user.irods_server, endpoint)
    #TODO: remove this testing line:
    #url = 'http://{}/api/1.0/{}'.format('0.0.0.0:5000', endpoint)
    auth = HTTPBasicAuth('alt\\{}'.format(current_user.username), current_user.ntlm_hash)
    return_data = {}
    if request_type in REQUESTS_METHODS:
        print(f'REST: {request_type} {url} {data}')
        response = REQUESTS_METHODS[request_type](url, auth=auth, json=data)
    try:
        return_data = response.json()
    except:
        return_data = {}
    return return_data, response.status_code

@bp.route('complete/<field>', methods=['GET'])
def get_complete(field):
    req = request.args.to_dict().get('q', '')
    data1 = db.session.query(FIELDS[field]).filter(FIELDS[field].like('%{}%'.format(req))).distinct().all()
    return jsonify(data1)

@bp.route('list', methods=['GET'])
@login_required
def run_list():
    idrequest = request.args.get('idrequest', 0)
    data = [ vars(f) for f in NGSRun.query.all() ]
    # Create a list of flowcells and collections in irods
    q = current_user.irods_session.query(Collection.name, CollectionMeta.value).filter( \
            Criterion('=', CollectionMeta.name, 'minion::flow_cell_id')).filter( \
            Criterion('=', Collection.parent_name, f'/{current_user.irods_zone}/projects/ngslab/minion'))
    flowcell_list = { x[CollectionMeta.value] : x[Collection.name] for x in q }
    for run in data:
        if run['flowcell'] and flowcell_list.get(run['flowcell']):
            run['datacoll'] = datafield('collection', str(flowcell_list.get(run['flowcell'])), 'irods_collection').htmlshort
        else:
            run['datacoll'] = ''
    data.sort(key = lambda x: x["id"], reverse=True)
    fields = ['id', 'name', 'flowcell', 'project', 'datacoll']
    data2 = [{ p:str(x[p]) for p in fields } for x in data ]
    return render_template('ngsruns.html', data=json.dumps(data2), idrequest=idrequest, default_project=current_user.settings.get('default_project', ''))

@bp.route('_barcodes', methods=['GET'])
def run_barcodes():
    id = request.args.get('idrequest', type=int)
    barcodes = NGSBarcode.query.filter(NGSBarcode.ngsrun == id).all()
    fields = [ 'barcode', 'description', 'primer_set', 'sampleid', 'virus_target']
    data = [ { p: getattr(x, p) for p in fields } for x in barcodes ]
    columns = [
        { "field": "barcode", "title": "Barcode", "sortable": True },
        { "field": "sampleid", "title": "SampleID", "sortable": True },
        { "field": "virus_target", "title": "Virus Target", "sortable": True },
        { "field": "primer_set", "title": "Primer Set", "sortable": True },
        { "field": "description", "title": "Description", "sortable": True }
    ]
    data = {
        'columnsJSON': json.dumps(columns),
        'dataJSON': json.dumps(data),
        'id': 'barcodetable'
    }
    return render_template('bootstraptable.html', data=data, no_page=True)
    
@bp.route('edit', methods=['GET'])
def edit_form():
    id = request.args.get('idrequest', '', type=str)
    run = NGSRun.query.filter(NGSRun.id == id).one_or_none()
    barcode_obj = NGSBarcode.query.filter(NGSBarcode.ngsrun == id).all()
    #barcodes = [ f.barcode for f in barcode_obj ] # maak een list van object
    data = { barcode : None for barcode in barcodes }
    for f in barcode_obj:
        data[f.barcode] = f
    data.update({"flowcell": run.flowcell})
    data.update({"name": run.name})
    data.update({"description": run.description})
    data.update({"project": run.project})
    data.update({"owner": run.owner})
    #data[name] = run.name
    #data[description] = run.description
    #data = { f.barcode: f for f in barcode_obj }
    return render_template('ngsrun.html', data=data, barcodes=barcodes, id=id)

@bp.route('new', methods=['GET'])
def run_form():
    pl, result = rest_call('GET', 'projects')
    projects=[]
    if result == 200:
        projects = [ p['name'] for p in pl ]
    data = { barcode : None for barcode in barcodes }
    return render_template('ngsrun.html', data=data, projects=projects, barcodes=barcodes, id=-1, default_project=current_user.settings.get('default_project', ''))

@bp.route('delete', methods=['GET'])
@login_required
def delete_ngs_run():
    id = request.args.get('id', type=int)
    if id:
        NGSBarcode.query.filter(NGSBarcode.ngsrun==id).delete()
        NGSRun.query.filter(NGSRun.id == id).delete()
        db.session.commit()
    return redirect(url_for('ngsruns.run_list'))

@bp.route('new', methods=['POST'])
def run_update():
    f = request.form.to_dict()
    new_run = NGSRun(f.get('flowcell', ''))
    new_run.name = f.get('name', '')
    new_run.project = f.get('project', '')
    new_run.description = f.get('description', '')
    db.session.add(new_run)
    db.session.commit()
    for barcode in barcodes:
        if f.get('sampleid_{}'.format(barcode)):
            new_barcode = NGSBarcode(new_run.id, barcode)
            new_barcode.sampleid = f.get('sampleid_{}'.format(barcode)).replace(" ","")
            new_barcode.virus_target = f.get('target_{}'.format(barcode))
            new_barcode.primer_set = f.get('primer_{}'.format(barcode))
            new_barcode.description = f.get('description_{}'.format(barcode))
            db.session.add(new_barcode)
    db.session.commit()
    current_user.settings['default_project'] = new_run.project
    return redirect(url_for('ngsruns.run_list', idrequest=new_run.id))

# GET

@bp.route('/api/runs', methods=['GET'])
def get_ngs_runs():
    """Retrieve a list of all ngs runs
    """
    all_runs = NGSRun.query.all()
    dump = ngsruns_schema.dump(all_runs)
    return jsonify(dump)

@bp.route('/api/runs/<flowcell>', methods=['GET'])
def get_ngs_run(flowcell):
    """Retrieve a single ngs runs
    """
    ngsrun = NGSRun.query.filter(NGSRun.flowcell == flowcell).one_or_none()
    return jsonify(ngsrun_schema.dump(ngsrun))

@bp.route('/api/runs/<flowcell>/barcodes', methods=['GET'])
def get_ngs_barcodes(flowcell):
    """Retrieve barcodes for a single ngs runs
    """
    ngsrun = NGSRun.query.filter(NGSRun.flowcell == flowcell).one_or_none()
    barcodes = NGSBarcode.query.filter(NGSBarcode.ngsrun == ngsrun.id).all()
    return jsonify(barcodes_schema.dump(barcodes))
