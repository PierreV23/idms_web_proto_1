#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 10 15:22:06 2020

@author: wierinve
"""

import re
from datetime import datetime
from flask import url_for
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta
from irods.column import Criterion
from app.object_factory import ObjectFactory

KNOWN_ATTRIBUTES = {
    'Date': 'date',
    'import_timestamp': 'timestamp',
    'stage_time': 'timestamp',
    'sys::pipeline::input_collection_id': 'collection_id',
    'sys::pipeline::used_by': 'runsheet'
}

MAXLEN = 45

factory = ObjectFactory()


def AVU(attr, value, unit):
    my_unit = KNOWN_ATTRIBUTES.get(attr) if unit is None else unit
    return factory.create(my_unit, attr=attr, value=value, unit=my_unit)

class AVU_base():
    def __init__(self, attr, value, unit=None):
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
    def __init__(self, attr, value, unit=None):
        super().__init__(attr, int(value), unit)

    def __str__(self):
        return str(self.value)

    @staticmethod
    def factory(**kwargs):
        return AVU_int(**kwargs)

    def __int__(self):
        return self.value

    def __lt__(self, other):
        return self.value < other.value


class AVU_boolean(AVU_base):

    def __str__(self):
        return 'TRUE' if self.value else 'FALSE'

    @property
    def htmlstring(self):
        return str(self.value)

    @staticmethod
    def factory(**kwargs):
        return AVU_boolean(**kwargs)


class AVU_timestamp(AVU_base):
    def __init__(self, attr, value, unit=None):
        try:
            myvalue = float(value)
            self._formatted_date = datetime.fromtimestamp(myvalue).strftime("%d-%m-%Y %H:%M:%S")
        except:
            myvalue = value
            self._formatted_date = value
        super().__init__(attr, myvalue, unit)

    def __str__(self):
        return self._formatted_date

    @property
    def htmlstring(self):
        return self.__str__()

    @staticmethod
    def factory(**kwargs):
        return AVU_timestamp(**kwargs)

    def __lt__(self, other):
        return self.value < other.value

INFINITE_DATE = AVU_timestamp(attr='none', value=1E11)


class AVU_irods_collection(AVU_base):

    def displaystring(self, maxlen=999):
        nameparts = self.value.split('/')
        shortname = nameparts[-1]
        prefix = '/{}'.format('/'.join(nameparts[1:-1]))
        if len(self.value) > maxlen:
            # LINE TOO LONG
            prefixlen = max(1, maxlen - len(shortname) - 2)
            prefix = '..' + prefix[-prefixlen:]
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
        return AVU_irods_collection(**kwargs)

    def __lt__(self, other):
        return self.value < other.value


class AVU_collection_id(AVU_base):
    def __init__(self, attr, value, unit=None):
        self._ref_col = None
        self._searched_for_ref_col = False
        super().__init__(attr, value, unit)

    @property
    @login_required
    def ref_col(self):
        if self._searched_for_ref_col:
            return self._ref_col
        irods_session = current_user.irods_session
        query = irods_session.query(Collection.name).filter( \
                                   Criterion('=', CollectionMeta.name, 'sys::dataset_id')).filter( \
                                   Criterion('=', CollectionMeta.value, self.value))
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
        return AVU_collection_id(**kwargs)


class AVU_runsheet(AVU_base):

    @property
    def htmlstring(self):
        runsheet_id = re.sub('-runsheet.yaml', '', self.value)
        return '<a href={0}?name={1} data-toggle="tooltip" title="{1}">{2}</a>'.format(url_for('jobs.show_jobdetails'), self.value, runsheet_id)

    @staticmethod
    def factory(**kwargs):
        return AVU_runsheet(**kwargs)

    def __str__(self):
        return str(self.value)

    def __lt__(self, other):
        return self.value < other.value


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

# Register all AVU objects
for classname in [a for a in globals() if a[:4] == 'AVU_' and a != 'AVU_base']:
    factory.register_builder(classname[4:], globals()[classname].factory)
 