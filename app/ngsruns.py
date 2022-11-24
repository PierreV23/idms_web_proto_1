from flask import Flask, current_app, Blueprint, flash, render_template, request, jsonify, redirect, url_for, session
from flask_login import current_user, login_required
from flask_marshmallow import Marshmallow
from marshmallow import Schema, fields, validate
from sqlalchemy.orm import relationship, remote, foreign, sessionmaker, scoped_session
from sqlalchemy import ForeignKey, distinct, create_engine, Column, Integer, String, TIMESTAMP, func, desc, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import OperationalError
from irods.models import Collection, CollectionMeta, User
from irods.column import Criterion
from app.datafield import datafield
import flask
import json
import requests
from requests.auth import HTTPBasicAuth
from app.projects import get_projectlist
from app.iqry import qcollbystaticmeta
from app.irodssessions import irods_manager

Base = declarative_base()

class NGSRunsDBUnavailableException(Exception):
    pass

class NGSRunsAlchemy:
    '''Handle db sessions for NGSRuns minilims database.'''

    def __init__(self):
        # Define a SQLAlchemy base class to wrap.
        self._sessions = {}
        self.default_env = None


    def init_app(self, app):
        for env_name, env in app.config.get('IRODS_ENVS', {}).items():
            if self.default_env is None and env.get('default', False):
                # Env in config with 'default' attr is assumed as default (e.g. 'Productie').
                self.default_env = env_name
            db_connect = env.get('minilims_db', 'sqlite://')
            connect_args = {}
            if db_connect.startswith('postgres'):
                connect_args = {'connect_timeout': 10}
            try:
                engine = create_engine(db_connect, connect_args=connect_args)
                Base.metadata.create_all(bind=engine)
            except OperationalError:
                # Unable to create connection to db. Continue to create
                # db engines for other envs.
                continue
            _sessionmaker = sessionmaker(autocommit=False, autoflush=False,
                                         bind=engine)
            self._sessions[env_name] = scoped_session(_sessionmaker, 
                scopefunc=flask._app_ctx_stack.__ident_func__)
        app.teardown_request(self.remove_session)

    def envs(self):
        return list(self._sessions)


    def session(self, environment=None):
        """Return session. If no specific environment is requested, use the one 
        defined in the user object, eventually fall back to `default_env`."""
        env = environment
        if environment is None:
            if hasattr(current_user, 'environment'):
                env = current_user.environment
            else:
                env = self.default_env
        
        try:
            return self._sessions[env]
        except KeyError:
            raise NGSRunsDBUnavailableException(f'env={env}')


    def remove_session(self, _exc=None):
        if hasattr(current_user, 'environment') and \
            current_user.environment in self._sessions:
            self._sessions[current_user.environment].remove()



db = NGSRunsAlchemy()

bp = Blueprint('ngsruns', __name__, url_prefix='/ngsruns')
ma = Marshmallow(bp)

REQUESTS_METHODS = {
    'GET':   requests.get,
    'PUT':   requests.put,
    'POST':  requests.post,
    'DELETE':requests.delete
}

class NGSRun(Base):
    #__bind_key__ = 'Production'
    __tablename__ = 'ngsruns'
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable = False)
    flowcell = Column(String(30), default='', nullable = False)
    creation_date = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)
    description = Column(String(250), default='', nullable = False)
    project = Column(String(32))
    owner = Column(String(32))

    def __init__(self, flowcell):
        self.flowcell = flowcell


class NGSBarcode(Base):
    #__bind_key__ = current_user.environment
    __tablename__ = 'ngsbarcodes'
    id = Column(Integer, primary_key=True)
    ngsrun = Column(Integer, ForeignKey('ngsruns.id'))
    barcode = Column(String(128), nullable = False)
    sampleid = Column(String(30), nullable = False)
    primer_set = Column(String(128), nullable = True)
    virus_target = Column(String(128), nullable = True)
    description = Column(String(256), nullable = True)
    creation_date = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)

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
        response = REQUESTS_METHODS[request_type](url, auth=auth, json=data)
    try:
        return_data = response.json()
    except:
        return_data = {}
    return return_data, response.status_code

