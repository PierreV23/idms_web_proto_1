#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 09:05:26 2019

@author: wierinve
"""

import json
import requests
from requests.auth import HTTPBasicAuth
from flask import abort, Blueprint, render_template, redirect, request, url_for
from flask_login import current_user, login_required
from flask import jsonify
from irods.exception import CAT_NO_ACCESS_PERMISSION, OVERWRITE_WITHOUT_FORCE_FLAG
from irods.models import Collection, CollectionMeta, User, UserMeta
from irods.column import Criterion
from app.datafield import AVU2data, datafield
from app.models import deobfuscate


BP = Blueprint('projects', __name__, url_prefix='/projects')

REQUESTS_METHODS = {
    'GET':   requests.get,
    'PUT':   requests.put,
    'POST':  requests.post,
    'DELETE':requests.delete
}

@login_required
def rest_call(request_type, endpoint, data={}):    
    url = 'http://{}/api/1.0/{}'.format(current_user.irods_server, endpoint)
    print(url)
    auth = HTTPBasicAuth('alt\\{}'.format(current_user.username), current_user.ntlm_hash)
    return_data = {}
    if request_type in REQUESTS_METHODS:
        response = REQUESTS_METHODS[request_type](url, auth=auth, json=data)
    try:
        return_data = response.json()
    except:
        return_data = {}
    return return_data, response.status_code

@login_required
def get_projectlist():
    pl, result = rest_call('GET', 'projects')
    projectlist = { p['name']: p for p in pl }
    #projectlist = sorted(projectlist)
    return projectlist

@login_required
def get_processlist(project):
    pl, result = rest_call('GET', f'projects/{project}/processes')
    processes = []
    if result == 200:
        processes = [ p['name'] for p in pl ]
    return processes

@BP.route('/')
@login_required
def show_projects():
    """
    Return a web page with a list of all projects
    """
    projectlist = get_projectlist()
    return render_template('projects.html', projects=projectlist)


@BP.route('/details')
@login_required
def show_projectdetails():
    """
    Shows page with project settings and processes belonging to a project
    """
    projectnaam = request.args.get('name', '', type=str)
    processnaam = request.args.get('process', '', type=str)

    projectlist, result = rest_call('GET', 'projects')
    all_projects = [ project['name'] for project in projectlist]
    

    pl, result = rest_call('GET', 'projects/{}'.format(projectnaam))
    projectdetails = {}

    projectdetails['name'] = projectnaam
    # Retrieve groups associated with project
    irods_session = current_user.irods_session
    query = irods_session.query(User.name).filter(
        Criterion('!=', User.type, "rodsuser")).filter(
            Criterion('=', UserMeta.name, "projectID")).filter(
                Criterion('=', UserMeta.value, projectnaam)).order_by(User.name)
    groups = [u[User.name] for u in query]
    projectdetails['groups'] = groups
    # Retrieve general project settings
    for attr in ['description', 'default_collection', 'service_account', 'modify_in_place',
                 'distribution', 'restartable', 'omit_staging']:
        projectdetails[attr] = pl.get(attr, '')

#    projectdetails['conf'] = config[projectnaam]
#    projectdetails['processes'] = [proc for proc in sorted(config[projectnaam]['processes'])]
    processes, result = rest_call('GET', '/projects/{}/processes'.format(projectnaam))
    projectdetails['processes'] = {}
    for proces in processes:
        name = proces['name']
        projectdetails['processes'][name] = proces
        if 'next_projectid' in proces:
            next_project, result = rest_call('GET', '/projects/{}'.format(proces['next_projectid']))
            if result == 200:
                projectdetails['processes'][name]['next_projectID'] = next_project.get('name')
            processlist, result = rest_call('GET', '/projects/{}/processes'.format(next_project.get('name')))
            if result == 200:
                next_processes = { proces['id']: proces['name'] for proces in processlist }
                projectdetails['processes'][name]['next_processID'] = next_processes.get(proces['next_processid'], '')
                projectdetails['processes'][name]['next_processes'] = [ next_processes[x] for x in next_processes ]
        
    
        

    # Retrieve collections associated with project
    query = irods_session.query(Collection.name).filter(
        Criterion('=', CollectionMeta.name, 'projectID')).filter(
            Criterion('=', CollectionMeta.value, projectnaam))
    projectdetails['colls'] = [datafield('col', q[Collection.name], 'irods_collection') for q in query]
    # return render_template('projectdetails.html', PD=projectdetails,
    #                        conf=config, processnaam=processnaam)
    return render_template('projectdetails.html', PD=projectdetails, all_projects = all_projects,
                           processnaam=processnaam)


@login_required
# def write_jsonfile(filepath, jsondict):
#     """
#     Writes dict object <jsondict> to the json file in <filepath>
#     """
#     ifs = current_user.ifs
#     jsonstr = json.dumps(jsondict, sort_keys=True, indent=4)
#     obj = ifs.getfile(filepath)
#     with obj.open('w') as jsonfile:
#         jsonfile.write(jsonstr.encode())


