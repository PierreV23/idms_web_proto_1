import os
import json
import jsonavu
import logging
from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from app.utils import cached_iqry
from app.utils.constants import SCHEMATA_BASE_PATH, DATASET_SCHEMATA_PATH, PROJECT_SCHEMATA_PATH, REFERENCE_DATASET_SCHEMATA_PATH
from idms.common.constants.attribute_names import (
                            ATTR_SCHEMA_IN_USE,
                            ATTR_PROJECT_SUFFIX,
                            ATTR_DATASET_DEFAULT_SUFFIX,
                            ATTR_REFERENCE_SUFFIX,
                            ATTR_METADATA_PREFIX, 
                            ATTR_UPLOAD_DEFAULT_PREFIX, 
                            ATTR_UPLOAD_PREFIX,
                            AVU2JSON_PREFIX
                        )
from idms.common.irods.irods_sessions import irods_manager
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
    
    with irods_manager.session(current_user) as session:
        
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
    suffix=ATTR_PROJECT_SUFFIX
    return schemata(meta_schemata_collection, meta_values_collection, suffix)



@bp.route('/schemata_dataset')
def schemata_for_dataset():
    """ Schemata for a dataset, in a project or in the home directory of current user
    """
    project_name = request.args.get('project_name', '')
    meta_schemata_collection = Path('/', current_user.irods_zone, SCHEMATA_BASE_PATH, DATASET_SCHEMATA_PATH, project_name)
    meta_values_collection = request.args.get('collection')
    suffix=ATTR_DATASET_DEFAULT_SUFFIX
    return schemata(meta_schemata_collection, meta_values_collection, suffix)


@bp.route('/schemata_reference')
def schemata_for_reference_dataset():
    """ Schemata for a reference dataset, so not linked to a project
    """
    refdata_name = request.args.get('refdata_name', '')
    meta_schemata_collection = Path('/', current_user.irods_zone, SCHEMATA_BASE_PATH, REFERENCE_DATASET_SCHEMATA_PATH, refdata_name)
    meta_values_collection = request.args.get('collection')
    suffix=ATTR_REFERENCE_SUFFIX
    return schemata(meta_schemata_collection, meta_values_collection, suffix)


def schemata(meta_schemata_collection :str, meta_values_collection :str, suffix :str):
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

    # Get schemata in use for the collection (specific suffix -> type)
    schemata_in_use = [a[CollectionMeta.value] for a in cached_iqry.qcollmetavals(meta_values_collection, ATTR_SCHEMA_IN_USE + suffix)]

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
            cached_iqry.addcollmetaval(collection, attr_type, schemapath)
            return jsonify({ 'result': 'OK' }), 200
        except Exception as e:
            logging.error(f'Not allowed to add schemata: {e}')
            return jsonify({}), 500
    if action == 'remove':
        # Remove the related metadata
        try:
            cached_iqry.delcollmeta(collection, attr_type, schemapath)
            store_collection_metadata_structured(collection, None, schemapath, prefix)
            remove_collection_metadata(collection, prefix + schemapath)
            return jsonify({ 'result': 'OK' }), 200
        except Exception as e:
            logging.error(f'Not allowed to remove schemata: {e}')
            return jsonify({}), 500


def remove_all_constraints(schema_json :dict) ->dict:

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
                remove_all_constraints(value)
    
    # check items in a list, and inspect them separately            
    elif isinstance(schema_json, list):
        for item in schema_json:
            remove_all_constraints(item)
    
    return schema_json


