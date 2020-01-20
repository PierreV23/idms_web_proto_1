#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 13:49:12 2019

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user, current_user, login_required
from irods.models import Collection, DataObject, DataObjectMeta
from irods.column import Criterion
from datetime import datetime
from app.formatting import AVU, INFINITE_DATE
import yaml
import time
import re

bp = Blueprint('jobs', __name__, url_prefix='/jobs')

@login_required
def jobdetails(jobfileObject):
    with jobfileObject.open('r') as f:
        txt = f.read();
        yy = yaml.load(txt)
    md = jobfileObject.metadata
    try: 
        ec = md.get_one('sys::run::exit_code').value
    except KeyError:
        ec = -1
    try:
        st = int(md.get_one('sys::run::start_time').value)
        strSt = datetime.utcfromtimestamp(st).strftime('%Y-%m-%d %H:%M:%S')
    except KeyError:
        strSt = "-"
        st = 0
    try:
        et = int(md.get_one('sys::run::finish_time').value)
        strEt = datetime.utcfromtimestamp(et).strftime('%Y-%m-%d %H:%M:%S')
    except KeyError:
        strEt = "-"
        et = 0
    try:
        ic = md.get_one('sys::runsheet::input_collection').value
    except KeyError:
        ic = ''
    try:
        oc = md.get_one('sys::run::output_collection').value
    except KeyError:
        oc = ''
    try:
        nextproj = yy['next_projectID']
    except:
        nextproj = ''
    try:
        description = yy['description']
    except:
        description = ''
    try:
        repo = yy['repo']
    except:
        repo = ''
    try:
        tag = yy['tag']
    except:
        tag = ''    
    details = {'name':jobfileObject.name, 'description': description, 'repo' : repo, 'tag': tag,
            'exit_code': ec, 'startTime': strSt, 'endTime': strEt, 'input_coll': ic, 'output_coll': oc, 'startTimestamp': st, 'next_projectID': nextproj}
    return details


@login_required
def joblist(state):
    FIELDS = {
            'sys::runsheet::description': ('Description', 'text'),
            'sys::run::start_time': ('Start time', 'timestamp'),
            'sys::run::finish_time': ('End time', 'timestamp'),
            'sys::runsheet::projectID': ('projectID', 'projectid'),
            'sys::run::exit_code': ('Result', 'int'),
            'sys::runsheet::input_collection': ('Input Collection', 'irods_collection'),
            'sys::run::output_collection': ('Output Collection', 'irods_collection')
    }
    b = []
    q1 = current_user.irods_session.query(DataObject.name, DataObject.id).filter ( \
        Criterion('like', Collection.name, '/rivmZone/system/runsheet/' + state +  '%'))

    for job in q1:
        jd2 = {'Name': AVU('runsheet', job[DataObject.name], 'runsheet')}
        jd2['State'] = state
        q2 = current_user.irods_session.query(DataObjectMeta.name, DataObjectMeta.value).filter( \
            Criterion('=', DataObject.id, job[DataObject.id] ))
        metadata = { meta[DataObjectMeta.name] : meta[DataObjectMeta.value] for meta in q2 }
        for field in FIELDS:
            if field in metadata:
#                jd2[FIELDS[field][0]] = format_value(field, metadata[field], FIELDS[field][1])
                jd2[FIELDS[field][0]] = AVU(field, metadata[field], FIELDS[field][1])
        if 'sys::run::finish_time' in metadata:
            if time.time() - int(metadata['sys::run::finish_time']) <2000000:
                b.append(jd2)
        else:
                b.append(jd2)
    return b

@bp.route('/')
@login_required
def show_jobs():
    x = request.args.get('items', 'all', type=str)
    l = []
    for a in [ 'waiting', 'incoming', 'queued', 'active', 'done' ]:
        if x in [ 'all', a]:
            l = l + joblist(a)
    l2 = sorted(l, key = lambda x: x['Start time'] if 'Start time' in x else INFINITE_DATE , reverse = True)
    columns = []
    for a in l2:
        for b in a:
            if b not in columns:
                columns.append(b)
    return render_template('jobs2.html', joblist=l2, items=x, columns=columns)

@bp.route('/jobdetails')
@login_required
def show_jobdetails():
    jobnaam = request.args.get('name', '', type=str)
    # We want the full path to the job runsheet object
    query = current_user.irods_session.query(DataObject.id, Collection.name).filter(Criterion('=', DataObject.name, jobnaam))
    jobpath = [ coll[Collection.name] for coll in query]
    runsheet = jobpath[0] + '/' + jobnaam
    jobid = [ coll[DataObject.id] for coll in query][0]
    jobObj = current_user.irods_session.data_objects.get(runsheet)
    jd = jobdetails(jobObj)
    q2 = current_user.irods_session.query(DataObjectMeta.name, DataObjectMeta.value).filter( \
            Criterion('=', DataObject.id, jobid ))
    metadata = { meta[DataObjectMeta.name] : meta[DataObjectMeta.value] for meta in q2 }
    # Find the job log file
    joblog = '/rivmZone/system/runsheet/log/' + jobnaam + '.log'
    ifs = current_user.ifs
    try:
        obj = ifs.getfile(joblog)
        with obj.open('r') as f:
            a = f.read( 500000 )
            log = a.decode('utf-8')
    except:
        log = ''
    # Find the collection log
    L = {}
    if 'sys::run::output_collection' in metadata:
        collOutlog = metadata['sys::run::output_collection'] + '/log'
        if ifs.folderexists(collOutlog):
            logfiles = ifs.ls(collOutlog)
            for logfile in logfiles:
                try:
                    obj = ifs.getfile(logfile.path)
                    with obj.open('r') as f:
                        a = f.read(500000)
                        L[logfile.shortname()] = a.decode('utf-8')
                except:
                    pass
    FIELDS = {
            'sys::runsheet::description': ('Description', 'text'),
            'sys::run::start_time': ('Start time', 'timestamp'),
            'sys::run::finish_time': ('End time', 'timestamp'),
            'sys::runsheet::projectID': ('Project ID', 'projectid'),
            'sys::runsheet::processID': ('Proces ID', 'processid'),
            'sys::run::exit_code': ('Result', 'int'),
            'sys::runsheet::input_collection': ('Input Collection', 'irods_collection'),
            'sys::run::output_collection': ('Output Collection', 'irods_collection'),
            'sys::run::input_dir': ('Input directory', 'directory'),
            'sys::run::output_dir': ('Output directory', 'directory'),
            'sys::run::owner': ('Job owner', 'irods_user'),
            'sys::run::pipeline_dir': ('Pipeline run directory', 'directory'),
            'sys::runsheet::repo': ('Git repository', 'git_repo'),
            'sys::runsheet::tag': ('Git tag', 'git_tag'),
            
    }            
    D = {}
    D['Runsheet file'] = AVU('runsheet',  runsheet, 'irods_object')
    for field in FIELDS:
        if field in metadata:
            D[FIELDS[field][0]] = AVU(field, metadata[field], FIELDS[field][1])
    D['Git repository'] = "<a href='{0}'>{0} TAG {1}</a>".format(jd['repo'].replace('.git',''), jd['tag'])
    D['Next projectID'] = "<a href='/projectdetails?name={0}'>{0}</a>".format(jd['next_projectID'])
    return render_template('jobdetails.html', details=D, jobnaam = jobnaam, runlog = log, logs = L)
