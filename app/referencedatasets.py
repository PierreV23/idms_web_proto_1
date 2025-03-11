#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 19 09:05:26 2019

@author: wierinve
"""

import json
from flask import abort, flash, Blueprint, render_template, redirect, request, url_for
from flask_login import current_user, login_required
from flask import jsonify
from irods.models import Collection, CollectionMeta, User, UserMeta
from irods.column import Criterion
from app.datafield import datafield
from graphviz import Digraph
from . import iqry
from app.constants import COLL_KEY_MAP
from app.irodssessions import irods_manager
from .projectdb_api import EPOCH, iso2dt, search, rest_call, add_checkbox
from datetime import datetime
from os import path

BP = Blueprint('reference', __name__, url_prefix='/reference')

reference_change_allowed = [ 'synchronize_command', 'synchronization_frequency', 'repository', 'tag', 'is_active']


def get_referencelist():
    referencelist_raw, status_code = rest_call('GET', 'reference')
    referencelist = {}
    if status_code == 200:
        referencelist = { reference['name']: reference for reference in referencelist_raw }
    return referencelist

@BP.route('/')
@login_required
def show_reference_datasets():
    """
    Return a web page with a list of all reference datasets

    url params:
        reference_dataset: switch to reference_datasets page and show <reference_dataset>
        process: swicth to processes page and show <processid> 
    """
    refdata_coll = current_user.refdata_coll 
    if not refdata_coll:
        flash('Reference data collection is not configured. Contact your administrator', 'error')
            
    reference_dataset = request.args.get('reference_dataset', '')
    reference_dataset_list = get_referencelist()
    return render_template('referencedatasets.html', referencedatasets=reference_dataset_list, reference_dataset=reference_dataset)

@BP.route('/details')
@login_required
def show_reference_details():
    """
    Shows page with reference dataset settings
    """
    reference_id = request.args.get('name', '', type=str)

    all_references_raw, result = rest_call('GET', 'references')
    all_references = [ reference['name'] for reference in all_references_raw]

    reference_details_raw, result = rest_call('GET', 'reference/{}'.format(reference_id))
    reference_details = {}
    for attr in ['id', 'name', 'creation_date',  'owner',  'synchronize_command', 'repository', 'tag', 'is_active']:
        val = reference_details_raw.get(attr, '')
        if val == None:
            val = ''
        reference_details[attr] = val
    for attr in ['synchronization_frequency']:
        val = reference_details_raw.get(attr, 0)
        if val == None:
            val = 0
        reference_details[attr] = val

    reference_versions = [] 

    import_state_raw, result = rest_call('GET', 'reference/{}/importer_state'.format(reference_id))
    import_state = {}
    for attr in [  "current_version",  "id",  "last_task_pid",    "referenceid"]:
        import_state[attr] = import_state_raw.get(attr, '')
    for attr in [  "last_synchronize",  "last_update" ]:
        import_state[attr] = import_state_raw.get(attr, 0)

    if import_state[ 'last_update' ] != 0:
        import_state[ 'last_update_iso' ] = datetime.fromtimestamp(import_state['last_update']).strftime("%d-%m-%Y %H:%M:%S")
    else:
        import_state[ 'last_update_iso' ] = "---"

    if import_state['last_synchronize'] != 0:
       import_state[ 'last_synchronize_iso' ] =  datetime.fromtimestamp(import_state['last_synchronize']).strftime("%d-%m-%Y %H:%M:%S")
    else:
        import_state[ 'last_synchronize_iso' ] = "---"

    return render_template('reference_details.html', 
                           RD=reference_details, 
                           all_references=all_references, 
                           reference_versions=reference_versions, 
                           import_state=import_state)


@BP.route('/activate_reference', methods=['GET', 'POST'])
@login_required
def activate_reference():
    requestdata = request.args.to_dict()
    reference = requestdata.get('reference')
    data = { 'is_active': 1 }
    response, result = rest_call('PUT', 'reference/{}'.format(reference), data=data)
    if result != 200:
        flash(response.get('message', f'Error: {result}'), 'error')
        location=f'reference_dataset={reference}'
    else:
        location = f'reference_dataset={reference}'

    return redirect(f'{url_for("reference.show_reference_datasets")}?{location}')

@BP.route('/deactivate_reference', methods=['GET', 'POST'])
@login_required
def deactivate_reference():
    requestdata = request.args.to_dict()
    reference = requestdata.get('reference')
    data = { 'is_active': 0 }
    response, result = rest_call('PUT', 'reference/{}'.format(reference), data=data)
    if result != 200:
        flash(response.get('message', f'Error: {result}'), 'error')
        location=f'reference_dataset={reference}'
    else:
        location = f'reference_dataset={reference}'

    return redirect(f'{url_for("reference.show_reference_datasets")}?{location}')


@BP.route('/update_reference', methods=['GET', 'POST'])
@login_required
def update_reference_settings():
    """
    Called when changing reference dataset settings from the web interface
    The request contains an <action> variable that specifiec the kind of update
    that is requested
    """

    requestdata = request.form.to_dict()
    location = ''
    reference = requestdata.get('reference')
    action = requestdata.get('action')

    if action == 'update_reference':
        data = {}
        for attr in reference_change_allowed:
            if attr in requestdata:
                data[attr] = requestdata[attr]
        response, result = rest_call('PUT', 'reference/{}'.format(reference), data=data)
        if result != 200:
            flash(response.get('message', f'Unknown error: {result}'), 'error')
        else:
            flash( 'update successful', 'info')
        location=f'reference_dataset={reference}'
    elif action == 'add_reference':
        response, result = rest_call('POST', 'reference', data={'name': reference})
        if result == 201:
            flash( 'creation successful', 'info')
            location = f'reference_dataset={reference}'
        else:            
            flash(response.get('message', 'Unknown error'), 'error')
            location='page=reference'
    elif action == 'remove_reference':
        response, result = rest_call('DELETE', 'reference/{}'.format(reference))
        location='page=reference'

    return redirect(f'{url_for("reference.show_reference_datasets")}?{location}')


@BP.route('/changeVersionName', methods=['GET', 'POST'])
@login_required
def change_version_name():
    requestdata = request.values.to_dict()
    reference_id = requestdata.get( 'reference_id')
    version_id = requestdata.get( 'version_id' )
    new_name = requestdata.get( 'new_name')
    response, result = rest_call('PUT', f'reference/{reference_id}/versions/{version_id}', data={'version_name': new_name})
    return (response, result)


@BP.route('/versions')
@login_required
def versions_table():
    reference_id = request.args.get('id', '', type=str)
    refdb_name = request.args.get('project', '', type=str)
    #in bio_rest we need to fix the api from reference_id to reference.id! 
    response, result = rest_call('GET', f'reference/{reference_id}/versions' )

    if result != 200:         
        flash(response.get('message', 'Unknown error'), 'error')
        location='page=reference'

    #format more nicely
    db_versions = [
                 {
                    'reference_id': reference_id,
                    'version_id': v['id'],
                    'is_valid': v['is_valid'],
                    'version': v['version'],
                    'creation_date': v['creation_date'],   
                    'dataset_id': v['dataset_id'],
                    'version_name': v['version_name']
                 }
                 for v in response ]

    #additionally get the collections
    refdata_coll = current_user.refdata_coll 

    q1 = iqry.qcollchildren( f"/{current_user.irods_zone}/{refdata_coll}/{refdb_name}")
    version_colls = { path.basename(c[Collection.name]): 
                        {
                            "irods_path": c[Collection.name],
                            "irods_display_path": f"<span class='path-change' data-path='{c[Collection.name]}'>{path.basename(c[Collection.name])}</span>" ,
                            'irods_create_time': datafield('create_time', c[Collection.create_time], 'timestamp').htmlstring,
                            'irods_owner_name': c[Collection.owner_name]
                        } 
                    for c in q1 }
    
    #and their metadata
    for key, items in version_colls.items():
        q2 = iqry.qcollmeta(items["irods_path"])
        meta_of_c = { m[CollectionMeta.name]: m[CollectionMeta.value] for m in q2 }
        version_colls[key]["irods_metadata"] = meta_of_c


    def add_irods_data(db_version):
        key = str(db_version["version"]) #this is the basename of the irods collection
        if key in version_colls:
           return db_version | version_colls[key]
        return db_version

    data_ext = list(map( add_irods_data, db_versions))

    options = {
        'download_btn': False,
        'view_btn': False,
        'delete_btn': False
    }
    return render_template('versions_table.html', data=json.dumps(data_ext), display_field=None, options=options)



@BP.route('/import_state')
@login_required
def import_state():
    reference_id = request.args.get('name', '', type=str)

    path=f"/{current_user.irods_zone}/projects/refdata/{reference_id}"
    return render_template('colltable.html', path=path, display_field=None)
