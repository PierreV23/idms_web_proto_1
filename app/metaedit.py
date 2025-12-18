import os
import json
import jsonavu
import logging
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from app import iqry
from app.constants import (SCHEMATA_BASE_PATH, 
                            DATASET_SCHEMATA_PATH, 
                            PROJECT_SCHEMATA_PATH, 
                            REFERENCE_DATASET_SCHEMATA_PATH,
                            ATTR_SCHEMA_IN_USE, 
                            ATTR_UPLOAD_DEFAULT_PREFIX, 
                            ATTR_UPLOAD_PREFIX)
from app.irodssessions import irods_manager
from irods.models import CollectionMeta
from irods.exception import CollectionDoesNotExist
from pathlib import Path

bp = Blueprint('metaedit', __name__, url_prefix='/metaedit')

def get_schemata( schema_collection ):
    """ Return list of all schemata from the leaf down to the base collection
        as a dictionary:
        {
            schema-name : schema-location
            TODO: what if the same name is on different levels
        }
    """
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
#     return render_template('metadata_editor.html', **request.args)


@bp.route('/schemata_project')
def schemata_for_project():
    """ Schemata for a project
    """
    project_name = request.args.get('project_name', '')
    meta_schemata_collection = Path('/', current_user.irods_zone, SCHEMATA_BASE_PATH, PROJECT_SCHEMATA_PATH, project_name)
    meta_values_collection = request.args.get('collection')
    return schemata(meta_schemata_collection, meta_values_collection)


@bp.route('/schemata_dataset')
def schemata_for_dataset():
    """ Schemata for a dataset, in a project or in the home directory of current user
    """
    project_name = request.args.get('project_name', '')
    meta_schemata_collection = Path('/', current_user.irods_zone, SCHEMATA_BASE_PATH, DATASET_SCHEMATA_PATH, project_name)
    meta_values_collection = request.args.get('collection')
    return schemata(meta_schemata_collection, meta_values_collection)


@bp.route('/schemata_reference')
def schemata_for_reference_dataset():
    """ Schemata for a reference dataset, so not linked to a project
    """
    refdata_name = request.args.get('refdata_name', '')
    meta_schemata_collection = Path('/', current_user.irods_zone, SCHEMATA_BASE_PATH, REFERENCE_DATASET_SCHEMATA_PATH, refdata_name)
    meta_values_collection = request.args.get('collection')
    return schemata(meta_schemata_collection, meta_values_collection)


def schemata(meta_schemata_collection :str, meta_values_collection :str):
    """ Returns a list of schemata

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
    """

    # Retrieve schemata for this project
    schemata = get_schemata(meta_schemata_collection)

    # Get schemata in use for the collection
    schemata_in_use = [a[CollectionMeta.value] for a in iqry.qcollmetavals(meta_values_collection, ATTR_SCHEMA_IN_USE)]

    rows = [
        {'schema': k, 'selected': v in schemata_in_use, 'schemapath': v, 'order': v.count('/')} for k, v in schemata.items()
    ]
    return jsonify({'rows': rows})


@bp.route('_store_metadata', methods=['POST'])
def store_metadata():
    """ Stores the metadata provided by the data structure
        under the schema <schemapath> on a collection
    """
    collection = request.json.get('collection')
    data = request.json.get('data')
    schemapath = request.json.get('schemapath')
    prefix = request.json.get('prefix')
   
    if not (collection and data and schemapath and prefix):
        return jsonify({}), 500
    try:
        store_collection_metadata_structured(collection, data, schemapath, prefix)
        return jsonify({'result': 'OK'}), 200
    except Exception as e:
        logging.error(f'Not allowed to edit this metadata: {e}')
        return jsonify({}), 500

