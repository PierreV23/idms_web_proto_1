#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 13:49:12 2019

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user, current_user, login_required
from irods.models import Collection, DataObject
from irods.column import Criterion
from datetime import datetime
import yaml

bp = Blueprint('jobs', __name__, url_prefix='/jobs')

@login_required
def jobdetails(jobfileObject):
    with jobfileObject.open('r') as f:
        txt = f.read();
        yy = yaml.load(txt)
    md = jobfileObject.metadata
    try: 
        ec = md.get_one('sys::runsheet::exit_code').value
    except KeyError:
        ec = -1
    try:
        st = int(md.get_one('sys::runsheet::start_time').value)
        strSt = datetime.utcfromtimestamp(st).strftime('%Y-%m-%d %H:%M:%S')
    except KeyError:
        strSt = "-"
        st = 0
    try:
        et = int(md.get_one('sys::runsheet::finish_time').value)
        strEt = datetime.utcfromtimestamp(et).strftime('%Y-%m-%d %H:%M:%S')
    except KeyError:
        strEt = "-"
        et = 0
    try:
        ic = md.get_one('sys::runsheet::input_collection').value
    except KeyError:
        ic = ''
    try:
        oc = md.get_one('sys::runsheet::output_collection').value
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
    a = []
    b = []
    
    coll = current_user.irods_session.collections.get('/rivmZone/system/runsheet/' + state)
    for job in coll.data_objects:
        jd = jobdetails(job)
        jd['state'] = state
        a.append({'start':jd['startTimestamp'], 'details':jd})
    for job  in sorted(a, key = lambda x: x['start'], reverse = True):    
        b.append(job['details'])
    return b

@bp.route('/')
@login_required
def show_jobs():
    x = request.args.get('items', 'all', type=str)
    l = []
    for a in [ 'waiting', 'incoming', 'queued', 'active', 'done' ]:
        if x in [ 'all', a]:
            l = l + joblist(a)
    return render_template('jobs2.html', joblist=l, items=x)

@bp.route('/jobdetails')
@login_required
def show_jobdetails():
    jobnaam = request.args.get('name', '', type=str)
    # We want the full path to the job runsheet object
    query = current_user.irods_session.query(Collection.name).filter(Criterion('=', DataObject.name, jobnaam))
    jobpath = [ coll[Collection.name] for coll in query]
    runsheet = jobpath[0] + '/' + jobnaam
    jobObj = current_user.irods_session.data_objects.get(runsheet)
    jd = jobdetails(jobObj)
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
    collOutlog = jd['output_coll'] + '/log'
    L = {}
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
    D = {}
    D['Runsheet File'] = "<a href='/docviewer?path=" + runsheet + "'>" + jobnaam + "</a>"
    D['Job Start Time'] = jd['startTime']
    D['Job End   Time'] = jd['endTime']
    D['Input  collection'] = "<a href='/collbrowser?path={0}'>{0}</a>".format(jd['input_coll'])
    D['Output collection'] = "<a href='/collbrowser?path={0}'>{0}</a>".format(jd['output_coll'])
    D['Git repository'] = "<a href='{0}'>{0} TAG {1}</a>".format(jd['repo'].replace('.git',''), jd['tag'])
    D['Next projectID'] = "<a href='/projectdetails?name={0}'>{0}</a>".format(jd['next_projectID'])
    return render_template('jobdetails.html', details=D, jobnaam = jobnaam, runlog = log, logs = L)
