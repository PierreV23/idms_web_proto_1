from flask import current_app, Blueprint, flash, render_template, request, jsonify, redirect, url_for
from flask_login import current_user, login_required
from flask_marshmallow import Marshmallow
from marshmallow import fields, validate
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import ForeignKey, create_engine, Column, Integer, String, TIMESTAMP, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import OperationalError, ArgumentError, MultipleResultsFound, NoResultFound
from irods.models import Collection
from app.utils.datafield import datafield
from .utils.flaskcache import cache, key_zone
import greenlet
import json
import requests
from requests.auth import HTTPBasicAuth
from app.projects import get_projectlist
from app.utils.cached_iqry import qcollbystaticmeta, qcollmetaval
from app.settings import NGSRUN_FIELDS, BARCODE_FIELDS

Base = declarative_base()


SESSION = 'session'
VERSION = 'version'

class NGSRunsDBUnavailableException(Exception):
    pass

class NGSRunsAlchemy:
    '''Handle db sessions for NGSRuns minilims database.'''

    def __init__(self):
        # Define a SQLAlchemy base class to wrap.
        self._sessions = {}
        self.default_env = None
        self._versions = {}


    def init_app(self, app):
        for env_name, env in app.config.get('IRODS_ENVS', {}).items():
            if self.default_env is None and env.get('default', False):
                # Env in config with 'default' attr is assumed as default (e.g. 'Productie').
                self.default_env = env_name
            db_connect = env.get('minilims_db', '')
            connect_args = {}
            if db_connect.startswith('postgres'):
                connect_args = {'connect_timeout': 10}
            try:
                engine = create_engine(db_connect, connect_args=connect_args)
            except (OperationalError, ArgumentError):
                # Unable to create connection to db. Continue to create
                # db engines for other envs.
                continue
            _sessionmaker = sessionmaker(autocommit=False, autoflush=False,
                                        bind=engine)
            session = scoped_session(_sessionmaker,
                scopefunc=greenlet.getcurrent)

            # test if the database exist or not
            try:
                session.execute(text("SELECT 1"))
            # does not exist, assign None for the session
            except OperationalError as e:
                continue

            self._sessions[env_name] = {SESSION: session}
            # Determine DB version
            q = text("select count(*) as versiontables from information_schema.tables where table_name = 'version'")
            column = Column("versiontables", Integer)

            if session.execute(q.columns(column)).all()[0][column] == 0:
                version = 1
            else:
                q = text("SELECT version FROM version;")
                column = Column("version", Integer)
                version = session.execute(q.columns(column)).all()[0][column]
            self._sessions[env_name][VERSION] = version

        app.teardown_request(self.remove_session)

    def envs(self):
        return list(self._sessions)

    def _sessiondict(self, environment=None):
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

    def session(self, environment=None):
        return self._sessiondict(environment)[SESSION]

    def version(self, environment=None):
        return self._sessiondict(environment)[VERSION]

    def remove_session(self, _exc=None):
        if hasattr(current_user, 'environment') and \
            current_user.environment in self._sessions:
            self._sessions[current_user.environment][SESSION].remove()

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
    owner = Column(String(32))

    def __init__(self, flowcell):
        self.flowcell = flowcell

class NGSRunView(Base):
    __tablename__ = 'v_ngsruns'
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable = False)
    flowcell = Column(String(30), default='', nullable = False)
    creation_date = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)
    description = Column(String(250), default='', nullable = False)
    project = Column(String(32))
    owner = Column(String(32))
    duplicate = False

class NGSBarcode(Base):
    #__bind_key__ = current_user.environment
    __tablename__ = 'ngsbarcodes'
    id = Column(Integer, primary_key=True)
    ngsrun = Column(Integer, ForeignKey('ngsruns.id'))
    enabled = Column(String(32), nullable=False, default='true')
    barcode = Column(String(128), nullable = False)
    sampleid = Column(String(30), nullable = False)
    primer_set = Column(String(128), nullable = True)
    virus_target = Column(String(128), nullable = True)
    kit = Column(String(128), nullable = True)
    description = Column(String(256), nullable = True)
    project = Column(String(32))
    creation_date = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)

    def __init__(self, ngsrun, barcode):
        self.ngsrun = ngsrun
        self.barcode = barcode

