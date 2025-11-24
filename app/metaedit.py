import os
import json
import jsonavu
from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import current_user
from app import iqry
from app.constants import ATTR_UISCHEMA, SCHEMATA_BASE_PATH, DATASET_SCHEMATA_PATH, PROJECT_SCHEMATA_PATH, REFERENCE_DATASET_SCHEMATA_PATH
from app.irodssessions import irods_manager
from irods.models import CollectionMeta
from irods.exception import CollectionDoesNotExist
from pathlib import Path

bp = Blueprint('metaedit', __name__, url_prefix='/metaedit')

PROJECT_ATTRS = ['user::upload::settings::projectID']
ATTR_SCHEMA_IN_USE = 'user::schema_in_use'
ATTR_SCHEMA_DEFAULT = 'user::schema_default'
ATTR_UPLOAD_PREFIX = 'user::meta::'
ATTR_UPLOAD_DEFAULT_PREFIX = 'user::default_metadata::'

def schemapath_abs(schemapath_rel):
    ''' 
        Translate relative to absolute schemapath

        example:
            input: salm/default
            output: /rivmZone/system/schemata/salm/default.json
    '''
    return f"{os.path.join('/', current_user.irods_zone, SCHEMATA_BASE_PATH, schemapath_rel)}.json"


def schemapath_rel(schemapath_abs):
    ''' 
        Translate absolute to relative schemapath:

        example:
            input: /rivmZone/system/schemata/salm/default.json
            output: salm/default.json
    '''
    base = os.path.join('/', current_user.irods_zone, SCHEMATA_BASE_PATH)
    result, _ = os.path.splitext(os.path.relpath(schemapath_abs, start=base))
    return result


def get_schemata( schema_collection ):
    '''
        Return list of all schemata from the leaf down to the base collection
        as a dictionary:
        {
            schema-name : schema-location
            TODO: what if the same name is on different levels
        }
    '''
    def get_schemata_in_coll( coll ):
        result = {}
        for obj in coll.data_objects:
            
            schemaId = Path(obj.name).stem
            path = f"{coll.path}/{obj.name}"
            result[ schemaId ] = path
        return result

    result = {}
    
    schema_collection_path = Path('/', current_user.irods_zone, schema_collection)
    
    with irods_manager.session() as session:
        
        while schema_collection_path != '/' and schema_collection_path != Path('/', current_user.irods_zone, SCHEMATA_BASE_PATH).parent: 
            try:
                schemaColl = session.collections.get(str(schema_collection_path))
                result.update(get_schemata_in_coll(schemaColl)) 
            except CollectionDoesNotExist as e:
                continue
            finally:
                # go up one level in the collection tree
                schema_collection_path = schema_collection_path.parent        
    return result


@bp.route('/')
# def metadata_editor():
#     schema_endpoint = url_for('metaedit.schemata')
#     print(url_for('metaedit.schemata', metadata=schema_endpoint))
#     return render_template('metadata_editor.html', **request.args)


@bp.route('/schemata_project')
def schemata_for_project():
    '''
        Schemata for a project
    '''
    project_name = request.args.get('project_name')
    meta_schemata_collection = Path('/', current_user.irods_zone, SCHEMATA_BASE_PATH, PROJECT_SCHEMATA_PATH, project_name)
    meta_values_collection = request.args.get('collection')
    objecttype = 'project'
    return schemata(meta_schemata_collection, meta_values_collection, objecttype)


@bp.route('/schemata_dataset')
def schemata_for_dataset():
    '''
        Schemata for a dataset, in a project or in the home directory of current user
    '''
    project_name = request.args.get('project_name', '')
    meta_schemata_collection = Path('/', current_user.irods_zone, SCHEMATA_BASE_PATH, DATASET_SCHEMATA_PATH, project_name)
    meta_values_collection = request.args.get('collection')
    objecttype = 'dataset'
    return schemata(meta_schemata_collection, meta_values_collection, objecttype)


@bp.route('/schemata_reference')
def schemata_for_reference_dataset():
    '''
        Schemata for a reference dataset, so not linked to a project
    '''
    meta_schemata_collection = request.args.get('collection')
    meta_values_collection = request.args.get('collection')
    objecttype = 'reference_dataset'
    return schemata(meta_schemata_collection, meta_values_collection, objecttype)


def schemata(meta_schemata_collection :str, meta_values_collection :str, objecttype :str):
    '''
        Returns a list of schemata

        Request parameter is the upload path
        Returns a bootstraptable data structure like:
        {
        'rows': [
                    {'schema': <schemaname>,
                    'selected: True or False,
                    'schemapath': <schemapath>,
                    'order': order to display the schemata
                }, {...}
            ]
        }
    '''

    # Retrieve schemata for this project
    schemata = get_schemata(meta_schemata_collection)

    # Get schemata in use for the collection
    schemata_in_use = [a[CollectionMeta.value] for a in iqry.qcollmetavals(meta_values_collection, ATTR_SCHEMA_IN_USE)]

    print(f'{schemata_in_use=}')
    print(f"{schemata=}")

    rows = [
        {'schema': k, 'selected': v in schemata_in_use, 'schemapath': v, 'order': v.count('/')} for k, v in schemata.items()
    ]
    return jsonify({'rows': rows})


