from flask import Blueprint, render_template, request, jsonify
from app import iqry
from app.upload import getSchemataForProject

bp = Blueprint('metaedit', __name__, url_prefix='/metaedit')

PROJECT_ATTRS = ['user::upload::settings::projectID']
SCHEMA_ATTR = 'user::upload::schemafile'


@bp.route('_schemas_for_collection')
def schemas_for_collection():
    """Return a list of schemas for a collection

       Primary aimed at upload collections, since
       those are the only ones where we edit metadata currently.
       But could easily be extended as a generic metadata editor.
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
    collection_name = request.args.get('collection')
    if not collection_name:
        return jsonify({})

    # Retrieve project from the collection
    project = None
    for project_attr in PROJECT_ATTRS:
        project = iqry.qcollmetaval(collection_name, project_attr)
        if not project is None:
            break
    if project is None:
        return jsonify({})

    # Retrieve schemas for this project
    schemata = getSchemataForProject(project)

    # Get schemas in use for the collection
    schemata_in_use = [ a for a in iqry.qcollmetavals(collection_name, SCHEMA_ATTR)]
    print(f'{schemata_in_use=}')


    print(f"{schemata=}")
    rows = [      
        {'schema': k, 'selected': v in schemata_in_use, 'schemapath': v} for k, v in schemata.items()
    ]
    return jsonify({'rows': rows})

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
    ...

    
    

