import os
import json
import jsonavu
from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import current_user
from app import iqry
from app.constants import ATTR_UISCHEMA, SCHEMATA_PATH
from app.upload import getSchemataForProject
from app.irodssessions import irods_manager
from irods.models import CollectionMeta

bp = Blueprint('metaedit', __name__, url_prefix='/metaedit')

PROJECT_ATTRS = ['user::upload::settings::projectID']
SCHEMA_ATTR = 'user::upload::schemafile'
ATTR_UPLOADPREFIX = 'user::upload::meta::'


def schemapath_abs(schemapath_rel):
    """ Translate relative to absolute schemapath:

        ex:
        input: salm/default
        output: /rivmZone/system/schemata/salm/default.json
    """
    return f"{os.path.join('/', current_user.irods_zone, SCHEMATA_PATH, schemapath_rel)}.json"

def schemapath_rel(schemapath_abs):
    """ Translate absolute to relative schemapath:

        ex:
        input: /rivmZone/system/schemata/salm/default.json
        output: salm/default.json
    """
    base = os.path.join('/', current_user.irods_zone, SCHEMATA_PATH)
    result, _ = os.path.splitext(os.path.relpath(schemapath_abs, start=base))
    return result

@bp.route('/')
def metadata_editor():
    schema_endpoint = url_for('metaedit.schemata', collection='/rivmZone_acc_01/home/wierinve/burning-point')
    print(url_for('metaedit.schemata', metadata=schema_endpoint))
    return render_template('metadata_editor.html', **request.args)

@bp.route('_schemata')
def schemata():
    """Return a list of schemata 

       request parameter is the upload path
       Return structure is a bootstraptable data structure like:
       {
            'rows': [
                    {'schema': 'schemaname,
                    'selected: True
                    },
                    ...
            ]
       }
    """
    
    # TODO make search path por specific object type
    objecttype = request.args.get('objecttype')
    collection_name = request.args.get('collection')
    project_name = request.args.get('project')
    
    if not collection_name:
        return jsonify({})

    # Retrieve project from the collection
    project = None
    for project_attr in PROJECT_ATTRS:
        project = iqry.qcollmetaval(collection_name, project_attr)
        if not project is None:
            objecttype = 'project'
            break
    if project is None:
        return jsonify({})
    
    # Retrieve schemata for this project
    schemata = { k: schemapath_rel(v) for k, v in getSchemataForProject(project).items() }

    # Get schemata in use for the collection
    schemata_in_use = [ a[CollectionMeta.value] for a in iqry.qcollmetavals(collection_name, SCHEMA_ATTR)]
    print(f'{schemata_in_use=}')


    print(f"{schemata=}")
    rows = [
        {'schema': k, 'selected': v in schemata_in_use, 'schemapath': v} for k, v in schemata.items()
    ]
    return jsonify({'rows': rows, 'objecttype': objecttype})

@bp.route('_store_metadata', methods=['POST'])
def store_metadata():
    """Stores the metadata provided by the data structure
       under the schema <schemapath> on the upload collection
    """
    collection =  request.json.get('collection')
    data = request.json.get('data')
    schemapath = request.json.get('schemapath')
    if not (collection and data and schemapath):
        return jsonify({}), 500
    store_collection_metadata_structured(collection, data, schemapath)
    return jsonify({'result': 'OK'}), 200


@bp.route('_set_schemata_for_collection', methods=['POST'])
def set_schemata_for_collection():
    """ Store the schemata used on the collection with
        key SCHEMA_ATTR
        There can be multiple schemata

        args:
            collection: collection path
            schemapath: path to the schema dataobject
            action(str): add or remove
    """
    collection = request.json.get('collection')
    schemapath = request.json.get('schemapath')
    action = request.json.get('action')
    print(collection, schemapath, action)
    if not (collection and schemapath and action):
        return jsonify({}), 500
    if action == 'add':
        iqry.addcollmetaval(collection, SCHEMA_ATTR, schemapath)
    if action == 'remove':
        # TODO: Remove the related metadata
        iqry.delcollmeta(collection, SCHEMA_ATTR, schemapath)
    return jsonify({ 'result': 'OK'}), 200

@bp.route('_get_schema_and_data', methods=['GET'])
def get_schema_and_data():
    """ Retrieve a metadata schema, the uiSchema
        and the already existing metadata for the schema

        Params:
            schemapath: path to the schema dataobject
            collection: path to the collection
    """
    content = "{}"
    uiSchema = "{}"
    data = "{}"
    schemapath = request.args.get('schemapath')
    collection = request.args.get('collection')
    if not (schemapath and collection):
        return jsonify({}), 500
    with irods_manager.session() as session:
        obj = session.data_objects.get(schemapath_abs(schemapath))
        with obj.open('r') as f:
            content = f.read().decode('UTF-8')
        uiSchemaFile = obj.metadata.get_all(ATTR_UISCHEMA)
        if uiSchemaFile:
            try:
                uiSchemaPath = uiSchemaFile[0].value
                uiObj =  session.data_objects.get(uiSchemaPath)
                with uiObj.open('r') as f:
                    uiSchema = f.read().decode('UTF-8')
            except:
                pass
    data = get_collection_metadata_structured(collection).get(schemapath, {})
    return { 'schema': content, 'uiSchema': uiSchema, 'data': json.dumps(data) }

def get_collection_metadata_structured(collection):
    """ Get schema metadata from a collection
        Removes the ATTR_UPLOADPREFIX prefix from attribute name
        Use jsonavu package to retrieve metadata structure
    """
    start = len(ATTR_UPLOADPREFIX)
    collection_metadata = iqry.qcollmeta(collection)
    jsonavu_metadata = [
        {
            'a': record[CollectionMeta.name][start:],
            'v': record[CollectionMeta.value],
            'u': record[CollectionMeta.units]
        } for record in collection_metadata if record[CollectionMeta.name].startswith(ATTR_UPLOADPREFIX)
    ]
    data = jsonavu.avu2json(jsonavu_metadata, '0') or {}
    return data

def remove_collection_metadata(collection, prefix):
    metadata = iqry.qcollmeta(collection)
    for record in metadata:
        if record[CollectionMeta.name].startswith(prefix):
            iqry.delcollmeta(collection, record[CollectionMeta.name])

def store_collection_metadata_structured(collection, data, schemapath):
    """ Store schema metadata from a collection

        Use jsonavu package to create metadata structure

        Does not modify data from other schemata
    """
    existing_data = get_collection_metadata_structured(collection)
    existing_data[schemapath] = data
    jsonavu_metadata = jsonavu.json2avu(existing_data, '0')
    remove_collection_metadata(collection, ATTR_UPLOADPREFIX)
    for avu in jsonavu_metadata:
        iqry.scollmetaval(collection, f"{ATTR_UPLOADPREFIX}{avu['a']}", avu['v'], avu['u'])