@bp.route('_store_metadata', methods=['POST'])
def store_metadata():
    '''
        Stores the metadata provided by the data structure
        under the schema <schemapath> on a collection
    '''
    collection = request.json.get('collection')
    data = request.json.get('data')
    schemapath = request.json.get('schemapath')
    prefix = request.json.get('prefix')
    if not (collection and data and schemapath and prefix):
        return jsonify({}), 500
    store_collection_metadata_structured(collection, data, schemapath, prefix)
    return jsonify({'result': 'OK'}), 200


@bp.route('_set_schemata_for_collection', methods=['POST'])
def set_schemata_for_collection():
    ''' 
        Store the schemata used on the collection with
        key SCHEMA_ATTR
        There can be multiple schemata

        args:
            attr_type: default schema attribute or in use attribute
            collection: collection path
            schemapath: path to the schema dataobject
            action(str): add or remove
    '''
    attr_type = request.json.get('attr_type')
    collection = request.json.get('collection')
    schemapath = request.json.get('schemapath')
    action = request.json.get('action')
    print(collection, schemapath, action)
    if not (collection and schemapath and action):
        return jsonify({}), 500
    if action == 'add':
        iqry.addcollmetaval(collection, attr_type, schemapath)
    if action == 'remove':
        # TODO: Remove the related metadata
        iqry.delcollmeta(collection, attr_type, schemapath)
        store_collection_metadata_structured(collection, None, schemapath)
        remove_collection_metadata(collection, ATTR_UPLOAD_PREFIX+schemapath)
    return jsonify({ 'result': 'OK' }), 200


@bp.route('_get_schema_and_data', methods=['GET'])
def get_schema_and_data():
    ''' 
        Retrieve a metadata schema, the uiSchema
        and the already existing metadata for the schema

        Params:
            schemapath: path to the schema dataobject
            collection: path to the collection
    '''
    content = "{}"
    uiSchema = "{}"
    data = "{}"
    prefix = request.args.get('prefix')
    schemapath = request.args.get('schemapath')
    # find collection where project metadata is located
    meta_default_values_collection = request.args.get('meta_default_values_collection')
    meta_values_collection = request.args.get('collection')
    if not (schemapath):
        return jsonify({}), 500
    with irods_manager.session() as session:
        obj = session.data_objects.get(schemapath)
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
    default_data = {}
    if meta_default_values_collection:
        default_data = get_collection_metadata_structured(meta_default_values_collection, ATTR_UPLOAD_DEFAULT_PREFIX).get(schemapath, {})
    
    used_data = get_collection_metadata_structured(meta_values_collection, prefix).get(schemapath, {})
    # first take all values from default, then add or overwrite values from used data
    data = default_data | used_data
    return { 'schema': content, 'uiSchema': uiSchema, 'data': json.dumps(data) }


def get_collection_metadata_structured(collection :str, prefix :str) -> dict:
    ''' 
        Get schema metadata from a collection
        
        Removes the ATTR_UPLOADPREFIX prefix from attribute name
        
        Use jsonavu package to retrieve metadata structure
    '''
    start = len(prefix)
    collection_metadata = iqry.qcollmeta(collection)
    jsonavu_metadata = [
        {
            'a': record[CollectionMeta.name][start:],
            'v': record[CollectionMeta.value],
            'u': record[CollectionMeta.units]
        } for record in collection_metadata if record[CollectionMeta.name].startswith(prefix)
    ]
    data = jsonavu.avu2json(jsonavu_metadata, '0') or {}
    return data


def remove_collection_metadata(collection, prefix):
    '''
        Remove metadata from collection    
    '''
    metadata = iqry.qcollmeta(collection)
    for record in metadata:
        if record[CollectionMeta.name].startswith(prefix):
            iqry.delcollmeta(collection, record[CollectionMeta.name])


def store_collection_metadata_structured(collection, data, schemapath, prefix):
    ''' 
        Store schema metadata from a collection

        Use jsonavu package to create metadata structure

        Does not modify data from other schemata
    '''
    existing_data = get_collection_metadata_structured(collection, prefix)
    existing_data[schemapath] = data
    jsonavu_metadata = jsonavu.json2avu(existing_data, '0')  # Why 0?
    remove_collection_metadata(collection, prefix)
    for avu in jsonavu_metadata:
        iqry.scollmetaval(collection, f"{prefix}{avu['a']}", avu['v'], avu['u'])