#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 09:05:26 2019

@author: wierinve
"""

import base64
import json
import requests
from requests.auth import HTTPBasicAuth
from flask import abort, flash, Blueprint, render_template, redirect, request, url_for, current_app
from flask_login import current_user, login_required
from flask import jsonify
from irods.exception import CAT_NO_ACCESS_PERMISSION
from irods.models import Collection, CollectionMeta, User, UserMeta, UserGroup
from irods.column import Criterion
from app.datafield import AVU2data, datafield
from app.models import deobfuscate
from graphviz import Digraph
from . import iqry
from .flaskcache import cache, dep_zone, dep_userzone, key_zone
from dateutil import parser as dateparser
from app.constants import COLL_KEY_MAP
from app.irodssessions import irods_manager


BP = Blueprint('projects', __name__, url_prefix='/projects')

REQUESTS_METHODS = {
    'GET':   requests.get,
    'PUT':   requests.put,
    'POST':  requests.post,
    'DELETE':requests.delete
}

EPOCH = '1970-01-01T01:00:00'

def iso2dt(timestr):
    """Convert ISO8601 datetime string to datetime

    Args:
        timestr (str): ISO8601 datetime string
    """
    if timestr is None:
        timestr = EPOCH
    return dateparser.parse(timestr)

def search(l, f, v):
    """Find an item x in a list l of objects
    where f(x) = v
    """
    matches = [ x for x in l if f(x) == v ]
    if not matches:
        matches = None
    return matches

@login_required
@cache.memoize(timeout=30, make_name=dep_userzone)
def rest_call(request_type, endpoint, data={}):
    if (hostname := current_app.config.get('API_HOST')) is None:
        hostname = current_user.irods_server
    url = 'http://{}/api/1.0/{}'.format(hostname, endpoint)
    auth = HTTPBasicAuth('alt\\{}'.format(current_user.username), current_user.ntlm_hash)
    return_data = {}
    if request_type in REQUESTS_METHODS:
        response = REQUESTS_METHODS[request_type](url, auth=auth, json=data)
    try:
        return_data = response.json()
    except:
        return_data = {}
    if request_type != 'GET':
        cache.delete_memoized(rest_call)
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

@login_required
def get_processgrouplist(project):
    pl, result = rest_call('GET', f'projects/{project}/processgroups')
    processgroups = []
    if result == 200:
        processgroups = [ p['name'] for p in pl ]
    return processgroups

@login_required
def get_process2list():
    pl, result = rest_call('GET', 'processes')
    processes = []
    if result == 200:
        processes = [ p['name'] for p in pl ]
    return processes


def get_contactlist(project):
    cl, result = rest_call('GET', f'projects/{project}/contacts')
    contacts = []
    if result == 200:
        contacts = cl
    return contacts


@BP.route('/projects/delete_contact', methods=['POST'])
@login_required
def delete_contact():
    json = request.get_json(force=True)
    project_id = json['project_id']
    contact_id = json['contact_id']
    result, status = rest_call('DELETE', f"projects/{project_id}/contacts/{contact_id}")
    ret = {}
    if status == 200:
        ret = { "success": True }
    else:
        ret = { "msg": f"Error: {result['msg']}"}
    return ret


@BP.route('/projects/update_contact', methods=['POST'])
@login_required
def update_contact():
    json = request.get_json(force=True)
    project_id = json['project_id']
    contact_id = json['contact_id']
    contact = json['contact']
    result, status = rest_call('PUT', f"projects/{project_id}/contacts/{contact_id}", contact)
    ret = {}
    if status == 200:
        ret = { "success": True }
    else:
        ret = { "msg": f"Error: {result['msg']}", "contact": result['contact'] }
    return ret


@BP.route('/projects/create_contact', methods=['POST'])
@login_required
def create_contact():
    json = request.get_json(force=True)
    project_id = json['project_id']
    contact = json['contact']
    result, status = rest_call('POST', f"projects/{project_id}/contacts", contact)
    ret = {}
    if status == 201:
        ret = { "success": True , "contact": result }
    else:
        ret = { "msg": f"Error: {result['msg']}"}
    return ret


@BP.route('/')
@login_required
def show_projects():
    """
    Return a web page with a list of all projects

    url params:
        project: switch to projects page and show <project>
        process: swicth to processes  page and show <processid> 
    """
    # TODO: refactor passing of arguments
    page = request.args.get('page', 'projects')

    project = request.args.get('project', '')
    process = request.args.get('process', '')
    pp = request.args.get('pp', '')
    processgroup = request.args.get('processgroup', '')
    processlist = get_process2list()
    if page == 'processes':
        return render_template('processes2.html', processes=processlist, process=process)
    else:
        projectlist = get_projectlist()
        return render_template('projects3.html', projects=projectlist, processes=processlist, 
            project=project, process=process, pp=pp, processgroup=processgroup)



@BP.route('/details')
@login_required
def show_projectdetails():
    """
    Shows page with project settings and processes belonging to a project
    """
    projectnaam = request.args.get('name', '', type=str)
    processnaam = request.args.get('process', '', type=str)
    processgroup = request.args.get('processgroup', 'default', type=str) 

    projectlist, result = rest_call('GET', 'projects')
    all_projects = [ project['name'] for project in projectlist]
    

    pl, result = rest_call('GET', 'projects/{}'.format(projectnaam))
    projectdetails = {}

    projectdetails['name'] = projectnaam
    # Retrieve groups associated with project
    with irods_manager.session() as session:
        query = session.query(User.name).filter(
            Criterion('!=', User.type, "rodsuser")).filter(
                Criterion('=', UserMeta.name, "projectID")).filter(
                    Criterion('=', UserMeta.value, projectnaam)).order_by(User.name)
        groups = [u[User.name] for u in query]
    projectdetails['groups'] = groups
    # Retrieve general project settings
    for attr in ['description', 'default_collection', 'service_account', 'modify_in_place',
                 'distribution', 'restartable', 'omit_staging', 'omit_bringonline']:
        projectdetails[attr] = pl.get(attr, '')

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
        
    #Contacts
    contacts, result = rest_call('GET', '/projects/{}/contacts'.format(projectnaam))
    projectdetails['contacts'] = contacts

    # Retrieve collections associated with project
    processing = iso2dt(pl.get('last_updated', EPOCH)) > iso2dt(pl.get('last_verified', EPOCH))
    return render_template('projectdetails.html', PD=projectdetails, all_projects = all_projects, processing=processing,
                           processnaam=processnaam, processgroup=processgroup)

@BP.route('_projectcolls')
def projectcolls():
    projectnaam = request.args.get('project', '', type=str)
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 999, type=int)
    filterstr = request.args.get('filter', '{}')

    irods_session = current_user.irods_session

    sortkey = request.args.get('sort', 'name')
    sort_order = request.args.get('order', 'asc')

    c_sortkey = COLL_KEY_MAP.get(sortkey, 'coll_name')

# Create collection and data filters
    filters = json.loads(filterstr)
    qc_filters = [Criterion('=', CollectionMeta.name, 'projectID'), Criterion('=', CollectionMeta.value, projectnaam)]
    if 'displayname' in filters:
        qc_filters.append(Criterion('like', Collection.name, f'%{filters["displayname"]}%'))

# Get item counts 
    qc_count = irods_session.query(Collection.id)
    for qc_filter in qc_filters:
        qc_count = qc_count.filter(qc_filter)
    coll_count = next(qc_count.count(Collection.id).get_results())[Collection.id]

    results = { 'total': coll_count , 'rows': []}
# Query for collection subcollections

    q1 = irods_session.query(Collection)
    for qc_filter in qc_filters:
        q1 = q1.filter(qc_filter)
    q1 = q1.order_by(c_sortkey, order=sort_order).offset(offset).limit(limit)
    try:
        colls = q1.execute()
        for coll in colls:
            objdict = { 
                'displayname': datafield('irods_collection', coll[Collection.name], 'irods_collection').collentry,
                'path': coll[Collection.name],
                'object': 'collection',
                'size': 'DIR',
                'create_time': datafield('create_time', coll[Collection.create_time], 'timestamp').htmlstring,
                'owner_name': coll[Collection.owner_name]
            }
            objdict['type'] = iqry.qcollmetaval(coll[Collection.name], 'sys::data::type', default='')
            results['rows'].append(objdict)
    except CAT_NO_ROWS_FOUND:
        pass
    return jsonify(results)


@BP.route('_projectcolltable')
def projectcolltable():
    projectnaam = request.args.get('project', '', type=str)
    options = {
        'download_btn': False,
        'view_btn': False,
        'delete_btn': False
    }
    path=f"/{current_user.irods_zone}/projects/{projectnaam}"
    return render_template('colltable.html', path=path, display_field=None, options=options)


@BP.route('/processdetails')
@login_required
def show_processdetails():
    """
    Shows page with process settings
    """
    processnaam = request.args.get('name', '', type=str)

    pl, result = rest_call('GET', f'processes/{processnaam}')

    return render_template('processdetails.html', details=pl)


def add_checkbox(data, attr, name, negate=False, key=None):
    set_value = 0 if negate else 1
    datakey = key if key else name
    if name in attr:
        data[datakey] = set_value
    else:
        data[datakey] = 1 - set_value
    return data

@BP.route('/update_project', methods=['GET', 'POST'])
@login_required
def update_projectsettings():
    """
    Called when changing project settings from the web interface
    The request contains an <action> variable that specifiec the kind of update
    that is requested
    """

    requestdata = request.form.to_dict()
    location = ''
    project = requestdata.get('project')
    process = requestdata.get('process')
    action = requestdata.get('action')

    if action == 'add_process2':
        if process:
            data = {'name': process}
            response, result = rest_call('POST', 'processes', data=data)
        location=f'page=processes&process={process}'
    elif action == 'add_processgroup':
        name = requestdata.get('name')
        if project and name:
            data = {'name' : name }
            response, result = rest_call('POST', f'projects/{project}/processgroups', data=data)
        location=f'project={project}&pp=processgroups&processgroup={name}'
    elif action == 'update_project':
        data = {}
        for attr in ['description', 'default_collection', 'service_account']:
            if attr in requestdata:
                data[attr] = requestdata[attr]
        rest_call('PUT', 'projects/{}'.format(project), data=data)
        location=f'project={project}'
    elif action == 'add_project':
        response, result = rest_call('POST', 'projects'.format(project), data={'name': project})
        if result == 202:
            location=f'project={project}'
        else:            
            flash(response.get('message', 'Unknown error'), 'error')
            location='page=projects'
    elif action == 'remove_project':
        response, result = rest_call('DELETE', 'projects/{}'.format(project))
        location='page=projects'

    return redirect(f'{url_for("projects.show_projects")}?{location}')

@BP.route('/_updateproc', methods=['POST'])
@login_required
def update_process():
    requestdata = request.form.to_dict()
    data = {}
    procid = requestdata.get('procid')
    process = requestdata.get('process')
    for attr in ['description', 'repo', 'tag']:
        if attr in requestdata:
            data[attr] = requestdata[attr]
    add_checkbox(data, requestdata, 'do_staging', negate=True, key='omit_staging')
    add_checkbox(data, requestdata, 'do_bringonline', negate=True, key='omit_bringonline')
    add_checkbox(data, requestdata, 'modify_in_place')
    add_checkbox(data, requestdata, 'restartable')
    add_checkbox(data, requestdata, 'distribution')
    rest_call('PUT', f'processes/{procid}', data=data)
    return redirect(f'{ url_for("projects.show_projects") }?page=processes&process={process}')

@BP.route('/get_process', methods=['GET','POST'])
def get_process():
    data = request.form.to_dict()
    if not 'project' in data:
        abort(400)
    processlist = get_processlist(data['project'])
    return jsonify(processlist)

@BP.route('_myprojectview', methods=['GET'])
@login_required
def my_projectview():

    projectlist = current_user.projects()

    projectdetails = {}

    pl, result = rest_call('GET', 'projects')

    if result == 200:
        projectdetails = { project['name'] : project['default_collection'] for project in pl if project['name'] in projectlist }

    columns = min(4, 1 + len(projectdetails) // 20)

    return render_template('_myprojects.html', projectdetails=projectdetails, columns=columns )


@BP.route('_pgaction', methods=['GET', 'POST'])
@login_required
def pgaction():
    project = request.args.get('project')
    group = request.args.get('group')
    action = request.args.get('action')
    if action == 'add_process':
        process = request.args.get('process')
        name = request.args.get('name')
        # Check if the process exists:
        pr, r2 = rest_call('GET', f'processes/{process}')
        if r2 != 200:
            # TODO: some error message???
            return 'FAILED'
        if name == "":
            # Auto-generate a name based on the process name
            all_pgprocs, r3 = rest_call('GET', f'projects/{project}/processgroups/{group}/processes')
            if r3 != 200:
                return 'FAILED'
            names = [ p.get('name') for p in all_pgprocs ]
            index = 1
            while True:
                name = f'{process}-{index}'
                if name not in names:
                    break
                index += 1

        new_process = {
            'name': name,
            'processid': pr.get('id')
        }
        pl, result = rest_call('POST', f'projects/{project}/processgroups/{group}/processes', new_process)
    elif action == 'update_process':
        process = request.args.get('process')
        data = {}
        for attr in ['lsf_queue', 'tag']:
            value = request.args.get(attr)
            if value:
                data[attr] = value
        pl, result = rest_call('PUT', f'projects/{project}/processgroups/{group}/processes/{process}', data = data)
    elif action == 'update_processes':
        lsf_queue = request.args.get('lsf_queue')
        pl, result = rest_call('GET', f'projects/{project}/processgroups/{group}/processes')
        if result == 200:
            for procref in pl:
                _, result = rest_call('PUT', f'projects/{project}/processgroups/{group}/processes/{procref.get("id")}', 
                    data = { 'lsf_queue': lsf_queue })
    elif action == 'delete_process':
        process = request.args.get('process')
        pl, result = rest_call('DELETE', f'projects/{project}/processgroups/{group}/processes/{process}')
    elif action == 'set_input':
        process = request.args.get('process')
        input = request.args.get('input')
        pl, result = rest_call('PUT', 
            f'projects/{project}/processgroups/{group}/processes/{process}',
            { 'input': input})
    elif action == 'add_dependency':
        process = request.args.get('process')
        depend = request.args.get('depend')
        pl, result = rest_call('POST',
            f'projects/{project}/processgroups/{group}/processes/{process}/dependencies',
            { 'depends_on': depend })
    elif action == 'delete_dependency':
        process = request.args.get('process')
        depend = request.args.get('depend')
        pl, result = rest_call('DELETE',
            f'projects/{project}/processgroups/{group}/processes/{process}/dependencies/{depend}')
    return "OK"

@BP.route('_pggraph', methods=['GET'])
@login_required
def pg_graph():
    """Generate a graph of process flow

        Node names:
            name: 'out,<id>', with id being the id from pgprocess
            label: 'out,name', with name being the name from pgprocess
                if id==0, label='DATA'
            id: 'out,id,name'

        Process names:
            name: 'proc,<id>', with id being the id from pgprocess
            label: '<name>', with name being the name from pgprocess
            id: 'proc,id,name'
    """
    def add_process(name, procid, selected):
        extra_settings = {}
        if selected:
            extra_settings = {
                'style': 'filled',
                'fillcolor': 'lightblue'
            }
        nodename = f'n,{procid}'
        nodeid = f'n,{procid},{name}'
        graph.node(nodename, label=name, shape='cds', id=nodeid, **extra_settings)

    project = request.args.get('project')
    group = request.args.get('group', 'default')
    selected_processref = request.args.get('selected_processref')
    pl, result = rest_call('GET', f'projects/{project}/processgroups/{group}/processes')
    if result != 200:
        return ""
    # Create the process group graph
    graph = Digraph('datagraph')
    graph.graph_attr['rankdir'] = 'LR'
    # There is always a node for NEW_DATA
    graph.node('d,0', label="NEW DATA", shape='box', id='d,0')
    for process in pl:
        pname = process.get('name')
        add_process(pname, process.get('id'), pname==selected_processref)
    # get the dependencies
    pd, r2 = rest_call('GET', f'projects/{project}/processgroups/{group}/dependencies')
    for process in pl:
        processname = f'n,{process.get("id")}'
        input = process.get("input")
        if input:
            precessor = f'n,{input}'
        else:
            precessor = f'd,0'
        graph.edge(precessor, processname, style='bold')
        for dep in [ p for p in pd if p.get('processrefid') == process.get('id') ]:
            depend_id = dep.get('depends_on')
            if depend_id is not None:
                depnode = f'n,{depend_id}'
                graph.edge(depnode, processname, style='dashed')

    graph_output = graph.pipe(format='svg').decode('utf-8')
    return graph_output

@BP.route('_pgdetails')
@login_required
def pg_details():

    project = request.args.get('project')
    group = request.args.get('group', 'default')
    selected_processref = request.args.get('selected_processref')
    mode = request.args.get('mode')
    pl, result = rest_call('GET', f'projects/{project}/processgroups/{group}/processes')
    all_processes, result = rest_call('GET', f'processes')
    dependency_names = []
    selected_details = None
    selected_tags = []
    selected_process = datafield('process', 'NOT FOUND', 'base')
    if selected_processref:
        sel_list = search(pl, lambda x: x.get('name'), selected_processref)
        selected_details  = sel_list[0] if sel_list else None
        dependencies, r2 = rest_call('GET', f'projects/{project}/processgroups/{group}/processes/{selected_processref}/dependencies')
        dependency_names = [ p['name'] for p in pl if p['id'] in [ d['depends_on'] for d in dependencies ]]
        selected_processlist = search(all_processes, lambda x: x.get('id'), selected_details.get('processid'))
        if selected_processlist:
            selected_process = datafield('process', selected_processlist[0].get('name'), 'process')
        selected_tags, r3 = rest_call('GET', f'processes/{selected_details.get("processid")}/tags')
    message = ''
    if mode == 'select_input':
        message = f'Please select input for process {selected_processref}'
    elif mode == 'add_dependency':
        message =f'Please select a required process for {selected_processref}'
    return render_template('pg_details.html', project=project, group=group, 
        all_processes=all_processes, pg_processes=pl, selected_details=selected_details,
        selected_tags = selected_tags, selected_process=selected_process,
        dependencies=dependency_names, message=message)

@BP.route('processgroups', methods=['GET'])
@login_required
def processgroups():
    # Retrieve the list of processes in a group
    project = request.args.get('project')
    processgroup = request.args.get('group', 'default')
    # find all groups
    pl, result = rest_call('GET', f'projects/{project}/processgroups')
    groups = [ g.get('name') for g in pl ]

    return render_template('processgroups.html', project=project, processgroup=processgroup, processgroups=groups)


@BP.route('usermanager', methods=['GET'])
@login_required
def usermanager():
    objectname = request.args.get('object')
    objecttype = request.args.get('objecttype')
    usertype = request.args.get('usertype')
    url = f'/{objecttype}/{objectname}/{usertype}'

    return render_template('usermanager.html', object=objectname, objecttype=objecttype, usertype=usertype)

@BP.route('processusage', methods=['GET'])
@login_required
def processusage():
    process = request.args.get('process')
    return render_template('processusage.html', process=process)