class Kits(Base):
    #__bind_key__ = current_user.environment
    __tablename__ = 'kits'
    id = Column(Integer, primary_key=True)
    kit = Column(String(128), nullable = False)
    start_date = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)
    end_date = Column(TIMESTAMP, nullable=True)

    def __init__(self, kit, end_date=None):
        self.kit = kit
        if end_date:
            self.end_date = end_date

class NGSRunSchema(ma.Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(1))
    flowcell = fields.String(required=True)
    description = fields.String()
    project = fields.String()

class NGSBarcodesSchema(ma.Schema):
    enabled = fields.String()
    barcode = fields.String()
    primer_set = fields.String()
    sampleid = fields.String()
    virus_target = fields.String()
    kit = fields.String()
    description = fields.String()
    project = fields.String()

class KitsSchema(ma.Schema):
    id = fields.Integer(dump_only=True)
    kit = fields.String(required=True, validate=validate.Length(1))

ngsrun_schema = NGSRunSchema()
ngsruns_schema = NGSRunSchema(many=True)
barcodes_schema = NGSBarcodesSchema(many=True)
kits_schema = KitsSchema()

barcodes = [ 'barcode{:02d}'.format(bar) for bar in range(1,97) ]

FIELDS = {
    'virus_target': NGSBarcode.virus_target,
    'primer_set': NGSBarcode.primer_set,
    'kit': NGSBarcode.kit
}

def minilims_authorized_for_projects(projectlist):
    """Check if a user is authorized to make/delete a minilims samplesheet

    Args:
        projectlist (list): List of project names in sample sheet

    Returns:
        bool, list: True if authorized, False if not. list is list of unauthorized projects
    """
    if current_app.config.get('MINILIMS_AUTHORS_GROUP') in current_user.groups():
        return True, []
    unauthorized_projects = [ project for project in projectlist if not project in current_user.projects() and project ]
    return not bool(unauthorized_projects), unauthorized_projects

def projects_in_run(id):
    """Return a list of all project names in the run

    Args:
        id (int): id of the ngsrun

    Returns:
        list: List of project names
    """
    return { b.project for b in db.session().query(NGSBarcode).filter(NGSBarcode.ngsrun==id).all() }

def rest_call(request_type, endpoint, data={}):
    url = 'http://{}/api/1.0/{}'.format(current_user.irods_server, endpoint)
    #TODO: remove this testing line:
    #url = 'http://{}/api/1.0/{}'.format('0.0.0.0:5000', endpoint)
    auth = HTTPBasicAuth(current_user.username, current_user.password)
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
    data1 = [ d[field] for d in db.session().query(FIELDS[field]).filter(FIELDS[field].like('%{}%'.format(req))).distinct().all()]
    return jsonify(data1)

def process_param(param, *args, **kwargs):
# Check if the parameter is a function/lambda
    if callable(param):
        return param(*args, **kwargs)
    # If not callable, treat it as a constant
    return param    

@bp.route('_runs', methods=['GET'])
def runs():
    offset = request.args.get('offset', 0)
    limit = request.args.get('limit', 12)
    filters = json.loads(request.args.get('filter', '{}'))
    sort = request.args.get('sort', 'creation_date')
    order = request.args.get('order', 'desc')

    result = {}
    # fetch ngsruns
    ngsruns = db.session().query(NGSRunView)

    # Count 'flowcell' to detect and label DUPLICATE records
    flowcell_list = [f.flowcell for f in ngsruns.all()]
    flowcell_dupl = [f for f in flowcell_list if flowcell_list.count(f) > 1]

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
                record['duplicate'] = val in flowcell_dupl
            if val is not None:
                formatted = datafield(key, val, process_param(NGSRUN_FIELDS[f]['format'], key, val))
                record |= { key: formatted.htmlshort, f'_{key}': formatted.value }
            # Check the projects in this run
        projects = projects_in_run(run.id)
        authorized, _ = minilims_authorized_for_projects(projects)
        record['_authorized'] = authorized
        result.append(record)

    for run in result:
        # find collection matching for flowcell
        colls = qcollbystaticmeta('minion::flow_cell_id', run['flowcell'])
        # sort by create_time to get first collection name
        colls = sorted(colls, key = lambda k: k[Collection.create_time])
        # Find import collection. They have data type 'imported'
        # To distinguish between raw and basecalled data, we check the ID metadata attr. 
        # This is only present on de basecalled data collections
        import_colls = [ c for c in colls 
                        if qcollmetaval(c[Collection.name], 'sys::data::type') == 'imported'
                        and qcollmetaval(c[Collection.name], 'ID') is not None ]
        # If there are multiple collections, match the id
        if len(import_colls) > 1:
            reuse_import_colls = [ c for c in import_colls if qcollmetaval(c[Collection.name], 'minion::sample_id') == run.get('id') ]
            if len(reuse_import_colls):
                import_colls = reuse_import_colls
        run['datacoll'] = '<p>'.join([ datafield('collection', c[Collection.name], 'irods_collection').htmlshort for c in import_colls ])              

    return { 'rows': result, 'filters': filters, 'total': count_runs }

