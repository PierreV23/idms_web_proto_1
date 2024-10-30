#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jun  8 11:01:32 2020

@author: wierinve
"""

import math
import io
import json
from flask import Blueprint, render_template, url_for, send_file, jsonify
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, Resource
from irods.column import Criterion
from app.projects import get_projectlist
from app.datafield import datafield
from app.irodssessions import irods_manager
from app import iqry, stats

RESOURCES_OMIT = ('demoResc', 'bundleResc')

bp = Blueprint('reports', __name__, url_prefix='/reports')

def collection_size(coll, resource, timeout=86400):
    irods_session = irods_manager.session()
    size_attr = 'sys::collection_size::{}'.format(resource)
    query = irods_session.query(CollectionMeta.value).filter(
        Criterion('=', Collection.name, coll)).filter(
            Criterion('=', CollectionMeta.name, size_attr))
    size = 0
    for q in query:
        size += int(round(float((q[CollectionMeta.value]))))
    return size

def projectdata_in_resource(project, resource):
    # Find all collections with a specific projectid
    irods_session = irods_manager.session()
    query = irods_session.query(Collection.name).filter(
            Criterion('=', CollectionMeta.name, 'projectID')).filter(
            Criterion('=', CollectionMeta.value, project))
    usage = 0
    for coll in query:
        usage += collection_size(coll[Collection.name], resource)
        
    return usage

@bp.route('_irods_sessionreport')
def irods_sessionreport():
    return jsonify(irods_manager.reportdata())

@bp.route('/irodssessions')
def irodssessions():
    """Create a report of active iRODS Sessions

    Returns:
        rendered template
    """    
    columns = [
        { "field": "Environment", "title": "Environment", "sortable": True },
        { "field": "User", "title": "User", "sortable": True },
        { "field": "State", "title": "State", "sortable": True },
        { "field": "Timestamp", "title": "Last use", "sortable": True },        
    ]
    return render_template('report_irodssessions.html', columns=columns)

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
    return send_file(mem, download_name='diskspace_report.csv',
                     as_attachment=True)
        
    

def get_space_usage():

    #load projects
    projectinfo = get_projectlist()
          
    #query resources
    irods_session = irods_manager.session()
    query = irods_session.query(Resource.name)
    resources = [ r[Resource.name] for r in query if not r[Resource.name] in RESOURCES_OMIT ]
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

def inter2(a, b):
    """Return intersection of two list of collection objects

    Args:
        a (list): List of Collection objects
        b (list): List of Collection objects

    Returns:
        list: List of Collection objects (a & b)
    """    
    aa = { x[Collection.id]: x for x in a }
    ai = set(aa)
    bi = { x[Collection.id] for x in b }
    ids = ai & bi
    return [ aa[i] for i in ids ]

@bp.route('/seqdata')
@login_required
def sequencer_data():
    if not current_user.is_admin:
        return('<TR><TD COLSPAN=3>Access denied</TD></TR>')
    with irods_manager.session() as session:
        # FIND SERIALS
        qry = session.query(CollectionMeta.value).filter(
            Criterion('=', CollectionMeta.name, 'sequencing::serial')
        )
        serials = { s[CollectionMeta.value] for s in qry }
        # Find last import
        imports = iqry.qcollbymetaattr('ID')
        sequencer_data = []
        for serial in serials:
            record = {
                'serial': serial
            }
            mycolls = iqry.qcollbymeta('sequencing::serial', serial)
            rootcolls = inter2(imports, mycolls)
            rootcolls = sorted(rootcolls, key = lambda x: x[Collection.create_time])
            if rootcolls:
                newest = rootcolls[-1]
                record['time'] = newest[Collection.create_time].strftime('%Y-%m-%d %H:%M:%S')
                for f in [ 'brand', 'host', 'platform' ]:
                    record[f] = iqry.qcollmetaval(newest[Collection.name], f'sequencing::{f}')
            record['runs'] = len(rootcolls)
            sequencer_data.append(record)
        columns = [
            { "field": "serial", "title": "Serial", "sortable": True },
            { "field": "time", "title": "Last data uploaded", "sortable": True },
            { "field": "brand", "title": "Sequencing brand",  "sortable": True },
            { "field": "platform", "title": "Sequencing platform",  "sortable": True },
            { "field": "host", "title": "Sequencing host",  "sortable": True },
            { "field": "runs", "title": "Runs", "sortable": True}
        ]
        data = {
            'id': 'sequencing_report',
            'columnsJSON': json.dumps(columns),
            'dataJSON': json.dumps(sequencer_data),
        }
    return render_template('bootstraptable.html', data=data)

@bp.route('/sequencers')
def sequence():
    return render_template('report_sequencers.html')