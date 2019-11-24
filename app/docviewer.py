#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 15:16:25 2019

@author: wierinve
"""
import os
from flask import Blueprint, render_template, redirect, request, url_for, send_file
from flask_login import login_user, current_user, login_required
import csv

bp = Blueprint('docviewer', __name__, url_prefix='/docviewer')

@login_required
def csvconvert(fobj):
    a = fobj.read().decode('utf-8')
    objCsv = csv.reader(a.split('\n'))
    hTable = '<table class="table table-sm table-striped">'
    for row in objCsv:
        hTable = hTable + '<tr>'
        for col in row:
            hTable = hTable + '<td>' + col + '</td>'
        hTable = hTable + '</tr>'
    hTable = hTable + '</table>'
    return '<html><head><link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css" integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T" crossorigin="anonymous"></head><body>{}</body></html>'.format(hTable)

@bp.route('/serve_image')
@login_required
def serve_image():
    path = request.args.get('path', '/', type=str)
    print("serve_image request for {}".format(path))
    filename, file_extension = os.path.splitext( path.lower() )
    ifs = current_user.ifs
    obj = ifs.getfile(path)
    f = obj.open('r')
    mimetype=''
    if file_extension in [ ".re", ".cfg" ]:
        mimetype = "text/plain"
    if file_extension in [ ".csv" ]:
        output = csvconvert(f)
        return output

    if mimetype:
        X = send_file(f, attachment_filename = os.path.split(path)[1], 
                      as_attachment = False, mimetype=mimetype)
    else:
        X = send_file(f, attachment_filename = os.path.split(path)[1], 
                      as_attachment = False)    
    return X

@bp.route('/')
@login_required
def docviewer():
    path = request.args.get('path', '/', type=str)
#    filename, file_extension = os.path.splitext( path.lower() )
#    fn = os.path.basename( path.lower() )        
#    irods_session = current_user.irods_session
#    ifs = current_user.ifs
#    obj = ifs.getfile(path)
    return '<embed width="100%" height="100%" src="{}?path={}">'.format(url_for('docviewer.serve_image'), path)