def remove_specific_constraints(schema_json :dict, keys :list = None) ->dict:
    '''
    Recursively remove specific `required` constraints from a JSON Schema if they are in a list of keys
    This keys can be listed in "required": or have the property "minItems": >0
    Works for nested objects, as well as the root required field.
    For use for infered metadata fields, that are not manually iput, but are requirred in the original schema
    
    input:  schema_json: the json schema
            keys: list of keys in schema_json to limit the removal of constraints to
    
    output: json schema without specific required constraints
    '''
    
    # No keys, return original schema
    if keys == None or keys == []:
        return schema_json
     
    # check keys on top level
    if isinstance(schema_json, dict):
        
        # Remove specific keys from "required" 
        if "required" in schema_json and isinstance(schema_json["required"], list):
            schema_json["required"] = [ field for field in schema_json["required"] if field not in keys ]

        # Traverse properties while knowing the property name, these could be nested!
        if "properties" in schema_json and isinstance(schema_json["properties"], dict):
            
            for prop_name, prop_schema in schema_json["properties"].items():
                
                if not prop_name in keys:
                    continue
                if "minItems" in prop_schema:
                    prop_schema["minItems"] = 0
                
                # check the nested items for constraints    
                remove_specific_constraints(prop_schema, keys)
        
    # check items in a list of dicts, and inspect them one by one            
    elif isinstance(schema_json, list):
        for item in schema_json:
            remove_specific_constraints(item, keys)
            
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
    metadata_infered = current_app.config.get('METADATA_INFERED')
    
    # find collection where project metadata is located
    meta_default_values_collection = request.args.get('meta_default_values_collection')
    meta_values_collection = request.args.get('collection')
    if not (schemapath):
        return jsonify({}), 500
    with irods_manager.session(current_user) as session:
        obj = session.data_objects.get(schemapath)
        with obj.open('r') as f:
            schema = f.read().decode('UTF-8')
            
            # remove specific required constraints from schema (if metadata is infered)
            for schemaname, keys in metadata_infered.items():
                if schemapath.endswith(schemaname):
                    schema_json = json.loads(schema)
                    schema_json = remove_specific_constraints(schema_json, keys)
                    schema = json.dumps(schema_json)
            
            # remove all required constraints from schema (if metadata is default metadata)
            if prefix==ATTR_UPLOAD_DEFAULT_PREFIX:
                schema_json = json.loads(schema)
                schema_json = remove_all_constraints(schema_json)
                schema = json.dumps(schema_json)
        
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
    
    # find default metadata from default values collection
    if meta_default_values_collection:
        default_data = get_collection_metadata_structured(meta_default_values_collection, ATTR_UPLOAD_DEFAULT_PREFIX).get(schemapath, {})
    
    # The preset default metadata for dataset upload is the project metadata
    if meta_default_values_collection == meta_values_collection:
        default_data = get_collection_metadata_structured(meta_default_values_collection, ATTR_METADATA_PREFIX).get(schemapath, {})
    
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
    collection_metadata = cached_iqry.qcollmeta(collection)
    jsonavu_metadata = [
        {
            'a': record[CollectionMeta.name][start:],
            'v': record[CollectionMeta.value],
            'u': record[CollectionMeta.units]
        } for record in collection_metadata if record[CollectionMeta.name].startswith(prefix)
    ]
    data = jsonavu.avu2json(jsonavu_metadata, AVU2JSON_PREFIX) or {}
    return data


def remove_collection_metadata(collection, prefix):
    """ Remove metadata with a specified prefix from collection   
    """
    metadata = cached_iqry.qcollmeta(collection)
    for record in metadata:
        if record[CollectionMeta.name].startswith(prefix):
            cached_iqry.delcollmeta(collection, record[CollectionMeta.name])


def store_collection_metadata_structured(collection, data, schemapath, prefix):
    """ Store schema metadata from a collection

        Use jsonavu package to create metadata structure

        Does not modify data from other schemata
    """
    existing_data = get_collection_metadata_structured(collection, prefix)
    existing_data[schemapath] = data
    jsonavu_metadata = jsonavu.json2avu(existing_data, AVU2JSON_PREFIX)
    remove_collection_metadata(collection, prefix)
    for avu in jsonavu_metadata:
        cached_iqry.scollmetaval(collection, f"{prefix}{avu['a']}", avu['v'], avu['u'])