@bp.route('complete/<field>', methods=['GET'])
def get_complete(field):
    req = request.args.to_dict().get('q', '')
    data1 = db.session().query(FIELDS[field]).filter(FIELDS[field].like('%{}%'.format(req))).distinct().all()
    return jsonify(data1)

@bp.route('_runs', methods=['GET'])
def runs():
    # Preparation for speedup: pagination for getting the list of runs,
    # for when getting the whole list (run_list()) takes too long.
    fields = ['id', 'name', 'flowcell', 'flowcell_display', 'project', 'owner', 'datacoll', 'description']
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 12))

    filterstr = request.args.get('filter', '{}')
    filters = json.loads(filterstr)

    sortfield = request.args.get('sort', 'id')
    sortorder = request.args.get('order', 'desc' if sortfield == 'id' else 'asc' )

    result = {}
    qry = db.session().query(NGSRun)
    for filter in filters:
        qry = qry.filter_by(**filters)
    qry = qry.order_by(text(f'{sortfield} {sortorder}'))
    qry = qry.limit(limit).offset(offset)
    data = [ vars(f) for f in qry ]
    for run in data:
        run['flowcell_display'] = run['flowcell']        
        colls = qcollbystaticmeta('minion::flow_cell_id', run['flowcell'])
        # q = irods_manager.session().query(Collection.name).filter( 
        #         Criterion('=', CollectionMeta.value, run['flowcell'])).filter( \
        #         Criterion('=', CollectionMeta.name, 'minion::flow_cell_id')).filter( \
        #         Criterion('like', Collection.name, '/rivmZone/projects/ngslab/minion/%'))
        # colls = [ x for x in q ]
        if colls:
            run['datacoll'] = datafield('collection', colls[0][Collection.name], 'irods_collection').htmlshort
        else:
            run['datacoll'] = ''
    rows = [ { f: str(d[f]) for f in fields} for d in data ]
    result['total'] = db.session().query(NGSRun).count()
    result['rows'] = rows
    return result

@bp.route('list', methods=['GET'])
def run_list():
    idrequest = request.args.get('idrequest', 0)
    data = [ vars(f) for f in db.session().query(NGSRun).all() ]
    # Create a list of flowcells and collections in irods
    with irods_manager.session() as session:
        q = session.query(Collection, CollectionMeta).filter( \
                Criterion('=', CollectionMeta.name, 'minion::flow_cell_id')).filter( \
                Criterion('=', Collection.parent_name, f'/{current_user.irods_zone}/projects/ngslab/minion'))
        flowcell_list = { x[CollectionMeta.value] : x[Collection.name] for x in q }
    flowcell_unique = set()
    flowcell_duplicate = set()
    for run in data:
        if run['flowcell'] in flowcell_unique:
            flowcell_duplicate.add(run['flowcell'])
        else:
            flowcell_unique.add(run['flowcell'])
        
        if run['flowcell'] and flowcell_list.get(run['flowcell']):
            run['datacoll'] = datafield('collection', str(flowcell_list.get(run['flowcell'])), 'irods_collection').htmlshort
        else:
            run['datacoll'] = ''
    
    for run in data:
        run['flowcell_display'] = run['flowcell']
        if run['flowcell'] in flowcell_duplicate:
            run['flowcell_display'] += ' (DUPLICATE)'

    data.sort(key = lambda x: x["id"], reverse=True)
    fields = ['id', 'name', 'flowcell', 'flowcell_display', 'project', 'owner', 'datacoll', 'description']
    data2 = [{ p:str(x[p]) for p in fields } for x in data ]
    return render_template('ngsruns.html', data=json.dumps(data2), 
        idrequest=idrequest, 
        default_project=current_user.settings.get('default_project', ''),
        projects = current_user.projects())

