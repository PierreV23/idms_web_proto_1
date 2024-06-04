#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 15:16:25 2019

@author: wierinve
"""
import os
import csv
import ctypes
import markdown
from flask import Blueprint, render_template, request, url_for, send_file, jsonify
from flask_login import current_user, login_required
import urllib.parse
from irods.exception import CAT_NO_ACCESS_PERMISSION, SYS_FILE_DESC_OUT_OF_RANGE
from app.irodssessions import irods_manager
from fs_irods import fs_irods

BP = Blueprint('docviewer', __name__, url_prefix='/docviewer')

csv.field_size_limit(int(ctypes.c_ulong(-1).value // 2))

def csvconvert(fobj):
    csvtext = fobj.read().decode('utf-8')
    try:
        dialect = csv.Sniffer().sniff(csvtext[:1024], delimiters=',;\t')
    except:
        dialect = None
    objcsv = csv.reader(csvtext.split('\n'), dialect)
    return render_template('csvview.html', data=objcsv)

def mdconvert(fobj):
    return markdown.markdown(fobj.read().decode('utf-8'))


@BP.route('/serve_image')
def serve_image():
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    ifs = current_user.ifs
    obj = ifs.getfile(path)
    imagefile = obj.open('r')
    return send_file(imagefile, download_name=os.path.split(path)[1],
                     as_attachment=False)

@BP.route('_access')
def test_access():
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    with irods_manager.session() as session:
        obj = fs_irods(session=session).getfile(path)
        try:
            objectfile = obj.open('r')
            access = 'GRANTED'
            objectfile.close()
        except (CAT_NO_ACCESS_PERMISSION, SYS_FILE_DESC_OUT_OF_RANGE):
            access = 'DENIED'
    return jsonify({
        'access': access
    })
    
@BP.route('/download_object')
def download_object():
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    #objectfile = current_user.ifs.getfile(path).open('r')
    with irods_manager.session() as session:
        objectfile = fs_irods(session=session).getfile(path).open('r')
        AA = send_file(objectfile, download_name=os.path.split(path)[1],
                         as_attachment=True)
    return AA

@BP.route('/serve_object')
def serve_object():
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    filename, file_extension = os.path.splitext(path.lower())
    with irods_manager.session() as session:
        obj = fs_irods(session=session).getfile(path)
        objectfile = obj.open('r')
        mimetype = ''
        if file_extension in [".csv"]:
            output = csvconvert(objectfile)
            return output
        if file_extension in [".md"]:
            return mdconvert(objectfile)
        if file_extension in [".jpg", ".png"]:
            output = '<IMG HEIGHT="100%" SRC="' + url_for('docviewer.serve_image') +  "?path=" + path + '">'
            return output
        if file_extension in [".re", ".cfg", ".xml", ".out", ".yml", ".yaml", ".err", ".log" ]:
            mimetype = "text/plain"

        if mimetype:
            returnobject = send_file(objectfile, download_name=os.path.split(path)[1],
                                    as_attachment=False, mimetype=mimetype, max_age=-1)
        else:
            returnobject = send_file(objectfile, download_name=os.path.split(path)[1],
                                    as_attachment=False, max_age=-1)
    return returnobject