def deprecated_message(menuname):
    text = """
<h3>
This version of iDMS does not support version 1 of the MiniLIMS database.<p>
<p>Try accessing the MiniLIMS through <a href="https://biorods.rivm.nl">iDMS production</a>.
<p>If that does not work, contact support through the <a href="{contacts}">contacts</a> page.
</h3>
""".format(contacts=url_for('about'))
    return render_template('deprecated.html', text=text, menuname=menuname)

@bp.route('list', methods=['GET'])
@login_required
def run_list():
    if db.version() < 2:
        return deprecated_message(menuname='runlist')

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

    ngsruns = db.session().query(NGSRunView)

    # find distinct values for fields, exclude '' and None
    filter_values = {i:i for i in set([ getattr(r, field, None) for r in ngsruns]) if i not in ['', None]}
    return jsonify(filter_values)


@bp.route('_barcodes', methods=['GET'])
def run_barcodes():
    id = request.args.get('idrequest', type=int)
    barcodes = db.session().query(NGSBarcode).filter(NGSBarcode.ngsrun == id).all()
    fields = [ v.get("field") for k, v in BARCODE_FIELDS.items() ]
    data = [ { p: getattr(x, p) for p in fields } for x in barcodes ]
    columns = [ v for _, v in BARCODE_FIELDS.items() ]
    data = {
        'columnsJSON': json.dumps(columns),
        'dataJSON': json.dumps(data),
        'id': 'barcodetable'
    }
    return render_template('bootstraptable.html', data=data, no_page=True)

@bp.route('new', methods=['GET'])
@login_required
def run_form():
    action = 'new_form'
    if db.version() < 2:
        return deprecated_message(menuname='newrun')
    if current_app.config.get('MINILIMS_AUTHORS_GROUP') in current_user.groups():
        projectlist = get_projectlist().keys()
    else:
        projectlist = current_user.projects()
    data = { barcode : None for barcode in barcodes }
    selected_id = int(request.args.get('id', -1))
    if selected_id > 0:
        action = 'edit_form'
        authorized, unauthorized_projects = minilims_authorized_for_projects(projects_in_run(selected_id))
        if not authorized:
            flash(f'You are not authorized to edit a sample sheet for project(s) {",".join(unauthorized_projects)}', 'error')
            return redirect(url_for('ngsruns.run_list', idrequest=selected_id))
        run = db.session().query(NGSRun).filter(NGSRun.id == selected_id).one_or_none()
        if run is None:
            flash(f'Run {selected_id} does not exist', 'error')
            return redirect(url_for('ngsruns.run_list', idrequest=selected_id))
        # Copy run properties
        for attr in ['name', 'flowcell', 'description', 'owner']:
            data[attr] = getattr(run, attr)
        barcode_obj = db.session().query(NGSBarcode).filter(NGSBarcode.ngsrun == selected_id).all()
        for f in barcode_obj:
            data[f.barcode] = f
    kits = get_kits()
    return render_template('ngsrun.html', data=data, projects=projectlist, barcodes=barcodes, id=selected_id, default_project=current_user.settings.get('default_project', ''), kits=kits, action=action)

@bp.route('delete', methods=['GET'])
def delete_ngs_run():
    if id := request.args.get('id', type=int):
        authorized, unauthorized_projects = minilims_authorized_for_projects(projects_in_run(id))
        if not authorized:
            flash(f'You are not authorized to remove a sample sheet for project(s) {",".join(unauthorized_projects)}', 'error')
            return redirect(url_for('ngsruns.run_list', idrequest=id))
        db.session().query(NGSBarcode).filter(NGSBarcode.ngsrun==id).delete()
        db.session().query(NGSRun).filter(NGSRun.id == id).delete()
        db.session().commit()
    return redirect(url_for('ngsruns.run_list'))

# Fetch the kits for the drop down
def get_kits():
    kits = db.session().query(Kits.kit).distinct().all()
    return sorted([kit[0] for kit in kits])