@bp.route('_barcodes', methods=['GET'])
def run_barcodes():
    id = request.args.get('idrequest', type=int)
    barcodes = db.session().query(NGSBarcode).filter(NGSBarcode.ngsrun == id).all()
    fields = [ 'barcode', 'description', 'primer_set', 'sampleid', 'virus_target']
    data = [ { p: getattr(x, p) for p in fields } for x in barcodes ]
    columns = [
        { "field": "barcode", "title": "Barcode", "sortable": True },
        { "field": "sampleid", "title": "ID", "sortable": True },
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
    run = db.session().query(NGSRun).filter(NGSRun.id == id).one_or_none()
    barcode_obj = db.session().query(NGSBarcode).filter(NGSBarcode.ngsrun == id).all()
    #barcodes = [ f.barcode for f in barcode_obj ] # maak een list van object
    data = { barcode : None for barcode in barcodes }
    for f in barcode_obj:
        data[f.barcode] = f
    data.update({"flowcell": run.flowcell})
    data.update({"name": run.name})
    data.update({"description": run.description})
    data.update({"project": run.project})
    data.update({"owner": run.owner})
    return render_template('ngsrun.html', data=data, barcodes=barcodes, id=id)

@bp.route('new', methods=['GET'])
def run_form():
    if current_app.config.get('MINILIMS_AUTHORS_GROUP') in current_user.groups():
        projectlist = get_projectlist().keys()
    else:
        projectlist = current_user.projects()
    data = { barcode : None for barcode in barcodes }
    # user=current_user.username
    return render_template('ngsrun.html', data=data, projects=projectlist, barcodes=barcodes, id=-1, default_project=current_user.settings.get('default_project', ''))

@bp.route('delete', methods=['GET'])
@login_required
def delete_ngs_run():
    if id := request.args.get('id', type=int):
        record = db.session().query(NGSRun).filter(NGSRun.id == id).one()
        if (project := record.project) not in current_user.projects():
            flash(f'You are not authorized to remove a sample sheet for project {project}', 'error')
            return redirect(url_for('ngsruns.run_list', idrequest=id))
        db.session().query(NGSBarcode).filter(NGSBarcode.ngsrun==id).delete()
        db.session().query(NGSRun).filter(NGSRun.id == id).delete()
        db.session().commit()
    return redirect(url_for('ngsruns.run_list'))

@bp.route('new', methods=['POST'])
def run_update():
    f = request.form.to_dict()
    new_run = NGSRun(f.get('flowcell', ''))
    new_run.name = f.get('name', '')
    new_run.project = f.get('project', '')
    new_run.owner = current_user.username
    new_run.description = f.get('description', '')

    if not(new_run.project in current_user.projects() or current_app.config.get('MINILIMS_AUTHORS_GROUP') in current_user.groups()):
            flash(f'You are not authorized to create a sample sheet for project {new_run.project}', 'error')
            return redirect(url_for('ngsruns.run_list'))  

    db.session().add(new_run)
    db.session().commit()
    for barcode in barcodes:
        if f.get('sampleid_{}'.format(barcode)):
            new_barcode = NGSBarcode(new_run.id, barcode)
            new_barcode.sampleid = f.get('sampleid_{}'.format(barcode)).replace(" ","")
            new_barcode.virus_target = f.get('target_{}'.format(barcode))
            new_barcode.primer_set = f.get('primer_{}'.format(barcode))
            new_barcode.description = f.get('description_{}'.format(barcode))
            db.session().add(new_barcode)
    db.session().commit()
    current_user.settings['default_project'] = new_run.project
    return redirect(url_for('ngsruns.run_list', idrequest=new_run.id))

# MiniLIMS API GET

@bp.route('/api/runs', methods=['GET'])
def get_ngs_runs():
    """Retrieve a list of all ngs runs
    """
    env = request.args.get('env', None)
    all_runs = db.session(env).query(NGSRun).all()
    dump = ngsruns_schema.dump(all_runs)
    return jsonify(dump)

@bp.route('/api/runs/<flowcell>', methods=['GET'])
def get_ngs_run(flowcell):
    """Retrieve a single ngs runs
    """
    env = request.args.get('env', None)
    ngsrun = db.session(env).query(NGSRun).filter(NGSRun.flowcell == flowcell).one_or_none()
    return jsonify(ngsrun_schema.dump(ngsrun))

@bp.route('/api/runs/<flowcell>/barcodes', methods=['GET'])
def get_ngs_barcodes(flowcell):
    """Retrieve barcodes for a single ngs runs
    """
    env = request.args.get('env', None)
    ngsrun = db.session(env).query(NGSRun).filter(NGSRun.flowcell == flowcell).one_or_none()
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).all()
    return jsonify(barcodes_schema.dump(barcodes))
