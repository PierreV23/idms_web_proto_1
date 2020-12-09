from flask import Flask, Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import current_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, remote, foreign
from sqlalchemy import ForeignKey, distinct
from irods.models import Collection, CollectionMeta
from irods.column import Criterion

db = SQLAlchemy()

bp = Blueprint('ngsruns', __name__, url_prefix='/ngsruns')

class NGSRun(db.Model):
    __tablename__ = 'ngsruns'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable = False)
    flowcell = db.Column(db.String(30), default='', nullable = False)
    creation_date = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), nullable=False)
    description = db.Column(db.String(250), default='', nullable = False)
    project = db.Column(db.Integer)
    owner = db.Column(db.String(32))

    def __init__(self, flowcell):
        self.flowcell = flowcell


class NGSBarcode(db.Model):
    __tablename__ = 'ngsbarcodes'
    id = db.Column(db.Integer, primary_key=True)
    ngsrun = db.Column(db.Integer, db.ForeignKey('ngsruns.id'))
    barcode = db.Column(db.String(128), nullable = False)
    unilab = db.Column(db.String(30), nullable = False)
    primer_set = db.Column(db.String(128), nullable = True)
    virus_target = db.Column(db.String(128), nullable = True)
    description = db.Column(db.String(256), nullable = True)
    creation_date = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), nullable=False)

    def __init__(self, ngsrun, barcode):
        self.ngsrun = ngsrun
        self.barcode = barcode

barcodes = [ 'barcode{:02d}'.format(bar) for bar in range(1,25) ]

FIELDS = {
    'virus_target': NGSBarcode.virus_target,
    'primer_set': NGSBarcode.primer_set
}

@bp.route('complete/<field>', methods=['GET'])
def get_complete(field):
    print(request)
    req = request.args.to_dict().get('q', '')
    data1 = db.session.query(FIELDS[field]).filter(FIELDS[field].like('%{}%'.format(req))).distinct().all()
    return jsonify(data1)

@login_required
def get_import_state(flowcell, flowcell_attr):
    irods_session = current_user.irods_session
    q = irods_session.query(Collection.name).filter( \
        Criterion('=', CollectionMeta.name, flowcell_attr)).filter( \
        Criterion('=', CollectionMeta.value, flowcell))
    import_coll = None
    for collobj in q:
        coll = irods_session.collections.get(collobj[Collection.name])
        meta = coll.metadata.get_all('import_foldername')
        if meta:
            import_coll = collobj[Collection.name]
    return import_coll

@bp.route('list', methods=['GET'])
def run_list():
    id = request.args.get('idrequest')
    all_runs = NGSRun.query.all()
    all_barcodes = NGSBarcode.query.all()
    data = [ vars(f) for f in all_runs ]
    barcodes = [ vars(f) for f in all_barcodes ]
    for run in data:
        if run['flowcell']:
            collstate = get_import_state(run['flowcell'], 'minion::flowcell_id')
            run['datacoll'] = collstate
    return render_template('ngsruns.html', data=data, barcodes=barcodes, idrequest=id)

@bp.route('edit', methods=['GET'])
def edit_form():
    id = request.args.get('idrequest', '', type=str)
    run = NGSRun.query.filter(NGSRun.id == id).one_or_none()
    barcode_obj = NGSBarcode.query.filter(NGSBarcode.ngsrun == id).all()
    #barcodes = [ f.barcode for f in barcode_obj ] # maak een list van object
    data = { barcode : None for barcode in barcodes }
    for f in barcode_obj:
        data[f.barcode] = f
    print(run)
    print(run.flowcell)
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
    data = { barcode : None for barcode in barcodes }
    return render_template('ngsrun.html', data=data, barcodes=barcodes, id=-1)

@bp.route('new', methods=['POST'])
def run_update():
    f = request.form.to_dict()
    new_run = NGSRun(f.get('flowcell', ''))
    new_run.name = f.get('name', '')
    new_run.description = f.get('description', '')
    db.session.add(new_run)
    db.session.commit()
    for barcode in barcodes:
        if f.get('unilab_{}'.format(barcode)):
            new_barcode = NGSBarcode(new_run.id, barcode)
            new_barcode.unilab = f.get('unilab_{}'.format(barcode))
            new_barcode.virus_target = f.get('target_{}'.format(barcode))
            new_barcode.primer_set = f.get('primer_{}'.format(barcode))
            new_barcode.description = f.get('description_{}'.format(barcode))
            db.session.add(new_barcode)
    db.session.commit()
    return redirect(url_for('ngsruns.run_list'))