@bp.route('new', methods=['POST'])
def run_update():
    f = request.form.to_dict()
    if ( run_id := int(f.get('id', -1))) > 0:
        # Update existing run
        modify_run = db.session().query(NGSRun).filter(NGSRun.id == run_id).one_or_none()
        if not modify_run:
            flash(f'Runsheet {run_id} does not exist', 'error')
            return redirect(url_for('ngsruns.run_list'))
        modify_run.flowcell = f.get('flowcell', '')
    else:
        modify_run = NGSRun(f.get('flowcell', ''))
    modify_run.name = f.get('name', '')
    modify_run.owner = current_user.username
    modify_run.description = f.get('description', '')

    # Check if user is authorized
    # either the user is in MINILIMS_AUTHORS_GROUP
    # or he/she is a member of all projects in the runsheet
    projects = { f.get(f'project_{barcode}') for barcode in barcodes if f.get(f'sampleid_{barcode}') }
    authorized, invalid_projects = minilims_authorized_for_projects(projects)
    if not authorized:
        flash(f'You are not authorized to create a sample sheet for projects {",".join(invalid_projects)}', 'error')
        return redirect(url_for('ngsruns.run_list'))

    db.session().add(modify_run)
    db.session().commit()
    # If this is a modify, delete all barcodes
    # They will be recreated
    if run_id > 0:
        db.session().query(NGSBarcode).filter(NGSBarcode.ngsrun==run_id).delete()
    for barcode in barcodes:
        if f.get(f'sampleid_{barcode}'):
            new_barcode = NGSBarcode(modify_run.id, barcode)
            new_barcode.enabled = f.get(f'enabled_{barcode}', 'true')
            new_barcode.sampleid = f.get(f'sampleid_{barcode}').replace(" ","")
            new_barcode.virus_target = f.get(f'target_{barcode}')
            new_barcode.primer_set = f.get(f'primer_{barcode}')
            new_barcode.kit = f.get(f'kit_{barcode}')
            new_barcode.description = f.get(f'description_{barcode}')
            new_barcode.project = f.get(f'project_{barcode}')
            db.session().add(new_barcode)
    db.session().commit()
    
    # determine new kits added in form
    current_kits = get_kits()
    new_kits = {v for k, v in f.items() if k.startswith('kit') and v != '' and v not in current_kits}
    
    # add new kits to the database table for future selectivity
    for nk in new_kits:
        new_kit = Kits(nk)
        db.session().add(new_kit)
    db.session().commit()

    if len(projects) == 1:
        current_user.settings['default_project'] = projects.pop()
    return redirect(url_for('ngsruns.run_list', idrequest=modify_run.id))

# MiniLIMS API GET

@bp.route('/api/runs', methods=['GET'])
def get_ngs_runs():
    """Retrieve a list of all ngs runs
    """
    env = request.args.get('env', None)
    all_runs = db.session(env).query(NGSRunView).all()
    dump = ngsruns_schema.dump(all_runs)
    return jsonify(dump)

@bp.route('/api/runs/<flowcell>', methods=['GET'])
def get_ngs_run(flowcell):
    """Retrieve a single ngs runs
    """
    env = request.args.get('env', None)
    ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.flowcell == flowcell).one_or_none()
    return jsonify(ngsrun_schema.dump(ngsrun))

@bp.route('/api/runs/<flowcell>/barcodes', methods=['GET'])
def get_ngs_barcodes(flowcell):
    """Retrieve all barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.flowcell == flowcell).one_or_none()
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).all()
    return jsonify(barcodes_schema.dump(barcodes))

@bp.route('/api/runs/<flowcell>/barcodes/enabled', methods=['GET'])
def get_ngs_barcodes_enabled(flowcell):
    """Retrieve all enabled barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.flowcell == flowcell).one_or_none()
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).filter(NGSBarcode.enabled == 'true').all()
    return jsonify(barcodes_schema.dump(barcodes))

