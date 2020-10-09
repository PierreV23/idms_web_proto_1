#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 13:49:12 2019

@author: wierinve
"""

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from fs_irods import folder_irods
from irods.exception import DataObjectDoesNotExist
from irods.models import Collection, DataObject, DataObjectMeta
from irods.column import Criterion
from app.datafield import datafield, AVU2data, INFINITE_DATE
import os
import sys
import time
from datetime import datetime, timezone

bp = Blueprint('jobs', __name__, url_prefix='/jobs')

JOB_FIELDS = {
    'sys::runsheet::description': ('Description', 'text'),
    'sys::run::start_time': ('Start time', 'timestamp'),
    'sys::run::finish_time': ('End time', 'timestamp'),
    'sys::runsheet::projectID': ('projectID', 'projectid'),
    'sys::run::exit_code': ('Result', 'int'),
    'sys::runsheet::input_collection': ('Input Collection', 'irods_collection'),
    ##'sys::run::output_collection': ('Output Collection', 'irods_collection')
}

MAX_READ_LOG_BYTES = 100000

def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)

@login_required
def joblist(state):
    job_list = []
    q1 = current_user.irods_session.query(DataObject.name, DataObject.id, DataObject.create_time).filter( \
        Criterion('like', Collection.name, '/rivmZone/system/runsheet/' + state +  '%'))
    current_time = time.time()
    for job in q1:
        job_record = {'Name': datafield('runsheet', job[DataObject.name], 'runsheet')}
        job_record['State'] = datafield('state', state, 'job_state')
        job_record['Created'] = datafield('create_time', utc_to_local(job[DataObject.create_time]).timestamp(), 'timestamp')
        if int(current_time) - int(job_record['Created']) < 200000:
            q2 = current_user.irods_session.query(DataObjectMeta.name, DataObjectMeta.value).filter( \
                Criterion('=', DataObject.id, job[DataObject.id]))
            metadata = {meta[DataObjectMeta.name] : meta[DataObjectMeta.value] for meta in q2}
            for field in JOB_FIELDS:
                if field in metadata:
                    job_record[JOB_FIELDS[field][0]] = datafield(field, metadata[field], JOB_FIELDS[field][1])
            job_list.append(job_record)
    return job_list

@bp.route('/')
@login_required
def show_jobs():
    x = request.args.get('items', 'all', type=str)
    l = []
    for a in ['waiting', 'incoming', 'queued', 'active', 'postprocessing', 'done', 'stage', 'error']:
        if x in ['all', a]:
            l = l + joblist(a)
    l2 = sorted(l, key=lambda x: x['Start time'] if 'Start time' in x else x['Created'], reverse=True)
    columns = ['Name', 'State'] + [JOB_FIELDS[a][0] for a in JOB_FIELDS]
    return render_template('jobs2.html', joblist=l2, items=x, columns=columns)

@bp.route('/jobdetails')
@login_required
def show_jobdetails():
    jobnaam = request.args.get('name', '', type=str)
    # We want the full path to the job runsheet object
    query = current_user.irods_session.query(DataObject.id, DataObject.create_time, Collection.name).filter(Criterion('=', DataObject.name, jobnaam))
    job = next(query.get_results())
    runsheet = job[Collection.name] + '/' + jobnaam
    jobid = job[DataObject.id]
#    jobObj = current_user.irods_session.data_objects.get(runsheet)
    q2 = current_user.irods_session.query(DataObjectMeta.name, DataObjectMeta.value).filter( \
            Criterion('=', DataObject.id, jobid ))
    metadata = {meta[DataObjectMeta.name] : meta[DataObjectMeta.value] for meta in q2}
    # Find the job log file
    joblog = '/rivmZone/system/runsheet/log/' + jobnaam + '.log'
    ifs = current_user.ifs
    try:
        obj = ifs.getfile(joblog)
        with obj.open('r') as f:
            a = f.read(500000)
            log = a.decode('utf-8')
    except:
        log = ''

    # Find output logs
    logfiles = {}
    try:
        log_location = '{}/log'.format(metadata['sys::run::output_collection'])
        if current_user.ifs.folderexists(log_location):
            logfiles = _get_logfiles(log_location)
    except KeyError:
        # output collection not set as metadata. Ignore.
        pass

    FIELDS = {
        'sys::run::start_time': ('Start time', 'timestamp'),
        'sys::run::finish_time': ('End time', 'timestamp'),
        'sys::runsheet::description': ('Description', 'text'),
        'sys::runsheet::projectID': ('Project ID', 'projectid'),
        'sys::runsheet::processID': ('Process ID', 'processid'),
        'sys::runsheet::next_projectID': ('Next Project ID', 'projectid'),
        'sys::runsheet::next_processID': ('Next Process ID', 'processid'),
        'sys::run::exit_code': ('Result', 'int'),
        'sys::runsheet::input_collection': ('Input Collection', 'irods_collection'),
        'sys::run::output_collection': ('Output Collection', 'irods_collection'),
        'sys::run::input_dir': ('Input directory', 'directory'),
        'sys::run::output_dir': ('Output directory', 'directory'),
        'sys::run::owner': ('Job owner', 'irods_user'),
        'sys::run::pipeline_dir': ('Pipeline run directory', 'directory'),
        'sys::run::run_dir': ('Pipeline run directory', 'directory'),
        'sys::runsheet::repo': ('Git repository', 'git_repo'),
        'sys::runsheet::tag': ('Git tag', 'git_tag'),
        'sys::runsheet::distribution': ('Distribution pipeline', 'boolean'),
        'sys::runsheet::restartable': ('Restarts on error', 'boolean'),
        'sys::run::pid': ('Process PID', 'text')
    }
    D = {}
    D['Runsheet file'] = datafield('runsheet',  runsheet, 'irods_object')
    D['Create time'] = datafield('create_time', utc_to_local(job[DataObject.create_time]).timestamp(), 'timestamp')
    for field in FIELDS:
        if field in metadata:
            D[FIELDS[field][0]] = datafield(field, metadata[field], FIELDS[field][1])
#    D['Git repository'] = "<a href='{0}'>{0} TAG {1}</a>".format(jd['repo'].replace('.git',''), jd['tag'])
#    D['Next projectID'] = "<a href='/projectdetails?name={0}'>{0}</a>".format(jd['next_projectID'])
    return render_template('jobdetails.html', details=D, jobnaam = jobnaam, runlog = log, logs = logfiles)


def _get_logfiles(location, subdir=''):
    logs = {}
    currentdir = os.path.join(location, subdir)
    for subdir2 in current_user.ifs.lsdirnames(currentdir):
        logs.update(_get_logfiles(location, subdir=os.path.join(subdir, subdir2)))
    logs.update({ os.path.join(subdir, filename): os.path.join(currentdir, filename) for filename in current_user.ifs.lsfilenames(currentdir) }) 
    return(logs)

@bp.route('/_joblog')
@login_required
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
