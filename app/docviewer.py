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
import base64

bp = Blueprint('docviewer', __name__, url_prefix='/docviewer')

@login_required
def csvconvert(fobj):
    a = fobj.read().decode('utf-8')
    objCsv = csv.reader(a.split('\n'))
    return render_template('csvview.html', data = objCsv)

@bp.route('/serve_image')
@login_required
def serve_image():
    path = request.args.get('path', '/', type=str)
    ifs = current_user.ifs
    obj = ifs.getfile(path)
    f = obj.open('r')
    return send_file(f, attachment_filename = os.path.split(path)[1], 
                      as_attachment = False) 

@bp.route('/serve_object')
@login_required
def serve_object():
    path = request.args.get('path', '/', type=str)
    filename, file_extension = os.path.splitext( path.lower() )
    ifs = current_user.ifs
    obj = ifs.getfile(path)
    f = obj.open('r')
    mimetype=''
    if file_extension in [ ".re", ".cfg", ".xml", ".out" ]:
        mimetype = "text/plain"
    if file_extension in [ ".csv" ]:
        output = csvconvert(f)
        return output
    if file_extension in [ ".jpg", ".png" ]:
        output = '<IMG WIDTH="100%" SRC="' + url_for('docviewer.serve_image') +  "?path=" + path + '">'
        return output

    if mimetype:
        X = send_file(f, attachment_filename = os.path.split(path)[1], 
                      as_attachment = False, mimetype=mimetype)
    else:
        X = send_file(f, attachment_filename = os.path.split(path)[1], 
                      as_attachment = False)    
    return X
