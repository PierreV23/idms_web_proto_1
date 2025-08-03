#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 13:49:12 2019

@author: wierinve
"""

from flask import Blueprint, render_template, request, url_for, redirect, flash
from flask_login import current_user, login_required
from fs_irods import folder_irods
from irods.exception import DataObjectDoesNotExist
from irods.models import Collection, DataObject, DataObjectMeta, CollectionMeta
from irods.column import Criterion
from app.datafield import datafield
from graphviz import Digraph
import os
import sys
import time
from datetime import datetime, timezone
from .flaskcache import cache, dep_zone, key_zone, key_userzone
from app.irodssessions import irods_manager
from . import iqry
from . import constants

bp = Blueprint('oldjobs', __name__, url_prefix='/oldjobs')

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
def processgroupprocs():
    PGFIELDS = {
        'sys::runsheet::id': ('runsheet', 'runsheet'),
        'sys::runsheet::description' : ('description', 'text'),
        'sys::runsheet::state': ('state', 'text'),
        'sys::run::result': ('result', 'text'),
        'sys::run::start_time': ('start', 'timestamp'),
        'sys::run::finish_time': ('end', 'timestamp'),
    }
    pgid = request.args.get('pgid')
    q = iqry.qcollbymeta('sys::runsheet::processgroupid', pgid)
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
    

@cache.memoize(timeout=30, make_name=dep_zone)
def joblist(state='', page=1):
    """Create a list of jobs in state state
    
    Returns max JOB_PAGE_SIZE jobs
    args:
        state: state filter for job runsheets
        page: page number. each page has MAX_PAGE jobs
        
    returns:
        joblist, total_job_count
    """

    job_list = []
    session = irods_manager.session()
    if state == '':
        q1b = session.query(Collection).filter( 
                Criterion('=', CollectionMeta.name, ATTR_RUNSHEET_STATE))
    else:  
        q1b = session.query(Collection).filter(
                Criterion('=', CollectionMeta.name, ATTR_RUNSHEET_STATE)).filter(
                Criterion('=', CollectionMeta.value, f'{state}'))

    # Create a list of all collection and runsheet based jobs
    q1b = q1b.order_by(Collection.create_time, order='desc')
    result_list = []
    for j in q1b:
        result_list.append((j, j[Collection.create_time]))
        if len(result_list) > 5000:
            break
    #result_list = [ (j, j[Collection.create_time]) for j in q1b ]

    # Get the paged subset of the sorted job list
    result_list_s = sorted( result_list, key = lambda j : j[1], reverse = True)[constants.JOB_PAGE_SIZE*(page-1):constants.JOB_PAGE_SIZE*page]

    # Get the job details for both types of jobs
    for res in result_list_s:
            job_record = {}
            runsheet_collection = res[0][Collection.name] 
            #create runsheet object by reading collection meta-data
            metadata = iqry.qcollmetadict(runsheet_collection)
            state = metadata.get(ATTR_RUNSHEET_STATE, 'unknown')
            name = metadata.get(ATTR_RUNSHEET_ID, 'unknown')
    #        job_record['COLLECTION'] =  Collection.name
            job_record['Name'] = datafield('runsheet', name, 'runsheet')
            job_record['create_time'] = timestamp_to_local(metadata.get(ATTR_RUNSHEET_CREATETIME, 0)).timestamp()
            job_record['Created'] =datafield('create_time', job_record['create_time'], 'timestamp')
            job_record['State'] =datafield('state', state, 'job_state')
            for field in constants.JOB_FIELDS:
                if field in metadata:
                    job_record[constants.JOB_FIELDS[field][0]] = datafield(field, metadata[field], constants.JOB_FIELDS[field][1])
            job_list.append( job_record )      

    coll_jobs = len(result_list)

    return job_list, coll_jobs

@bp.route('/')
@login_required
@cache.cached(timeout=30, key_prefix=key_userzone)
def show_jobs():
    state = request.args.get('items', 'all', type=str)
    page = request.args.get('page', 1, type=int)
    if state == 'all':
        l, total = joblist(page=page)
    else:
        l, total = joblist(state, page=page)
    # for a in ['waiting', 'incoming', 'queued', 'active', 'postprocessing', 'done', 'stage', 'error']:
    #     if x in ['all', a]:
    #         l = l + joblist(a)
    columns = ['Name', 'State'] + [constants.JOB_FIELDS[a][0] for a in constants.JOB_FIELDS]
    buttons = pagebuttons(constants.JOB_PAGE_SIZE, total, page, 10, 'href={}?page={{}}&items={}'.format(url_for('oldjobs.show_jobs'), state))
    return render_template('oldjobs2.html', joblist=l, items=state, columns=columns, buttons=buttons, LAYOUT=constants.LAYOUT)

NAME_LENGTH = 15

def shortname(name,l):
    s = name
    if len(name)>l:
        s = '...' + name[-l+4:]
    return s

def coll_shape(coll_type):
    layout = constants.LAYOUT.get(coll_type, constants.DEFAULT_SHAPE)
    return layout[constants.SHAPE2], layout[constants.FILLCOLOR]    

@bp.route('/processgraph')
def processgraph():
    runsheet_coll = request.args.get('runsheet', '/', type=str)
    graph = Digraph('datagraph')

    # We need the processgroupID
    pgid = iqry.qcollmetavalstatic(runsheet_coll, 'sys::runsheet::processgroupid')
    q = iqry.qcollbymeta('sys::runsheet::processgroupid', pgid)
    colls = [ r[Collection.name] for r in q ]
    for coll in colls:
        state = iqry.qcollmetaval(coll, 'sys::runsheet::state', default='unknown')
        if state == 'done':
            state = iqry.qcollmetaval(coll, 'sys::run::result')
        shape, fillcolor = coll_shape(state)
        penwidth = '3' if runsheet_coll == coll else '1'
        graph.node(coll, label=iqry.qcollmetavalstatic(coll, 'sys::runsheet::description'), style='filled', penwidth=penwidth, 
            shape=shape, fillcolor=fillcolor, URL=url_for('oldjobs.jobdetails', name=iqry.qcollmetaval(coll, ATTR_RUNSHEET_ID)))
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
                shape, fillcolor = coll_shape('source')
                graph.node(src, shortname(src, NAME_LENGTH), shape=shape, fillcolor=fillcolor, style='filled',
                    URL=url_for('collbrowser.collbrowser', path=src))
                graph.edge(src, coll)

    graph.graph_attr['rankdir'] = 'LR'
    graph.graph_attr['fontsize'] = '15'

    return graph.pipe(format='svg').decode('utf-8')

@bp.route('/jobdetails')
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
        return redirect(url_for('oldjobs.show_jobs'))
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
    pgid = metadata.get('sys::runsheet::processgroupid', '')
    return render_template('jobdetails.html', details=details, multi=multi, runsheet=runsheet, pgid=pgid, jobnaam=datafield('jobnaam', jobnaam, 'runsheet'))

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