# @login_required
# def read_jsonfile(filepath):
#     """
#     Returns a dictionary from json file <filepath>
#     """
#     ifs = current_user.ifs
#     obj = ifs.getfile(filepath)
#     with obj.open('r') as jsonfile:
#         jsondict = json.load(jsonfile)
#     return jsondict


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
            data[name] = 1
        else:
            data[name] = 0
        return data

    requestdata = request.form.to_dict()
    viewprocess = ''
    project = requestdata['project']
    try:
        process = requestdata['process']
    except:
        process = 'none'

    redirecturl = ''

    if requestdata['action'] == 'update_process':
        data = {}
        for attr in ['description', 'repo', 'tag', 'lsf_queue']:
            if attr in requestdata:
                data[attr] = requestdata[attr]
        add_checkbox(data, requestdata, 'omit_staging')
        add_checkbox(data, requestdata, 'modify_in_place')
        add_checkbox(data, requestdata, 'restartable')
        add_checkbox(data, requestdata, 'distribution')
        if requestdata.get('next_process') == 'true':
            for attr in ['next_projectID', 'next_processID']:
                if attr in requestdata:
                    data[attr] = requestdata[attr]
        else:
            data['next_projectid'] = 0
            data['next_processid'] = 0
        rest_call('PUT', 'projects/{}/processes/{}'.format(project, process), data=data)
        viewprocess = requestdata['process']
    elif requestdata['action'] == 'add_process':
        if requestdata['process']:
            data = {'name': requestdata['process']}
            response, result = rest_call('POST', 'projects/{}/processes'.format(project), data=data)
            viewprocess = requestdata['process']
    elif requestdata['action'] == 'delete_process':
        response, result = rest_call('DELETE', 'projects/{}/processes/{}'.format(project, process))
        viewprocess = 'none'
    elif requestdata['action'] == 'update_project':
        data = {}
        for attr in ['description', 'default_collection', 'service_account']:
            if attr in requestdata:
                data[attr] = requestdata[attr]
        rest_call('PUT', 'projects/{}'.format(project), data=data)
    elif requestdata['action'] == 'add_project':
        rest_call('POST', 'projects'.format(project), data={'name': project})
        redirecturl = url_for('projects.show_projects')
    elif requestdata['action'] == 'remove_project':
        response, result = rest_call('DELETE', 'projects/{}'.format(project))
        redirecturl = url_for('projects.show_projects')
    if redirecturl:
        return redirect(redirecturl)

    return redirect(url_for('projects.show_projectdetails') + "?name={0}&process={1}".format(project, viewprocess))


@BP.route('/get_process', methods=['GET','POST'])
def get_process():
    data = request.form.to_dict()
    if not 'project' in data:
        abort(400)
    processlist = get_processlist(data['project'])
    return jsonify(processlist)