@bp.route('_set_schemata_for_collection', methods=['POST'])
def set_schemata_for_collection():
    """ Store the schemata used on the collection with
        key ATTR_UPLOAD_PREFIX
        There can be multiple schemata

        args:
            attr_type: default schema attribute or in use attribute
            collection: collection path
            schemapath: path to the schema dataobject
            action(str): add or remove
    """
    attr_type = request.json.get('attr_type')
    collection = request.json.get('collection')
    schemapath = request.json.get('schemapath')
    prefix = ATTR_UPLOAD_PREFIX
    action = request.json.get('action')
    prefix = request.json.get('prefix')
    
    if not (collection and schemapath and action):
        return jsonify({}), 500
    if action == 'add':
        try:
            iqry.addcollmetaval(collection, attr_type, schemapath)
            return jsonify({ 'result': 'OK' }), 200
        except Exception as e:
            logging.error(f'Not allowed to add schemata: {e}')
            return jsonify({}), 500
    if action == 'remove':
        # Remove the related metadata
        try:
            iqry.delcollmeta(collection, attr_type, schemapath)
            store_collection_metadata_structured(collection, None, schemapath, prefix)
            remove_collection_metadata(collection, prefix + schemapath)
            return jsonify({ 'result': 'OK' }), 200
        except Exception as e:
            logging.error(f'Not allowed to remove schemata: {e}')
            return jsonify({}), 500


def remove_required(schema_json :dict):
    '''
    Recursively remove all `required` constraints from a JSON Schema.
    Also set minItems to 0.
    Works for nested objects, as well as the root required field.
    For use in default schemata, where no fields should be required
    
    input: json schema
    output: json schema without required fields and with minItems = 0
    '''
    
    # check keys on top level
    if isinstance(schema_json, dict):
        for key, value in schema_json.items():
            if key == "required" and isinstance(value, list):
                schema_json[key] = []
            if key == "minItems" and isinstance(value, int):
                schema_json[key] = 0
            else:
                # check lower level items (nested)
                remove_required(value)
    
    # check items in a list, and inspect them separately            
    elif isinstance(schema_json, list):
        for item in schema_json:
            remove_required(item)
    
    # Use for testing, writes the json to a file
    # with open(Path(__file__).resolve().parent + "/schemata/_schema_development/rivm_test_clean.json", "w", encoding="utf-8") as f:
    #    f.write(json.dumps(schema_json))
    
    return schema_json


@bp.route('_get_schema_and_data', methods=['GET'])
def get_schema_and_data():
    """ Retrieve a metadata schema, the uiSchema
        and the already existing metadata for the schema

        Params:
            schemapath: path to the schema dataobject
            collection: path to the collection
    """
    schema = "{}"
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
            schema = f.read().decode('UTF-8')
            
            # remove required fields from schema, first turn into json.
            if prefix==ATTR_UPLOAD_DEFAULT_PREFIX:
                schema_json = json.loads(schema)
                schema_clean = remove_required(schema_json)
                schema = json.dumps(schema_clean)
        
        # Find the path to a ui schema file, and check for existing ones (ui_ + file_name)
        uiSchemaPath = os.path.dirname(schemapath) + '/ui/ui_' + os.path.basename(schemapath)
        if uiSchemaPath:
            try:
                uiObj = session.data_objects.get(uiSchemaPath)
                with uiObj.open('r') as f:
                    uiSchema = f.read().decode('UTF-8')
            except:
                pass
    default_data = {}
    if meta_default_values_collection:
        default_data = get_collection_metadata_structured(meta_default_values_collection, ATTR_UPLOAD_DEFAULT_PREFIX).get(schemapath, {})
    
    used_data = get_collection_metadata_structured(meta_values_collection, prefix).get(schemapath, {})
    # first take all values from default, then add or overwrite values from used data
    #     
    data = default_data | used_data
    return { 'schema': schema, 'uiSchema': uiSchema, 'data': json.dumps(data) }


def get_collection_metadata_structured(collection :str, prefix :str) -> dict:
    """ Get schema metadata from a collection
        
        Removes the ATTR_UPLOADPREFIX prefix from attribute name
        
        Use jsonavu package to retrieve metadata structure
    """
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
    """ Remove metadata with a specified prefix from collection   
    """
    metadata = iqry.qcollmeta(collection)
    for record in metadata:
        if record[CollectionMeta.name].startswith(prefix):
            iqry.delcollmeta(collection, record[CollectionMeta.name])


def store_collection_metadata_structured(collection, data, schemapath, prefix):
    """ Store schema metadata from a collection

        Use jsonavu package to create metadata structure

        Does not modify data from other schemata
    """
    existing_data = get_collection_metadata_structured(collection, prefix)
    existing_data[schemapath] = data
    jsonavu_metadata = jsonavu.json2avu(existing_data, '0')  # Why 0?
    remove_collection_metadata(collection, prefix)
    for avu in jsonavu_metadata:
        iqry.scollmetaval(collection, f"{prefix}{avu['a']}", avu['v'], avu['u'])