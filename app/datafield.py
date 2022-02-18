#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 10 15:22:06 2020

@author: wierinve
"""

import math
import re
from datetime import datetime, timedelta
from flask import url_for
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta
from irods.column import Criterion
from app.object_factory import ObjectFactory
from . import iqry

KNOWN_ATTRIBUTES = {
    'Date': 'date',
    'import_timestamp': 'timestamp',
    'stage_time': 'timestamp',
    'sys::access_time': 'timestamp',
    'sys::archive::lastrun': 'timestamp',
    'sys::archive::lastcheck': 'timestamp',
    'sys::collection_size' : 'bytes',
    'sys::collection_size_time': 'timestamp',
    'sys::pipeline::gitrepo': 'url',
    'sys::pipeline::input_collection_id': 'collection_id',
    'sys::pipeline::last_use': 'timestamp',
    'sys::pipeline::stage_time': 'timestamp',
    'sys::pipeline::used_by': 'runsheet',
    'user::pipeline::input_collection_id': 'collection_id',
    'sys::run::last_move_time': 'timestamp',
    'sys::run::output_collection': 'irods_collection',
    'sys::runsheet::create_time': 'timestamp',
    'sys::runsheet::depends_on': 'collection_id',
    'sys::runsheet::id': 'runsheet',
    'sys::runsheet::input_collection': 'irods_collection',
    'sys::runsheet::projectID': 'projectid',
    'sys::runsheet::repo': 'url'
}

KNOWN_ATTRIBUTE_TEMPLATES = {
    'sys::collection_size_time::.*' : 'timestamp',
    'sys::collection_size::.*' : 'bytes',
    'sys::run::.*_time': 'timestamp',
    'sys::lock::time::.*::valid_till': 'timestamp',
    'sys::lock::time::.*::runtime': 'timedelta',
    'sys::lock::time::.*::timeout': 'timedelta'
}

MAXLEN = 45

factory = ObjectFactory()


def AVU2data(attr, value, unit):
    my_unit = KNOWN_ATTRIBUTES.get(attr) if unit is None else unit
    if my_unit is None:
        for pattern in KNOWN_ATTRIBUTE_TEMPLATES:
            if re.match(pattern, attr):
                my_unit = KNOWN_ATTRIBUTE_TEMPLATES[pattern]
                break
    return datafield(attr, value, my_unit)

def datafield(name, value, datatype):
    return factory.create(datatype, name=name, value=value, datatype=datatype)

class data_base():
    def __init__(self, name, value, datatype=None):
        self.name = name
        self.value = value
        self.datatype = datatype

    @staticmethod
    def factory(**kwargs):
        return data_base(**kwargs)

    @property
    def htmlshort(self):
        return self.htmlstring

    @property
    def htmlstring(self):
        return str(self.value)

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return f'{self.name} = {self.value} {self.datatype}'

factory.register_default_builder(data_base.factory)

class data_int(data_base):
    def __init__(self, name, value, datatype=None):
        super().__init__(name, int(value), datatype)

    def __str__(self):
        return str(self.value)

    @staticmethod
    def factory(**kwargs):
        return data_int(**kwargs)

    def __int__(self):
        return self.value

    def __lt__(self, other):
        return self.value < other.value

class data_bytes(data_int):
    def _formatted(self):
        labels = ['B', 'kB', 'Mb', 'GB', 'TB', 'PB', 'EB']
        bytes = int(self)
        if bytes == 0:
            return('0')
        g = math.log10(bytes)//3
        return '{0:.2f} {1}'.format(bytes/(1e3**g), labels[int(g)])

    @staticmethod
    def factory(**kwargs):
        return data_bytes(**kwargs)

    @property
    def htmlstring(self):
        return str(self)

    def __str__(self):
        return self._formatted()

class data_boolean(data_base):

    def __eq__(self, other):
        if type(other) == bool:
            return self.value == other
        return self == other

    def __str__(self):
        return 'TRUE' if self.value else 'FALSE'

    @property
    def htmlstring(self):
        return str(self.value)

    @staticmethod
    def factory(**kwargs):
        return data_boolean(**kwargs)

class data_timedelta(data_base):

    def __str__(self):
        if self.value.isnumeric():
            return str(timedelta(seconds=int(self.value)))
        else:
            return self.value

    @property
    def htmlstring(self):
        return str(self)

    @staticmethod
    def factory(**kwargs):
        return data_timedelta(**kwargs)

class data_timestamp(data_base):
    def __init__(self, name, value, datatype=None):
        try:
            myvalue = float(value)
            self._formatted_date = datetime.fromtimestamp(myvalue).strftime("%d-%m-%Y %H:%M:%S")
        except:
            myvalue = value
            self._formatted_date = value
        super().__init__(name, myvalue, datatype)

    def __str__(self):
        return self._formatted_date

    def __int__(self):
        return int(self.value)

    @property
    def htmlstring(self):
        return self.__str__()

    @staticmethod
    def factory(**kwargs):
        return data_timestamp(**kwargs)

    def __lt__(self, other):
        return self.value < other.value

    def __eq__(self, other):
        return self.value == other.value

INFINITE_DATE = data_timestamp(name='none', value=1E11)


class data_irods_collection(data_base):

    def displaystring(self, maxlen=999):
        nameparts = self.value.split('/')
        shortname = nameparts[-1]
        prefix = '/{}'.format('/'.join(nameparts[1:-1]))
        if len(self.value) > maxlen:
            # LINE TOO LONG
            prefixlen = max(1, maxlen - len(shortname) - 2)
            prefix = '..' + prefix[-prefixlen:]
        if prefix == '/':
            return '/{}'.format(shortname)
        else:
            return '{}/{}'.format(prefix, shortname)

    @property
    def htmlstring(self):
        displaystring = self.displaystring()
        return '<a href="{0}?path={1}">{2}</A>'.format(
            url_for('collbrowser.collbrowser'), self.value, displaystring)

    @property
    def htmlshort(self):
        displaystring = self.displaystring(maxlen=MAXLEN)
        return '<div class="container"><a href="{0}?path={1}" data-toggle="tooltip" title="{1}">{2}</A></div>'.format(format(url_for('collbrowser.collbrowser')), self.value, displaystring)

    @staticmethod
    def factory(**kwargs):
        return data_irods_collection(**kwargs)

    def __lt__(self, other):
        return self.value < other.value


class data_collection_id(data_base):
    def __init__(self, name, value, datatype=None):
        self._ref_col = None
        self._searched_for_ref_col = False
        super().__init__(name, value, datatype)

    @property
    @login_required
    def ref_col(self):
        if self._searched_for_ref_col:
            return self._ref_col
        query = iqry.qcollbystaticmeta('sys::dataset_id', self.value)
        for coll in query:
            self._ref_col = coll[Collection.name]
        self._searched_for_ref_col = True
        return self._ref_col

    @property
    def htmlstring(self):
        if self.ref_col is None:
            return self.value
        return '<a href="{0}?path={1}">{1}</A>'.format(
            url_for('collbrowser.collbrowser'), self.ref_col)

    @staticmethod
    def factory(**kwargs):
        return data_collection_id(**kwargs)


class data_runsheet(data_base):

    @property
    def htmlstring(self):
        runsheet_id = re.sub('-runsheet.yaml', '', self.value)
        return '<a href={0}?name={1} data-toggle="tooltip" title="{1}">{2}</a>'.format(url_for('jobs.jobdetails'), self.value, runsheet_id)

    @staticmethod
    def factory(**kwargs):
        return data_runsheet(**kwargs)

    def __str__(self):
        return str(self.value)

    def __lt__(self, other):
        return self.value < other.value


class data_irods_object(data_base):

    @property
    def htmlstring(self):
        shortname = self.value.split('/')[-1]
        return '<a href="#" data-toggle="modal" data-target="#myOutput" onClick="fillModal(\'{0}\', \'{1}\')">{1}</a>'.format(self.value, shortname)

    @staticmethod
    def factory(**kwargs):
        return data_irods_object(**kwargs)

    def __lt__(self, other):
        return self.value < other.value


class data_projectid(data_base):

    @property
    def htmlstring(self):
        return '<a href="{0}">{1}</a>'.format(url_for('projects.show_projects', project=self.value), self.value)

    @staticmethod
    def factory(**kwargs):
        return data_projectid(**kwargs)

class data_process(data_base):

    @property
    def htmlstring(self):
        return '<a href="{0}">{1}</a>'.format(url_for('projects.show_projects', page='processes', process=self.value), self.value)

    @staticmethod
    def factory(**kwargs):
        return data_process(**kwargs)


class data_processgroupid(data_base):

    @property
    def htmlstring(self):
        return self.value

    @property
    def htmlshort(self):
        return f'<div data-toggle="tooltip" title={self.value}>{self.value[:8]}</div'
        
    @staticmethod
    def factory(**kwargs):
        return data_processgroupid(**kwargs)


class data_url(data_base):

    @property
    def htmlstring(self):
        return '<a href="{0}">{0}</a>'.format(self.value)

    @staticmethod
    def factory(**kwargs):
        return data_url(**kwargs)


# Register all AVU objects
for classname in [a for a in globals() if a[:5] == 'data_' and a != 'data_base']:
    factory.register_builder(classname[5:], globals()[classname].factory)
 
