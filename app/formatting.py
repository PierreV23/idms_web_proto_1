#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 10 15:22:06 2020

@author: wierinve
"""

import re
from flask import url_for
from datetime import datetime

def format_exit_code(value):
    if value == "0":
        return "OK"
    else:
        return "FAILED"

def format_timestamp(value):
    return '<small>{}<small>'.format(datetime.fromtimestamp(float(value)).strftime("%d-%m-%Y %H:%M:%S"))

def format_runsheet(value):
    runsheet_id = re.sub('-runsheet.yaml','', value)
    print(runsheet_id)
    return '<a href={0}?name={1}>{2}</a>'.format(url_for('jobs.show_jobdetails'), value, runsheet_id)    

def format_irods_collection(value):
    return '<a href={0}?path={1}>{1}</a>'.format(url_for('collbrowser.collbrowser'), value)

def format_value(value, units):
    formatted_value = value
    if units:
        format_function_name = 'format_' + units
        if format_function_name in globals():
            formatted_value = globals()[format_function_name](value)
    return formatted_value
