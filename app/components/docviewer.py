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
from flask import Blueprint, Response, render_template, request, url_for, send_file, jsonify, abort
from flask_login import current_user, login_required
import urllib.parse
from irods.exception import CAT_NO_ACCESS_PERMISSION, SYS_FILE_DESC_OUT_OF_RANGE
from idms.common.irods.irods_sessions import irods_manager
from idms.common.filesys.fs_irods import fs_irods
from app.utils.constants import INDEX_FORMATS

bp = Blueprint('docviewer', __name__, url_prefix='/docviewer')

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

@bp.route('/serve_image')
def serve_image():
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    with irods_manager.session(current_user) as session:
        obj = fs_irods(session=session).getfile(path)
        imagefile = obj.open('r')
    return send_file(imagefile, download_name=os.path.split(path)[1],
                     as_attachment=False)

@bp.route('_access')
def test_access():
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    with irods_manager.session(current_user) as session:
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
    
@bp.route('/download_object')
def download_object():
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    with irods_manager.session(current_user) as session:
        objectfile = fs_irods(session=session).getfile(path).open('r')
        AA = send_file(objectfile, download_name=os.path.split(path)[1],
                         as_attachment=True)
    return AA

@bp.route('/serve_file')
def serve_file():
    """ Serve any iRODS dataobject
        
        args:
            path: path to irods file

        This function honors the Range request header to serve partial irods dataobjects
    """
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    range_header = request.headers.get('Range')
    with irods_manager.session(current_user) as session:
        try:
            obj = fs_irods(session=session).getfile(path)
        except:
            abort(404, description="Dataobject not found")

        file_size = obj.filesize()
        if not range_header:
        # If no Range header, send the entire file
            objectfile = obj.open('r')        
            return send_file(objectfile, mimetype="application/octet-stream")
        try:
            # Parse the Range header (e.g., "bytes=0-1024")
            bytes_range = range_header.strip().split('=')[1].split('-')
            if (bytes_range[0]):
                start = int(bytes_range[0])
                end = int(bytes_range[1]) if bytes_range[1] else file_size - 1
            else:
                start = file_size - int(bytes_range[1])
                end = file_size - 1
        except (IndexError, ValueError):
            # Handle invalid Range header format
            abort(416, description="Invalid Range header")

        # Ensure the requested range is valid
        if start >= file_size or end >= file_size or start > end:
            abort(416, description="Requested range is not satisfiable")

        chunk_length = end - start + 1

        objectfile = obj.open('r')

        def generate(length):
            objectfile.seek(start)
            while length > 0:
                # Read 1MB chunks
                chunk = objectfile.read(min(1048576, length))
                if not chunk:
                    break
                yield chunk
                length -= len(chunk)

        # Create the response
        response = Response(generate(chunk_length), 206) #, mimetype='video/mp4')
        response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Content-Length'] = str(chunk_length)

        return response


def find_index():
    '''
    finds an index file for a file, by checking the existence of:
    filename.extension.index_extension or filename.index_extension
    in the location of the original file
    '''
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    filename, file_extension = os.path.splitext(path.lower())
    format = file_extension.strip(".")
    
    with irods_manager.session(current_user) as session:

        # Handle IGV extensions        
        if format in INDEX_FORMATS:           
            index_format = INDEX_FORMATS[format]
            # Search for index files, both with and without the original extension
            index_path = None
            for index_path in [f'{path}.{index_format}', f'{os.path.splitext(path)[0]}.{index_format}']:
                if fs_irods(session=session).fileexists(index_path):
                    break
            return {"exists": True, "index_path": index_path}

    return {"exists": False, "index_path": None}


@bp.route("/check_index")
def check_index():
    result = find_index()
    return jsonify(result)


@bp.route('/serve_object')
def serve_object():
    path = urllib.parse.unquote(request.args.get('path', '/', type=str))
    filename, file_extension = os.path.splitext(path.lower())
    coll, dataobject = os.path.split(path)
    with irods_manager.session(current_user) as session:

        # Handle IGV extensions        
        if file_extension in [".bam", ".cram"]:
            format=file_extension.strip(".")

            # Get user settings for reference genome
            hosted_genome = None
            ref_object = None
            reftype = current_user.settings.get('igv::reftype', None)
            if reftype == 'hosted':
                hosted_genome = current_user.settings.get('igv::genome', 'hg38')
            elif reftype == 'object':
                ref_object = current_user.settings.get('igv::fasta')
            
            return render_template('igv.html', coll=coll, path=path, name=dataobject, format=format,
                reftype=reftype, ref_object=ref_object, genome=hosted_genome)  

        obj = fs_irods(session=session).getfile(path)
        objectfile = obj.open('r')
        mimetype = None
        # Handle csv files
        if file_extension in [".csv", ".tsv"]:
            output = csvconvert(objectfile)
            return output
        # Handle markdown files
        if file_extension in [".md"]:
            output = mdconvert(objectfile)
            return output
        # Handle image files
        if file_extension in [".jpg", ".png"]:
            output = '<img height="100%" src="' + url_for('docviewer.serve_image') +  "?path=" + path + '">'
            return output
        # Handle text files
        if file_extension in [".re", ".cfg", ".xml", ".out", ".yml", ".yaml", ".err", ".log", ".metrics", ".vcf" ]:
            mimetype = "text/plain"

        returnobject = send_file(objectfile, download_name=os.path.split(path)[1],
                                    as_attachment=False, mimetype=mimetype, max_age=-1)
    return returnobject