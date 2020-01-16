#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 10 15:22:06 2020

@author: wierinve
"""

import re
from flask import url_for
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta
from irods.column import Criterion
from datetime import datetime

KNOWN_ATTRIBUTES = {
        'Date'                                  : 'date',
        'import_timestamp'                      : 'timestamp',
        'stage_time'                            : 'timestamp',
        'sys::pipeline::input_collection_id'    : 'collection_id',
        'sys::pipeline::used_by'                : 'runsheet'
}

def format_exit_code(value):
    if value == "0":
        return "OK"
    else:
        return "FAILED"

def format_date(value):
    return '{}-{}-20{}'.format(value[4:6], value[2:4], value[0:2])

def format_timestamp(value):
    return '{}'.format(datetime.fromtimestamp(float(value)).strftime("%d-%m-%Y %H:%M:%S"))

def format_runsheet(value):
    runsheet_id = re.sub('-runsheet.yaml','', value)
    print(runsheet_id)
    return '<a href={0}?name={1}>{2}</a>'.format(url_for('jobs.show_jobdetails'), value, runsheet_id)    

def format_irods_collection(value):
    return '<a href={0}?path={1}>{1}</a>'.format(url_for('collbrowser.collbrowser'), value)

@login_required
def format_collection_id(value):
    display_value = value
    irods_session = current_user.irods_session
    query = irods_session.query(Collection.name).filter( \
                               Criterion('=', CollectionMeta.name, 'sys::dataset_id')).filter( \
                               Criterion('=', CollectionMeta.value, value))
    for coll in query:
        display_value = format_irods_collection(coll[Collection.name])        
    return display_value

def format_value(attr, value, units):
    formatted_value = value
    data_unit = ''
    if units:
        data_unit = units
    elif attr in KNOWN_ATTRIBUTES:
        data_unit = KNOWN_ATTRIBUTES[attr]
    if data_unit:
        format_function_name = 'format_' + data_unit
        if format_function_name in globals():
            formatted_value = globals()[format_function_name](value)
    return formatted_value