@bp.route('/api/runs/<flowcell>/barcodes/disabled', methods=['GET'])
def get_ngs_barcodes_disabled(flowcell):
    """Retrieve all disabled barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.flowcell == flowcell).one_or_none()
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).filter(NGSBarcode.enabled == 'false').all()
    return jsonify(barcodes_schema.dump(barcodes))

@bp.route('/api/v2/runs', methods=['GET'])
def get_v2_ngs_runs():
    """Retrieve a list of all ngs runs
    """
    env = request.args.get('env', None)
    all_runs = db.session(env).query(NGSRunView).all()
    dump = ngsruns_schema.dump(all_runs)
    return jsonify(dump)

@bp.route('/api/v2/runs/flowcell/<flowcell>', methods=['GET'])
def get_v2_ngs_runs_by_flowcell(flowcell):
    """Retrieve ngs runs by flowcell
    """
    env = request.args.get('env', None)
    ngsruns = db.session(env).query(NGSRunView).filter(NGSRunView.flowcell == flowcell).all()
    return jsonify(ngsruns_schema.dump(ngsruns))

@bp.route('/api/v2/runs/id/<runid>', methods=['GET'])
def get_v2_ngs_runs_by_id(runid):
    """Retrieve ngs runs by id
    """
    env = request.args.get('env', None)
    try:
        ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.id == runid).one()
    except NoResultFound:
        return jsonify({'Error': f'Run id {runid} not found'}), 404
    return jsonify(ngsrun_schema.dump(ngsrun))

@bp.route('/api/v2/runs/flowcell/<flowcell>/barcodes', methods=['GET'])
def get_v2_ngs_barcodes_by_flowcell(flowcell):
    """Retrieve all barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    try:
        ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.flowcell == flowcell).one()
    except MultipleResultsFound:
        return jsonify({'Error': f'Multiple results found for flowcell {flowcell}'}), 400
    except NoResultFound:
        return jsonify({'Error': f'Flowcell {flowcell} not found'}), 404
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).all()
    return jsonify(barcodes_schema.dump(barcodes))

@bp.route('/api/v2/runs/flowcell/<flowcell>/barcodes/enabled', methods=['GET'])
def get_v2_ngs_barcodes_by_flowcell_enabled(flowcell):
    """Retrieve all enabled barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    try:
        ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.flowcell == flowcell).one()
    except MultipleResultsFound:
        return jsonify({'Error': f'Multiple results found for flowcell {flowcell}'}), 400
    except NoResultFound:
        return jsonify({'Error': f'Flowcell {flowcell} not found'}), 404
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).filter(NGSBarcode.enabled == 'true').all()
    return jsonify(barcodes_schema.dump(barcodes))

@bp.route('/api/v2/runs/flowcell/<flowcell>/barcodes/disabled', methods=['GET'])
def get_v2_ngs_barcodes_by_flowcell_disabled(flowcell):
    """Retrieve all disabled barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    try:
        ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.flowcell == flowcell).one()
    except MultipleResultsFound:
        return jsonify({'Error': f'Multiple results found for flowcell {flowcell}'}), 400
    except NoResultFound:
        return jsonify({'Error': f'Flowcell {flowcell} not found'}), 404
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).filter(NGSBarcode.enabled == 'false').all()
    return jsonify(barcodes_schema.dump(barcodes))


@bp.route('/api/v2/runs/id/<runid>/barcodes', methods=['GET'])
def get_v2_ngs_barcodes_by_id(runid):
    """Retrieve all barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    try:
        ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.id == runid).one()
    except NoResultFound:
        return jsonify({'Error': f'Run id {runid} not found'}), 404
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).all()
    return jsonify(barcodes_schema.dump(barcodes))

@bp.route('/api/v2/runs/id/<runid>/barcodes/enabled', methods=['GET'])
def get_v2_ngs_barcodes_by_id_enabled(runid):
    """Retrieve all enabled barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    try:
        ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.id == runid).one()
    except NoResultFound:
        return jsonify({'Error': f'Run id {runid} not found'}), 404
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).filter(NGSBarcode.enabled == 'true').all()
    return jsonify(barcodes_schema.dump(barcodes))

@bp.route('/api/v2/runs/id/<runid>/barcodes/disabled', methods=['GET'])
def get_v2_ngs_barcodes_by_id_disabled(runid):
    """Retrieve all disabled barcodes for a single ngs run
    """
    env = request.args.get('env', None)
    try:
        ngsrun = db.session(env).query(NGSRunView).filter(NGSRunView.id == runid).one()
    except NoResultFound:
        return jsonify({'Error': f'Run id {runid} not found'}), 404
    barcodes = db.session(env).query(NGSBarcode).filter(NGSBarcode.ngsrun == ngsrun.id).filter(NGSBarcode.enabled == 'false').all()
    return jsonify(barcodes_schema.dump(barcodes))
