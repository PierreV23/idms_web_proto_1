#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 09:05:26 2019

@author: wierinve
"""

import json
from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import current_user, login_required
from flask import jsonify
from irods.models import Collection, CollectionMeta, User, UserMeta
from irods.column import Criterion
from app.datafield import AVU2data, datafield


BP = Blueprint('projects', __name__, url_prefix='/projects')


@BP.route('/')
@login_required
def show_projects():
    """
    Return a web page with a list of all projects defined in
    pipelinesettings.json
    """
    projectlist = {}
    ifs = current_user.ifs
    obj = ifs.getfile('/rivmZone/system/files/pipelinesettings.json')
    with obj.open('r') as settingsfile:
        settings = json.load(settingsfile)
    for project in sorted(settings):
        try:
            description = settings[project]['settings']['description']
        except KeyError:
            description = ''
        projectlist[project] = {'name': project, 'description': description}
    return render_template('projects.html', projects=projectlist)


@BP.route('/details')
@login_required
def show_projectdetails():
    """
    Shows page with project settings and processes belonging to a project
    """
    projectdetails = {}
    projectnaam = request.args.get('name', '', type=str)
    processnaam = request.args.get('process', '', type=str)
    irods_session = current_user.irods_session
    ifs = current_user.ifs
    obj = ifs.getfile('/rivmZone/system/files/pipelinesettings.json')
    with obj.open('r') as settingsfile:
        config = json.load(settingsfile)

    projectdetails['name'] = projectnaam
    # Retrieve grousp associated with project
    query = irods_session.query(User.name).filter(
        Criterion('!=', User.type, "rodsuser")).filter(
            Criterion('=', UserMeta.name, "projectID")).filter(
                Criterion('=', UserMeta.value, projectnaam)).order_by(User.name)
    groups = [u[User.name] for u in query]
    projectdetails['groups'] = groups
    # Retrieve general project settings
    for attr in ['description', 'default_collection', 'service_account']:
        try:
            projectdetails[attr] = config[projectnaam]['settings'][attr]
        except:
            projectdetails[attr] = ''

    projectdetails['conf'] = config[projectnaam]
    projectdetails['processes'] = [proc for proc in sorted(config[projectnaam]['processes'])]

    # Retrieve collections associated with project
    query = irods_session.query(Collection.name).filter(
        Criterion('=', CollectionMeta.name, 'projectID')).filter(
            Criterion('=', CollectionMeta.value, projectnaam))
    projectdetails['colls'] = [datafield('col', q[Collection.name], 'irods_collection') for q in query]
    return render_template('projectdetails.html', PD=projectdetails,
                           conf=config, processnaam=processnaam)


@login_required
def write_jsonfile(filepath, jsondict):
    """
    Writes dict object <jsondict> to the json file in <filepath>
    """
    ifs = current_user.ifs
    jsonstr = json.dumps(jsondict, sort_keys=True, indent=4)
    obj = ifs.getfile(filepath)
    with obj.open('w') as jsonfile:
        jsonfile.write(jsonstr.encode())


@login_required
def read_jsonfile(filepath):
    """
    Returns a dictionary from json file <filepath>
    """
    ifs = current_user.ifs
    obj = ifs.getfile(filepath)
    with obj.open('r') as jsonfile:
        jsondict = json.load(jsonfile)
    return jsondict


@BP.route('/update_project', methods=['GET', 'POST'])
@login_required
def update_projectsettings():
    """
    Called when changing project settings from the web interface
    The request contains an <action> variable that specifiec the kind of update
    that is requested
    """
    def add_checkbox(data, attr, name):
        if name in attr:
            data[name] = 'true'
        else:
            data[name] = 'false'
        return data

    requestdata = request.form.to_dict()
    viewprocess = ''
    project = requestdata['project']
    try:
        process = requestdata['process']
    except:
        process = 'none'

    print(requestdata)
    config = read_jsonfile('/rivmZone/system/files/pipelinesettings.json')
    redirecturl = ''

    if requestdata['action'] == 'update_process':
        processConfig = config[project]['processes'][process]
        for attr in ['description', 'repo', 'tag', 'next_projectID',
                     'next_processID']:
            processConfig[attr] = requestdata[attr]
        add_checkbox(processConfig, requestdata, 'modify_in_place')
        add_checkbox(processConfig, requestdata, 'restartable')
        add_checkbox(processConfig, requestdata, 'distribution')
        viewprocess = process
    elif requestdata['action'] == 'add_process':
        if requestdata['process']:
            newProcess = requestdata['process']
            config[project]['processes'][newProcess] = {'next_projectID': 'none', 'next_processID': 'none'}
            viewprocess = newProcess
    elif requestdata['action'] == 'delete_process':
        del config['project']['processes'][process]
        viewprocess = 'none'
    elif requestdata['action'] == 'update_project':
        if 'settings' not in config[project]:
            config[project]['settings'] = {}
        projectSettings = config[project]['settings']
        for attr in ['description', 'default_collection', 'service_account']:
            projectSettings[attr] = requestdata[attr]
    elif requestdata['action'] == 'add_project':
        config[project] = {'processes': {}, 'settings': {}}
    elif requestdata['action'] == 'remove_project':
        del config[project]
        redirecturl = url_for('projects.show_projects')

    write_jsonfile('/rivmZone/system/files/pipelinesettings.json', config)

    if redirecturl:
        return redirect(redirecturl)

    return redirect(url_for('projects.show_projectdetails') + "?name={0}&process={1}'; </script>".format(project, viewprocess))


@BP.route('/get_process', methods=['GET','POST'])
def get_process():
    data = request.form.to_dict()
    pl = read_jsonfile('/rivmZone/system/files/pipelinesettings.json')
    processes = [ p for p in pl.get(data['project'])['processes'] ]
    return(jsonify(processes))

