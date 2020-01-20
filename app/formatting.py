#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 10 15:22:06 2020

@author: wierinve
"""

import re
from flask import url_for
from datetime import datetime
from app.object_factory import ObjectFactory

KNOWN_ATTRIBUTES = {
        'Date'                                  : 'date',
        'import_timestamp'                      : 'timestamp',
        'stage_time'                            : 'timestamp',
        'sys::pipeline::input_collection_id'    : 'collection_id',
        'sys::pipeline::used_by'                : 'runsheet'
}

factory = ObjectFactory()

class AVUclass():
    def __init__(self, attr, value, unit = None):
        self.attr = attr
        self.value = value
        self.unit = unit
    
    @staticmethod
    def factory(**kwargs):
        return AVUclass(**kwargs)
    
    def __str__(self):
        return str(self.value)
    
    def __repr__(self):
        return f'{self.attr} = {self.value} {self.unit}'
    
factory.register_default_builder(AVUclass.factory)    

class timestamp_AVUclass(AVUclass):
    def __init__(self, attr, value, unit = None):
        super().__init__(attr = attr, value = int(value), unit = unit)
        
    def __str__(self):
        return '{}'.format(datetime.fromtimestamp(float(self.value)).strftime("%d-%m-%Y %H:%M:%S"))
    
    @staticmethod
    def factory(**kwargs):
        return timestamp_AVUclass(**kwargs)
    
    def __lt__(self, other):
#        print(self, other)
        return self.value < other.value
    
INFINITE_DATE = timestamp_AVUclass(attr='none', value=1E11)    

factory.register_builder('timestamp', timestamp_AVUclass.factory)

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
    return '<a href={0}?name={1}>{2}</a>'.format(url_for('jobs.show_jobdetails'), value, runsheet_id)    

def format_irods_collection(value):
    return '<a href={0}?path={1}>{1}</a>'.format(url_for('collbrowser.collbrowser'), value)

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
