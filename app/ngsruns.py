from flask import Flask, current_app, Blueprint, flash, render_template, request, jsonify, redirect, url_for, session
from flask_login import current_user, login_required
from flask_marshmallow import Marshmallow
from marshmallow import Schema, fields, validate
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import ForeignKey, create_engine, Column, Integer, String, TIMESTAMP, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.hybrid import hybrid_property
from irods.models import Collection, CollectionMeta, User
from irods.column import Criterion
from app.datafield import datafield
import flask
from .flaskcache import cache, key_zone
import greenlet
import json
import requests
from requests.auth import HTTPBasicAuth
from app.projects import get_projectlist
from app.iqry import qcollbystaticmeta
from app.irodssessions import irods_manager
from app.settings import NGSRUN_FIELDS

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
                scopefunc=greenlet.getcurrent)
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
            return self._sessions[env]()
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
    offset = request.args.get('offset', 0)
    limit = request.args.get('limit', 12)
    filters = json.loads(request.args.get('filter', '{}'))
    sort = request.args.get('sort', 'creation_date')
    order = request.args.get('order', 'desc')

    result = {}
    # fetch ngsruns
    ngsruns = db.session().query(NGSRun)

    # Count 'flowcell' to detect and label DUPLICATE records
    flowcell_list = [f.flowcell for f in ngsruns.all()]
    flowcell_dupl = {f:' (DUPLICATE)' if flowcell_list.count(f) > 1 else '' for f in flowcell_list}

    # Apply filters on ngsruns ('select' and 'input')
    for _, field_attrs in NGSRUN_FIELDS.items():
        field_name = field_attrs['field']
        filter_value = filters.get(field_name)
        filter_control = field_attrs.get('filtercontrol')
        if not filter_value or filter_control is None:
            continue
        if filter_control == 'select':
            ngsruns = ngsruns.filter(text(f"{field_name}='{filter_value}'"))
        if filter_control == 'input':
            ngsruns = ngsruns.filter(text(f"{field_name} like('%{filter_value}%')"))

    ngsruns = ngsruns.order_by(text(f'{sort} {order}'))

    # count total after filter
    count_runs = ngsruns.count() 
    ngsruns = ngsruns.offset(offset).limit(limit)

    # format data ngsruns
    result = []
    for run in ngsruns:
        record = {}
        for f in NGSRUN_FIELDS:
            key = NGSRUN_FIELDS[f]['field']
            val = getattr(run, key, None)
            if key == 'flowcell' and val is not None:
                # append (DUPLICATE) to flowcell name
                val += flowcell_dupl.get(val)
            if val is not None:
                formatted = datafield(key, val, NGSRUN_FIELDS[f]['format'])
                record |= { key: formatted.htmlshort, f'_{key}': formatted.value }
        result.append(record)

    for run in result:
        # find collection matching for flowcell
        colls = qcollbystaticmeta('minion::flow_cell_id', run['flowcell'])
        # sort by create_time to get first collection name 
        colls = sorted(colls, key = lambda k: k[Collection.create_time])
        # format available collection name
        if colls:            
            run['datacoll'] = datafield('collection', colls[0][Collection.name], 'irods_collection').htmlshort
        else:
            run['datacoll'] = ''

    return { 'rows': result, 'filters': filters, 'total': count_runs }


@bp.route('list', methods=['GET'])
def run_list():
    idrequest = request.args.get('idrequest', 0)
    return render_template('ngsruns.html',  
        idrequest=idrequest, columns = NGSRUN_FIELDS,
        default_project=current_user.settings.get('default_project', ''),
        projects = current_user.projects())


@bp.route('_filterdata')
@cache.cached(timeout=60, key_prefix=key_zone)
def filterdata():
# Determine prepopulated filter values for 'select' filters
    field = request.args.get('field', type=str)
    ngsruns = db.session().query(NGSRun)

    # find distinct values for fields, exclude '' and None
    filter_values = {i:i for i in set([ getattr(r, field, None) for r in ngsruns]) if i not in ['', None]}
    return jsonify(filter_values)


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
