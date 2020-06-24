#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jun  8 11:01:32 2020

@author: wierinve
"""

import math
import io
from flask import Blueprint, render_template, url_for, send_file
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, Resource
from irods.column import Criterion
from app.projects import get_projectlist
from app.datafield import datafield


bp = Blueprint('reports', __name__, url_prefix='/reports')

def format_diskspace(x):
    labels = ['B', 'kB', 'Mb', 'GB', 'TB', 'PB', 'EB']
    if x==0:
        return('0')
    g = math.log10(x)//3
    return '{0:.2f} {1}'.format(x/(1e3**g), labels[int(g)])

@login_required
def collection_size(coll, resource, timeout=86400):
    irods_session = current_user.irods_session
    size_attr = 'sys::collection_size::{}'.format(resource)
    query = irods_session.query(CollectionMeta.value).filter(
        Criterion('=', Collection.name, coll)).filter(
            Criterion('=', CollectionMeta.name, size_attr))
    size = 0
    for q in query:
        size += int(round(float((q[CollectionMeta.value]))))
    return size

@login_required
def projectdata_in_resource(project, resource):
    # Find all collections with a specific projectid
    irods_session = current_user.irods_session
    query = irods_session.query(Collection.name).filter(
            Criterion('=', CollectionMeta.name, 'projectID')).filter(
            Criterion('=', CollectionMeta.value, project))
    usage = 0
    for coll in query:
        usage += collection_size(coll[Collection.name], resource)
        
    return usage

@bp.route('/_download')
def download_report():
    projectlist, resources = get_space_usage()
    output = io.StringIO()
    output.write('"id","name"')
    for r in resources:
        output.write(',"{}"'.format(r))
    output.write(',"total"\n')
    for project in projectlist:
        output.write('{id},{name}'.format(**project))
        for r in resources:
            output.write(',{}'.format(int(project[r])))
        output.write(',{}\n'.format(int(project['total'])))
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    # seeking was necessary. Python 3.5.2, Flask 0.12.2
    mem.seek(0)
    output.close()
    return send_file(mem, attachment_filename='diskspace_report.csv',
                     as_attachment=True)
        
    

@login_required
def get_space_usage():

    #load projects
    projectinfo = get_projectlist()
          
    #query resources
    irods_session = current_user.irods_session
    query = irods_session.query(Resource.name)
    resources = [ r[Resource.name] for r in query ]
    resources = [ 'computeResc', 'storageResc' ]
    # query projects
    query =  irods_session.query(CollectionMeta.value).filter(
        Criterion('=', CollectionMeta.name, 'projectID'))
    projects=[ r[CollectionMeta.value] for r in query]
    projects.sort()
    # create projectlist
    projectlist = []
    for p in projects:
        projectdata = {'id': p}
        projectdata['name'] = projectinfo.get(p, {'name': p, 'description': ''})['description']      
        total = 0
        for r in resources:
            projectdata[r] = datafield('usage', projectdata_in_resource(p, r), 'bytes')
            total += int(projectdata[r])
        projectdata['total'] = datafield('total', total, 'bytes')
        projectlist.append(projectdata)
    return projectlist, resources


@bp.route('/space')
@login_required
def space_report():
    if not current_user.is_admin:
        return('<TR><TD COLSPAN=3>Access denied</TD></TR>')
    projectlist, resources = get_space_usage()
    return render_template('report_space.html', projectlist=projectlist, 
                           resources=resources)
