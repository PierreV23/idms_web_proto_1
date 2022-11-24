#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 13:49:12 2019

@author: wierinve
"""

from flask import Blueprint, render_template, request, url_for, jsonify, redirect, flash
from flask_login import current_user, login_required
from fs_irods import folder_irods
from irods.exception import DataObjectDoesNotExist
from irods.models import Collection, DataObject, DataObjectMeta, CollectionMeta
from irods.column import Criterion
from app.datafield import datafield, AVU2data, INFINITE_DATE
from app.settings import JOB_FIELDS, PG_FIELDS, PG_JOB_FIELDS
from graphviz import Digraph
import json
import os
import sys
import time
from datetime import datetime, timezone
from .flaskcache import cache, dep_zone, key_zone, key_userzone
from app.irodssessions import irods_manager
from . import iqry
from . import constants

from sqlalchemy import create_engine, Float, text
from sqlalchemy.orm import sessionmaker

bp = Blueprint('jobs', __name__, url_prefix='/jobs')

ATTR_RUNSHEET_PREFIX = 'sys::runsheet::'
ATTR_RUNSHEET_STATE = '{}state'.format(ATTR_RUNSHEET_PREFIX)
ATTR_RUNSHEET_ID = '{}id'.format(ATTR_RUNSHEET_PREFIX)
ATTR_RUNSHEET_CREATETIME = '{}create_time'.format(ATTR_RUNSHEET_PREFIX)

MAX_READ_LOG_BYTES = 10000000

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
@login_required
def processgroupprocs():
    PGFIELDS = {
        'sys::runsheet::id': ('runsheet', 'runsheet'),
        'sys::runsheet::description' : ('description', 'text'),
        'sys::runsheet::state': ('state', 'text'),
        'user::run::exit_code': ('result', 'text'),
        'sys::run::start_time': ('start', 'timestamp'),
        'sys::run::finish_time': ('end', 'timestamp'),
    }
    processgroupid = request.args.get('processgroupid')
    q = iqry.qcollbymeta('sys::runsheet::processgroupid', processgroupid)
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
    

def dbsession():
    from sqlalchemy.ext.automap import automap_base
    from sqlalchemy.orm import Session
    from sqlalchemy import create_engine
    from sqlalchemy import MetaData, Table

    engine = create_engine('postgresql://irods:testpassword@rivm-bioir-l01a.rivm.ssc-campus.nl/ICAT', echo=False)
    meta = MetaData()
    meta.reflect(bind=engine, views=True, only=['rivm_mat_jobtable', 'rivm_v_processgroups'])

    # retrieve tables
    Jobs = Table("rivm_mat_jobtable", meta, autoload_with=engine)
    Processgroups = Table("rivm_v_processgroups", meta, autoload_with=engine)

    session = Session(engine)
   
    return session, Jobs, Processgroups

@bp.route('_jobs')
@login_required
def jobs():
# populate jobtable
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 999, type=int)
    filters = json.loads(request.args.get('filter', '{}'))
    order = request.args.get('order', 'desc')
    orderby = request.args.get('sort', 'start_time')
            
    session, Jobs, Processgroups = dbsession()   

    count_jobs = session.query(Jobs).count()
    # default second order by start_time desc
    jbs = session.query(Jobs).order_by(text(f"{orderby} {order}, start_time desc"))
    
    # Apply filters ('select' and 'input')
    for key, value in filters.items():
        for f in JOB_FIELDS:
            if JOB_FIELDS[f]['field'] == key:
                if JOB_FIELDS[f].get('filtercontrol') == 'select':
                    jbs = jbs.filter(text(f"{key}='{value}'"))
                elif JOB_FIELDS[f].get('filtercontrol') == 'input':
                    jbs = jbs.filter(text(f"{key} like('%{value}%')"))

    # recount, offset, limit data
    count_jobs = jbs.count()
    jbs = jbs.offset(offset).limit(limit)

    # format data
    result = []
    for j in jbs:
        rec = {}
        for f in JOB_FIELDS:
            dbkey = JOB_FIELDS[f]['field']
            val = getattr(j, dbkey)
            if val:
                v = datafield(dbkey, val, JOB_FIELDS[f]['format'])
                rec |= { dbkey: v.htmlshort, f'_{dbkey}': v.value }
        result.append(rec)
    
    engine = None
    return { 'rows': result, 'filters': filters, 'total': count_jobs }


@bp.route('_filterdata')
@cache.cached(timeout=3600, key_prefix=key_zone)
def filterdata():
# Determine prepopulated filter values for 'select' filters
    field = request.args.get('field', type=str)
    table = request.args.get('table', type=str)
    session, Jobs, Processgroups = dbsession() 

    sql = f"SELECT DISTINCT {field} FROM {table} WHERE {field} IS NOT NULL"
    fd = {v[0]:v[0] for v in session.execute(sql)}
    return jsonify(fd)


@bp.route('_pglist')
@login_required
def pglist():
#POPULATE processgrouplist
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 999, type=int)
    filters = json.loads(request.args.get('filter', '{}'))
    order = request.args.get('order', 'desc')
    orderby = request.args.get('sort', 'start_time')
    processgroupid = request.args.get('processgroupid', None, type=str)
            
    session, Jobs, Processgroups = dbsession()   

    count_jobs = session.query(Processgroups).count()

    # order by; default second order by start_time desc
    pgs = session.query(Processgroups).order_by(text(f"{orderby} {order}, start_time desc"))

    # drilldown on processgroupid
    if processgroupid:
        pgs = pgs.filter(Processgroups.columns.processgroupid==processgroupid)

    for key, value in filters.items():
        for f in PG_FIELDS:
            if PG_FIELDS[f].get('filtercontrol') == 'select':
                pgs = pgs.filter(text(f"{key}='{value}'"))
            elif PG_FIELDS[f].get('filtercontrol') == 'input':
                pgs = pgs.filter(text(f"{key} like('%{value}%')"))

    # recount, offset, limit data
    count_jobs = pgs.count()
    pgs = pgs.offset(offset).limit(limit)

    # format displayed data
    result = []
    for j in pgs:
        rec = {}
        for f in PG_FIELDS:
            dbkey = PG_FIELDS[f]['field']
            val = getattr(j, dbkey)
            if val:
                v = datafield(dbkey, val, PG_FIELDS[f]['format'])
                rec |= { dbkey: v.htmlshort, f'_{dbkey}': v.value }
        result.append(rec)
    
    engine = None
    return { 'rows': result, 'filters': filters, 'total': count_jobs }

 
@bp.route('_pgjobs')
@login_required
def pgjobs():
# display jobs under a processgroupid
    processgroupid = request.args.get('processgroupid', None, type=str)
    session, Jobs, Processgroups = dbsession()
    result = []
    pgj = session.query(Jobs)
    pgj = pgj.filter(Jobs.columns.processgroupid==processgroupid)

    for j in pgj:
        rec = {}
        for f in PG_JOB_FIELDS:
            dbkey = PG_JOB_FIELDS[f]['field']
            val = getattr(j, dbkey)
            if val:
                v = datafield(dbkey, val, PG_JOB_FIELDS[f]['format'])
                rec |= { dbkey: v.htmlshort, f'_{dbkey}': v.value }
        result.append(rec)
        
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
@login_required
def show_pg():
    processgroupid = request.args.get('processgroupid', None, type=str)
    default_project = current_user.settings.get('default_project', '')
    return render_template('pglist.html', default_project=default_project
                            , processgroupid=processgroupid, columns = PG_FIELDS)


@bp.route('/')
@login_required
#@cache.cached(timeout=30, key_prefix=key_zone)
def show_jobs():
    default_project=current_user.settings.get('default_project', '')
    return render_template('jobs.html', default_project = default_project, columns = JOB_FIELDS)

    
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
@login_required
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
@login_required
def jobdetails():
    #this could be either the object-name of the yaml file or meta information attached to the collection
    jobnaam = request.args.get('name', '', type=str)
    
    details = {}
    metadata = {}
    joblog = ''

    # the jobnaam is refering to metainfo on a collection
    q = iqry.qcollbystaticmeta(ATTR_RUNSHEET_ID, jobnaam)
    if len(q) != 1:
        flash(f'Cannot find unique job collection for {jobnaam}', 'error')
        return redirect(url_for('jobs.show_jobs'))
    runsheet = q[0][Collection.name]
    metadata = iqry.qcollmetadict(runsheet)
    details['Runsheet collection'] = datafield('runsheet',  runsheet, 'irods_collection')
    details['Create time'] = datafield('create_time', float(metadata[ATTR_RUNSHEET_CREATETIME]), 'timestamp')

    FIELDS = {
        'sys::run::start_time': ('Start time', 'timestamp'),
        'sys::run::finish_time': ('End time', 'timestamp'),
        'sys::runsheet::projectID': ('Project ID', 'projectid'),
        'sys::runsheet::processID': ('Process ID', 'processid'),
        'sys::runsheet::description': ('Description', 'text'),
        'sys::runsheet::processgroupid': ('Processgroup Instance', 'processgroupid'),
        'sys::run::exit_code': ('Result', 'int'),
#        'sys::runsheet::input_collection': ('Input Collection', 'irods_collection'),
        'sys::run::output_collection': ('Output Collection', 'irods_collection'),
        'sys::run::account': ('Run Account', 'irods_user'),
        'sys::run::input_dir': ('Input directory', 'directory'),
        'sys::run::output_dir': ('Output directory', 'directory'),
        'sys::run::owner': ('Job owner', 'irods_user'),
        'sys::runsheet::service_account': ('Sevice account', 'irods_user'),
        'sys::runsheet::requesting_user': ('Requesting user', 'irods_user'),
        'sys::run::pipeline_dir': ('Pipeline run directory', 'directory'),
        'sys::run::run_dir': ('Pipeline run directory', 'directory'),
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
@login_required
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
    joblog = { f'Job log', f'{runsheet}/log/{jobnaam}.log' }
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
@login_required
@cache.cached(timeout=120, key_prefix=key_userzone)
def show_logfile():
    path = request.args.get('path', '', type=str)
    try:
        obj = current_user.ifs.getfile(path)
    except DataObjectDoesNotExist:
        return 'Could not read logfile at "{}"'.format(path)
        
    with obj.open('r') as f:
        data = f.read(MAX_READ_LOG_BYTES)

    if sys.getsizeof(data) >= MAX_READ_LOG_BYTES:
        return '{}\n!!! log truncated to max {} bytes !!!'.format(data.decode('utf-8'), MAX_READ_LOG_BYTES)
    return data.decode('utf-8')