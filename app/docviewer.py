#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 15:16:25 2019

@author: wierinve
"""
import os
from flask import Blueprint, render_template, redirect, request, url_for
from flask_login import login_user, current_user, login_required

bp = Blueprint('docviewer', __name__, url_prefix='/docviewer')

@bp.route('/')
@login_required
def docviewer():
    path = request.args.get('path', '/', type=str)
    action = request.args.get('action', 'none', type=str)
    filename, file_extension = os.path.splitext( path.lower() )
    fn = os.path.basename( path.lower() )
        
    print("path, filename, file_extension: ", path, fn, file_extension)
    #obj =fs_irods.fs_irods( path ).getfile( path )
    irods_session = current_user.irods_session
    ifs = current_user.ifs
    obj = ifs.getfile(path)
    with obj.open('r') as f:
        a = f.read( 500000 )
    #print (a)
    try:
        doc = a.decode('utf-8')
    except:
        f = open("static/images/pic_trulli" + file_extension, "wb")
        f.write(a)
        f.close()
        doc="Deze file kan niet gelezen worden"
    return render_template('docviewer.html', doc = doc, path = path, fn = fn, file_extension = file_extension)
