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

MAXLEN = 45

factory = ObjectFactory()

def AVU(attr, value, unit):
    return factory.create(unit, attr=attr, value=value, unit=unit)

class AVU_base():
    def __init__(self, attr, value, unit = None):
        self.attr = attr
        self.value = value
        self.unit = unit
    
    @staticmethod
    def factory(**kwargs):
        return AVU_base(**kwargs)
    
    @property
    def htmlshort(self):
        return self.htmlstring

    @property
    def htmlstring(self):
        return str(self.value)
    
    def __str__(self):
        return str(self.value)
    
    def __repr__(self):
        return f'{self.attr} = {self.value} {self.unit}'
    
factory.register_default_builder(AVU_base.factory)    

class AVU_int(AVU_base):
    def __init__(self, attr, value, unit = None):
        super().__init__(attr = attr, value = int(value), unit = unit)
        
    def __str__(self):
        return str(self.value)
    
    @staticmethod
    def factory(**kwargs):
        return AVU_int(**kwargs)

    def __str__(self):
        return str(self.value)

    def __int__(self):
        return self.value
    
    def __lt__(self, other):
        return self.value < other.value
    
factory.register_builder('int', AVU_int.factory)

class AVU_boolean(AVU_base):
    def __init__(self, attr, value, unit = None):
        super().__init__(attr = attr, value = value, unit = unit)
        
    def __str__(self):
        return 'TRUE' if self.value else 'FALSE'

    @property
    def htmlstring(self):
        return str(self.value)
    
    @staticmethod
    def factory(**kwargs):
        return AVU_boolean(**kwargs)

    def __str__(self):
        return str(self.value)
    
    def __lt__(self, other):
        return self.value < other.value
    
factory.register_builder('boolean', AVU_boolean.factory)


class AVU_timestamp(AVU_base):
    def __init__(self, attr, value, unit = None):
        super().__init__(attr = attr, value = int(value), unit = unit)
        
    def __str__(self):
        return '{}'.format(datetime.fromtimestamp(float(self.value)).strftime("%d-%m-%Y %H:%M:%S"))
    
    @property 
    def htmlstring(self):
        return self.__str__()
    
    @staticmethod
    def factory(**kwargs):
        return AVU_timestamp(**kwargs)
    
    def __lt__(self, other):
        return self.value < other.value
    
INFINITE_DATE = AVU_timestamp(attr='none', value=1E11)    

factory.register_builder('timestamp', AVU_timestamp.factory)

class AVU_irods_collection(AVU_base):
    
    def displaystring(self, maxlen=999):
        nameparts = self.value.split('/')
        shortname =  nameparts[-1]
        prefix = '/{}'.format('/'.join(nameparts[1:-1]))
        if len(self.value) > maxlen:
            # LINE TOO LONG
            prefixlen = max(1, maxlen - len(shortname) - 2)
            prefix = '..' + prefix[-prefixlen:]
        return '{}/{}'.format(prefix, shortname)
    
    @property
    def htmlstring(self):
        displaystring = self.displaystring()
        return '<a href="{0}?path={1}">{2}</A>'.format(format(url_for('collbrowser.collbrowser')), self.value, displaystring)
    
    @property
    def htmlshort(self):
        displaystring = self.displaystring(maxlen=MAXLEN)
        return '<div class="container"><a href="{0}?path={1}" data-toggle="tooltip" title="{1}">{2}</A></div>'.format(format(url_for('collbrowser.collbrowser')), self.value, displaystring)
    
    @staticmethod
    def factory(**kwargs):
        return AVU_irods_collection(**kwargs)
    
    def __lt__(self, other):
        return self.value < other.value
    
INFINITE_DATE = AVU_timestamp(attr='none', value=1E11)    

factory.register_builder('irods_collection', AVU_irods_collection.factory)

class AVU_runsheet(AVU_base):
        
    @property
    def htmlstring(self):
        runsheet_id = re.sub('-runsheet.yaml','', self.value)
        return '<a href={0}?name={1} data-toggle="tooltip" title="{1}">{2}</a>'.format(url_for('jobs.show_jobdetails'), self.value, runsheet_id)    
    
    @staticmethod
    def factory(**kwargs):
        return AVU_runsheet(**kwargs)

    def __str__(self):
        return str(self.value)
   
    def __lt__(self, other):
        return self.value < other.value
    
factory.register_builder('runsheet', AVU_runsheet.factory)

class AVU_irods_object(AVU_base):
        
    @property
    def htmlstring(self):
        shortname = self.value.split('/')[-1]
        return '<a href="#" data-toggle="modal" data-target="#myOutput" onClick="fillModal(\'{0}\', \'{1}\')">{1}</a>'.format(self.value, shortname)
    
    @staticmethod
    def factory(**kwargs):
        return AVU_irods_object(**kwargs)
 
    def __lt__(self, other):
        return self.value < other.value
    
factory.register_builder('irods_object', AVU_irods_object.factory)


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
