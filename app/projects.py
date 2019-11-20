#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 09:05:26 2019

@author: wierinve
"""

from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user, current_user, login_required
from irods.models import Collection, CollectionMeta, User, UserMeta
from irods.column import Criterion
import fs_irods
import json

bp = Blueprint('projects', __name__, url_prefix='/projects')

@bp.route('/')
@login_required
def show_projects():
    P = {}
    irods_session = current_user.irods_session
    ifs = current_user.ifs
    obj = ifs.getfile('/rivmZone/system/files/pipelinesettings.json')
    with obj.open('r') as f:
        pl = json.load(f)
    for project in sorted(pl):
        P[project] = {'name': project, 'details': pl[project]}   
    return render_template('projects.html', projects=P)

@bp.route('/details')
@login_required
def show_projectdetails():
    PD = {}
    projectnaam = request.args.get('name', '', type=str)
    processnaam = request.args.get('process', '', type=str)
    irods_session = current_user.irods_session
    ifs = current_user.ifs
    obj = ifs.getfile('/rivmZone/system/files/pipelinesettings.json')
    with obj.open('r') as f:
        config = json.load(f)
    # Retrieve grousp associated with project
    query = irods_session.query(User.name).filter(
            Criterion('!=', User.type, "rodsuser")).filter(
                    Criterion('=', UserMeta.name, "projectID")).filter(
                            Criterion('=', UserMeta.value, projectnaam)).order_by(User.name)
    groups = [u[User.name] for u in query]    
    PD['name'] = projectnaam
    for attr in ['description', 'default_collection','service_account']:
        try:
            PD[attr] = config[projectnaam]['settings'][attr]
        except:
            PD[attr] = ''
    PD['groups'] = groups
    PD['conf'] = config[projectnaam]
    PD['processes'] = [proc for proc in sorted(config[projectnaam]['processes'])]

    # Retrieve collections associated with project
    query = irods_session.query(Collection.name).filter(
            Criterion('=',CollectionMeta.name, 'projectID')).filter(
                    Criterion('=',CollectionMeta.value, projectnaam))
    PD['colls'] = [q[Collection.name] for q in query]
    return render_template('projectdetails.html', PD = PD, conf = config, processnaam = processnaam)

@login_required
def write_jsonfile(filepath, jsondict):
    ifs = current_user.ifs
    jsonstr = json.dumps(jsondict, sort_keys = True, indent = 4)
    obj = ifs.getfile(filepath)
    with obj.open('w') as f:
            f.write(jsonstr.encode())

@login_required
def read_jsonfile(filepath):
    ifs = current_user.ifs
    obj = ifs.getfile(filepath)
    with obj.open('r') as f:
            pl = json.load(f)
    return pl

@bp.route('/update_project', methods=['GET','POST'])
@login_required
def update_projectsettings():
    
    def add_checkbox(data, attr, name):
        if name in attr:
            data[name] = 'true'
        else:
            data[name] = 'false'
        return data
    
    requestdata = request.form.to_dict()
    viewProcess=''
    project = requestdata['project']
    try:
        process = requestdata['process']
    except:
        process = 'none'

    print(requestdata)
    config = read_jsonfile('/rivmZone/system/files/pipelinesettings.json')
    if requestdata['action'] == 'update_process':
        processConfig = config[project]['processes'][process]
        for attr in ['description', 'repo', 'tag', 'output_prefix', 'next_projectID', 'next_processID' ]:
            processConfig[attr] = requestdata[attr]
        add_checkbox(processConfig, requestdata, 'modify_in_place')
        add_checkbox(processConfig, requestdata, 'restartable')
        add_checkbox(processConfig, requestdata, 'distribution')
        viewProcess = process
    elif requestdata['action'] == 'add_process':
        if requestdata['process']:
            newProcess = requestdata['process']
            config[project]['processes'][newProcess] = {'next_projectID': 'none', 'next_processID': 'none'}
            viewProcess = newProcess
    elif requestdata['action'] == 'delete_process':
        del config['project']['processes'][process]
        viewProcess = 'none'
    elif requestdata['action'] == 'update_project':
        if not 'settings' in config[project]:
            config[project]['settings'] = {}
        projectSettings = config[project]['settings']
        for attr in ['description', 'default_collection','service_account']:
            projectSettings[attr] = requestdata[attr]
    write_jsonfile('/rivmZone/system/files/pipelinesettings.json', config)
    return("<script> window.location.href ='" + url_for('projects.show_projectdetails') + "?name={0}&process={1}'; </script>".format(requestdata['project'], viewProcess))
