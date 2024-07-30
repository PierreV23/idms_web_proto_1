#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 13:49:12 2019

@author: wierinve
"""

from flask import Blueprint, render_template, request, url_for, jsonify, redirect, flash, current_app
from flask_login import current_user, login_required
from irods.exception import DataObjectDoesNotExist, CAT_NO_ACCESS_PERMISSION
from irods.models import Collection, CollectionMeta
from irods.column import Criterion
from app.datafield import datafield
from app.settings import JOB_FIELDS, PG_FIELDS, PG_JOB_FIELDS
from graphviz import Digraph
import flask
import greenlet
import json
import os
import sys
import time
from datetime import datetime, timezone
from .flaskcache import cache, dep_zone, key_zone, key_userzone
from app.irodssessions import irods_manager
from . import iqry
from . import constants
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

bp = Blueprint('jobs', __name__, url_prefix='/jobs')

ATTR_RUNSHEET_PREFIX = 'sys::runsheet::'
ATTR_RUNSHEET_STATE = '{}state'.format(ATTR_RUNSHEET_PREFIX)
ATTR_RUNSHEET_ID = '{}id'.format(ATTR_RUNSHEET_PREFIX)
ATTR_RUNSHEET_CREATETIME = '{}create_time'.format(ATTR_RUNSHEET_PREFIX)
ATTR_RUNSHEET_PROCESSGROUPGUID = '{}processgroupid'.format(ATTR_RUNSHEET_PREFIX)

MAX_READ_LOG_BYTES = 10000000


def my_env():
    """Return environment the current_user is logged in to 
       or None if not set
    Returns:
        str: environment name
    """    
    if hasattr(current_user, 'environment'):
        return current_user.environment        
    return None
class JobsDBUnavailableException(Exception):
    pass

class DBConnection:
    
    def __init__(self, pool):
        self._pool = pool
              
    def sql(self, statement):
        with self as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(statement)
            if cursor.rowcount == 0:
                return []
            else:
                return cursor.fetchall()            
        
    def __enter__(self):
        self._conn = self._pool.getconn()
        return self._conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._pool.putconn(self._conn)

class DBPools:
    
    def __init__(self):
        self._pools = {}

    def init_app(self, app):
        pass
        #app.teardown_request(self.remove_session)
        
    def startpool(self):
        env = my_env()
        env_params = current_app.config.get('IRODS_ENVS', {}).get(env)
        db_connect = env_params.get('jobs_db')
        self._pools[env] = pool.ThreadedConnectionPool(1, 50, db_connect)
        
    def connection(self):
        env = my_env()
        if not env in self._pools:
            self.startpool()
        if env in self._pools:
            return DBConnection(self._pools.get(env))
        else:
            raise JobsDBUnavailableException(f'env={env}')


db = DBPools()

# @bp.before_request
# def before_request_func():
#     # This ensures the flash error message will show up if the job table is not available
#     db.connection()

def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)

def timestamp_to_local(timestamp):
    utc_dt = datetime.utcfromtimestamp(float(timestamp))
    return utc_to_local(utc_dt)

def pagebuttons(page_size, count, current_page, max_buttons, template):
    pagebuttons = []
    pages = count // page_size + 1
    for buttonnr in range(0, pages):
        button = { 'text': '{} - {}'.format(buttonnr*constants.JOB_PAGE_SIZE+1, min((buttonnr+1)*constants.JOB_PAGE_SIZE, count)),
                   'button': True, 'ref': template.format(buttonnr+1), 'class': 'btn-success'}
        if buttonnr == current_page-1:
            button['class'] = 'btn-outline-success'
            button['ref'] = ''
        pagebuttons.append(button)
    dotbutton = { 'text': '...', 'button': False}
    # Create a slice if the page list is too long
    if pages > max_buttons:
        hbc = max_buttons // 2 - 1        
        if current_page>hbc:
            before = [pagebuttons[0]] + [dotbutton] + pagebuttons[current_page-hbc:current_page]
        else:
            before = pagebuttons[:current_page]
        remain = max_buttons - len(before)
        if pages-current_page>remain:
            after = pagebuttons[current_page:current_page+remain] + [dotbutton] + [pagebuttons[-1]]
        else:
            after = pagebuttons[current_page:]
    else:
        before = pagebuttons
        after = []
    return before + after
    

@bp.route('/api/pgprocs')
def processgroupprocs():
    PGFIELDS = {
        'sys::runsheet::id': ('runsheet', 'runsheet'),
        'sys::runsheet::description' : ('description', 'text'),
        'sys::runsheet::state': ('state', 'text'),
        'sys::run::result': ('result', 'text'),
        'user::run::exit_code': ('result', 'text'),
        'sys::run::start_time': ('start', 'timestamp'),
        'sys::run::finish_time': ('end', 'timestamp'),
    }
    processgroupguid = request.args.get('processgroupguid')
    q = iqry.qcollbymeta('sys::runsheet::processgroupid', processgroupguid)
    result = []
    for r in q:
        metadata = iqry.qcollmetadict(r[Collection.name])
        job = {}
        for field in PGFIELDS:
            if metadata.get(field):
                job[PGFIELDS[field][0]] = datafield(PGFIELDS[field][0], metadata.get(field,''), PGFIELDS[field][1]).htmlstring
#        job = { PGFIELDS[field][0]: datafield(PGFIELDS[field][0], metadata.get(field,''), PGFIELDS[field][1]).htmlstring for field in PGFIELDS }
        result.append(job)
    return { 'rows': result }
    
@bp.route('jobpage')
def jobpage():
    preferred_page = current_user.settings.setdefault('jobs::view', 'jobs')
    if preferred_page == 'processgroups':
        return redirect(url_for('jobs.show_pg'))
    return redirect(url_for('jobs.show_jobs')) 

@bp.route('_jobs')
def jobs():
# populate jobtable
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 999, type=int)
    filters = json.loads(request.args.get('filter', '{}'))
    sort = request.args.get('sort', 'create_time')
    order = request.args.get('order', 'desc')
    
    current_user.settings['default_project'] = filters.get('projectid', '')

    where_clause = 'where 1=1'
    
    # Apply filters on jobs_query ('select' and 'input')
    for _, field_attrs in JOB_FIELDS.items():
        field_name = field_attrs['field']
        filter_value = filters.get(field_name)
        filter_control = field_attrs.get('filtercontrol')
        if not filter_value or filter_control is None:
            continue
        if filter_control == 'select':
            where_clause = f"{where_clause} and {field_name}='{filter_value}'"
        if filter_control == 'input':
            where_clause = f"{where_clause} and {field_name} like('%{filter_value}%')"
    
    # order; default second order by start_time desc, after filter takes less time

    sqlj = f'select * from rivm_mat_jobtable {where_clause} order by {sort} {order}, create_time desc, start_time desc offset {offset} limit {limit}'
    sqlc = f'select count(*) from rivm_mat_jobtable {where_clause}'
    with db.connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(sqlc)
        result_jobcount = cursor.fetchall()
        cursor.execute(sqlj)
        jobs_query = cursor.fetchall()
    
    # count, offset, limit data
    count_jobs = result_jobcount[0]['count']

    # format data jobs_query
    result = []
    for job in jobs_query:
        record = {}
        for f in JOB_FIELDS:
            dbkey = JOB_FIELDS[f]['field']
            val = job.get(dbkey, None)
            if val is not None:
                formatted = datafield(dbkey, val, JOB_FIELDS[f]['format'])
                record |= { dbkey: formatted.htmlshort, f'_{dbkey}': formatted.value }
        result.append(record)
    
    return { 'rows': result, 'filters': filters, 'total': count_jobs }


@bp.route('_filterdata')
@cache.cached(timeout=60, key_prefix=key_zone)
def filterdata():
# Determine prepopulated filter values for 'select' filters
    field = request.args.get('field', type=str)
    table = request.args.get('table', type=str)
    
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT {field} FROM {table} WHERE {field} IS NOT NULL")
        results = cursor.fetchall()
    filter_values = {v[0]:v[0] for v in results}
    return jsonify(filter_values)


@bp.route('_pglist')
def pglist():
#POPULATE processgrouplist
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 999, type=int)
    filters = json.loads(request.args.get('filter', '{}'))
    order = request.args.get('order', 'desc')
    sort = request.args.get('sort', 'create_time')
    processgroupid = request.args.get('processgroupid', None, type=str)
    current_user.settings['default_project'] = filters.get('projectid', '')

    where_clause = 'where 1=1'

    if processgroupid:
        where_clause = f'{where_clause} and processgroupid={processgroupid}'
   
    # Apply filters on pgs_query ('select' and 'input')
    for _, field_attrs in PG_FIELDS.items():
        field_name = field_attrs['field']
        filter_value = filters.get(field_name)
        filter_control = field_attrs.get('filtercontrol')
        if not filter_value or filter_control is None:
            continue
        if filter_control == 'select':
            where_clause = f"{where_clause} and {field_name}='{filter_value}'"
        if filter_control == 'input':
            where_clause = f"{where_clause} and {field_name} like('%{filter_value}%')"

    fieldlist = { PG_FIELDS[v]['field'] for v in PG_FIELDS.keys() }
    fields = ','.join(fieldlist)
    # Most efficient to use separate queries for total row count and page of processgroups
    sqlj = f'select {fields} from rivm_v_processgroups {where_clause} order by {sort} {order} offset {offset} limit {limit}'
    sqlc = f'select count(*) from rivm_v_processgroups {where_clause}'

    with db.connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(sqlc)
        c_query = cursor.fetchall()
        cursor.execute(sqlj)
        pgs_query = cursor.fetchall()

    count_jobs = c_query[0]['count']

    # format data pgs_query
    result = []
    for processgroup in pgs_query:
        record = {}
        for f in PG_FIELDS:
            dbkey = PG_FIELDS[f]['field']
            val = processgroup.get(dbkey, None)
            if val is not None:
                formatted = datafield(dbkey, val, PG_FIELDS[f]['format'])
                record |= { dbkey: formatted.htmlshort, f'_{dbkey}': formatted.value }
        result.append(record)
    
    return { 'rows': result, 'filters': filters, 'total': count_jobs }

@bp.route('_jobrefresh')
def jobs_refresh():
    sql = 'select max(refresh_time) from rivm_mat_jobtable'
    result = db.connection().sql(sql)
    if not result:
        return jsonify('unknown')
    else:
        return jsonify(datafield('refresh_time', float(result[0]['max']), 'timestamp').htmlshort)
 

@bp.route('_pgjobs')
def pgjobs():
# display jobs under a processgroupid
    processgroupid = request.args.get('processgroupid', None, type=str)

    result = []

    sql = f"select * from rivm_mat_jobtable where processgroupid='{processgroupid}'"

    jobs_query = db.connection().sql(sql)

    for job in jobs_query:
        record = {}
        for f in PG_JOB_FIELDS:
            dbkey = PG_JOB_FIELDS[f]['field']
            val = job.get(dbkey, None)
            if val is not None:
                formatted = datafield(dbkey, val, PG_JOB_FIELDS[f]['format'])
                record |= { dbkey: formatted.htmlshort, f'_{dbkey}': formatted.value }
        result.append(record)
        
    columns = []
    for f in PG_JOB_FIELDS:
        if PG_JOB_FIELDS[f].get('filtercontrol') == 'select':
            f1 = {}
            for v in result:
                key = v.get(f'_{PG_JOB_FIELDS[f]["field"]}')
                if key:
                    f1[key] = key
            filterdata = json.dumps(f1)
            PG_JOB_FIELDS[f]['filterdata'] = f"json:{filterdata}"
        columns.append(PG_JOB_FIELDS[f])
        
    return { 'columns': columns, 'rows': result }
    

@bp.route('/pg')
def show_pg():
    processgroupguid = request.args.get('processgroupguid', None, type=str)
    default_project = current_user.settings.get('default_project', '')
    visible_columns = current_user.settings.get('processgroups::columns', [v["field"] for v in PG_FIELDS.values()])
    current_user.settings['jobs::view'] = 'processgroups'
    return render_template('pglist.html', default_project=default_project
                            , processgroupguid=processgroupguid, columns=PG_FIELDS, visible_columns=visible_columns)


@bp.route('/')
def show_jobs():
    default_project = current_user.settings.get('default_project', '')
    visible_columns = current_user.settings.get('jobs::columns', [v["field"] for v in JOB_FIELDS.values()])
    current_user.settings['jobs::view'] = 'jobs'
    return render_template('jobs.html', default_project=default_project, columns=JOB_FIELDS, visible_columns=visible_columns)
    
NAME_LENGTH = 15

def shortname(name,l):
    s = name
    if len(name)>l:
        s = '...' + name[-l+4:]
    return s

def coll_shape(coll_type):
    layout = constants.LAYOUT.get(coll_type, constants.DEFAULT_SHAPE)
    return layout[constants.SHAPE2], layout[constants.COLOR1]    

@bp.route('/processgraph')
def processgraph():
    runsheet_coll = request.args.get('runsheet', '/', type=str)
    graph = Digraph('datagraph')

    # We need the processgroupID
    processgroupid = iqry.qcollmetavalstatic(runsheet_coll, 'sys::runsheet::processgroupid')
    q = iqry.qcollbymeta('sys::runsheet::processgroupid', processgroupid)
    colls = [ r[Collection.name] for r in q ]
    for coll in colls:
        state = iqry.qcollmetaval(coll, 'sys::runsheet::state', default='unknown')
        if state == 'done':
            state = iqry.qcollmetaval(coll, 'sys::run::result')
        shape, shape_color = coll_shape(state)
        penwidth = '3' if runsheet_coll == coll else '1'
        graph.node(coll, label=iqry.qcollmetavalstatic(coll, 'sys::runsheet::description'), style='filled', penwidth=penwidth, 
            shape=shape, fillcolor=shape_color, URL=url_for('jobs.jobdetails', name=iqry.qcollmetaval(coll, ATTR_RUNSHEET_ID)))
    for coll in colls:
        ir = iqry.qcollmetaval(coll, 'sys::pipeline::input_collection_id')
        input_colls = [ c for c in colls if iqry.qcollmetavalstatic(c, 'sys::dataset_id') == ir ]
        if input_colls: 
            for input_coll in input_colls:
                graph.edge(input_coll, coll)
        else:
            q = iqry.qcollbystaticmeta('sys::dataset_id', ir)
            src = None
            for r in q:
                src = r[Collection.name]
            if src:
                shape, shape_color = coll_shape('source')
                graph.node(src, shortname(src, NAME_LENGTH), shape=shape, fillcolor=shape_color, style='filled',
                    URL=url_for('collbrowser.collbrowser', path=src))
                graph.edge(src, coll)

    graph.graph_attr['rankdir'] = 'LR'
    graph.graph_attr['fontsize'] = '15'

    return graph.pipe(format='svg').decode('utf-8')

@bp.route('/jobdetails')
def jobdetails():
    #this could be either the object-name of the yaml file or meta information attached to the collection
    jobnaam = request.args.get('name', '', type=str)
    processgroupguid = request.args.get('processgroupguid', '', type=str)
    
    details = {}
    metadata = {}

    # the jobnaam is refering to metainfo on a collection
    q = []
    if jobnaam:
        q = iqry.qcollbystaticmeta(ATTR_RUNSHEET_ID, jobnaam)
    elif processgroupguid:
        q = iqry.qcollbystaticmeta(ATTR_RUNSHEET_PROCESSGROUPGUID, processgroupguid)
    if len(q) < 1:
        flash(f'Cannot find unique job collection for {jobnaam}', 'error')
        return redirect(url_for('jobs.show_jobs'))
    runsheet = q[0][Collection.name]
    if not jobnaam:
        jobnaam = iqry.qcollmetaval(runsheet, ATTR_RUNSHEET_ID)
    metadata = iqry.qcollmetadict(runsheet)
    details['Runsheet collection'] = datafield('runsheet',  runsheet, 'irods_collection')
    details['Create time'] = datafield('create_time', float(metadata[ATTR_RUNSHEET_CREATETIME]), 'timestamp')

    FIELDS = {
        'sys::run::start_time': ('Start time', 'timestamp'),
        'sys::run::finish_time': ('End time', 'timestamp'),
        'sys::runsheet::projectID': ('Project ID', 'projectid'),
        'sys::runsheet::processID': ('Process ID', 'process'),
        'sys::runsheet::description': ('Description', 'text'),
        'sys::runsheet::processgroupid': ('Processgroup Instance', 'processgroupguid'),
        'sys::run::exit_code': ('Result', 'int'),
#        'sys::runsheet::input_collection': ('Input Collection', 'irods_collection'),
        'sys::run::output_collection': ('Output Collection', 'irods_collection'),
        'sys::run::account': ('Run Account', 'irods_user'),
        'sys::run::input_dir': ('Input directory', 'directory'),
        'sys::run::output_dir': ('Output directory', 'directory'),
        'sys::run::owner': ('Job owner', 'irods_user'),
        'sys::run::service_account': ('Sevice account', 'irods_user'),
        'sys::run::requestinguser': ('Requesting user', 'irods_user'),
        'sys::run::pipeline_dir': ('Pipeline run directory', 'directory'),
        'sys::run::run_dir': ('Pipeline run directory', 'directory'),
        'sys::run::useprojectaccount': ('Use project service account', 'boolean'),
        'sys::runsheet::repo': ('Git repository', 'url'),
        'sys::runsheet::tag': ('Git tag', 'tag'),
        'sys::runsheet::distribution': ('Distribution pipeline', 'boolean'),
        'sys::runsheet::omit_staging': ('Omit staging', 'boolean'),
        'sys::runsheet::omit_bringonline': ('Omit bring input data online', 'boolean'),
        'sys::runsheet::lsf_queue': ('LSF Queue', 'lsf_queue'),
        'sys::run::lsf_jobid': ('LSF Job ID', 'text'),
        'sys::run::pid': ('Process PID', 'text'),
    }
    MULTI_FIELDS = {
        'sys::runsheet::input_collection': ('Input Collection', 'irods_collection'),
        'sys::runsheet::dataobject': ('Dataobject', 'irods_object')
    }
    for field in FIELDS:
        if field in metadata:
            details[FIELDS[field][0]] = datafield(field, metadata[field], FIELDS[field][1])
    multi = {}
    for field, attrs in MULTI_FIELDS.items():
        values = iqry.qcollmetavals(runsheet, field)
        datavalues = [ datafield(field, value[CollectionMeta.value], attrs[1]).htmlstring for value in values ]
        multi[attrs[0]] = datavalues
    processgroupid = metadata.get('sys::runsheet::processgroupid', '')
    return render_template('jobdetails.html', details=details, multi=multi, runsheet=runsheet, processgroupid=processgroupid, jobnaam=datafield('jobnaam', jobnaam, 'runsheet'))


@bp.route('joblogs')
def job_logs():
    jobnaam = request.args.get('name', '', type=str)
    session = irods_manager.session()

    # the jobnaam is refering to metainfo on a collection
    query = session.query(Collection.name, CollectionMeta).filter( 
            Criterion('=', CollectionMeta.name, ATTR_RUNSHEET_ID )).filter(
            Criterion('=', CollectionMeta.value, f'{jobnaam}'))
    # Find the job log file
    results = query.get_results()
    job = next(results)
    runsheet = job[Collection.name] 
    q2 = session.query(CollectionMeta.name, CollectionMeta.value).filter( \
            Criterion('=', Collection.name, runsheet ))
    metadata = {meta[CollectionMeta.name] : meta[CollectionMeta.value] for meta in q2}
    ifs = current_user.ifs

    # Find output logs
    logfiles = {}
    try:
        log_location = '{}/log'.format(metadata['sys::run::output_collection'])
        if current_user.ifs.folderexists(log_location):
            logfiles = _get_logfiles(log_location)
    except KeyError:
        # output collection not set as metadata. Ignore.
        pass    
    return render_template('joblogs.html', jobnaam = datafield('jobnaam', jobnaam, 'runsheet'), logs = logfiles)


def _get_logfiles(location, subdir=''):
    logs = {}
    currentdir = os.path.join(location, subdir)
    for subdir2 in current_user.ifs.lsdirnames(currentdir):
        logs.update(_get_logfiles(location, subdir=os.path.join(subdir, subdir2)))
    logs.update({ os.path.join(subdir, filename): os.path.join(currentdir, filename) for filename in current_user.ifs.lsfilenames(currentdir) }) 
    return(logs)

@bp.route('/_joblog')
@cache.cached(timeout=120, key_prefix=key_userzone)
def show_logfile():
    # result object
    result = { 
        "error": False, 
        "data": None, 
        "msg": None
    }


    path = request.args.get('path', '', type=str)
    filename = path.split("/")[-1]

    try:
        obj = current_user.ifs.getfile(path)
    except DataObjectDoesNotExist:
        result["msg"] = f"The {path} does not exist"
        result["error"] = True
        return result

    try:
        with obj.open('r') as f:
            data = f.read(MAX_READ_LOG_BYTES)
    except CAT_NO_ACCESS_PERMISSION: # if encountered the error
        result["msg"] = f"You don't have permission to access {filename}"
        result["error"] = True
        return result # return the result, otherwise data is being read
    
    if sys.getsizeof(data) >= MAX_READ_LOG_BYTES:
        result["data"] = f"{data.decode('utf-8')}\n!!! log truncated to max {MAX_READ_LOG_BYTES} bytes !!!"
        return result

    # if everything went well
    result["data"] = data.decode('utf-8')
    
    return result

