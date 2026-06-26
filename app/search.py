import time
from flask import jsonify, render_template, request, Blueprint
from irods.query import SpecificQuery
from irods.exception import CAT_NO_ROWS_FOUND, CAT_SQL_ERR

from idms.common.irods.irods_sessions import irods_manager
from app.utils.flaskcache import cache, dep_zone
from app.utils.datafield import datafield
from flask_login import current_user


""" Input structures:

searchdata: {
    'keywords': [
        'keyword1', 'keyword2'
    ],
    'meta' : {
        'attr1': 'value1',
        'attr2': 'value2'
    }
}

"""

bp = Blueprint('search', __name__, url_prefix='/search')

class Const:
    KEYWORDS = 'keywords'
    META = 'meta'
    ID = 'id'
    COLLECTIONS = 'collections'
    DATAOBJECTS = 'dataobjects'
    NAME = 'name'
    VALUE = 'value'
    ATTRS = 'attrs'
    
class TableFormat:
    html = 'html'
    plain = 'plain'    

class Tables:
    coll = 'r_coll_main'
    metamap = 'r_objt_metamap'
    meta = 'r_meta_main'

# class Tables:
#     coll = 'r_coll_main'
#     metamap = 'evw_objt_metamap'
#     meta = 'evw_metamap'

def search_dict(keywords, meta_attrs):
    return {
        Const.KEYWORDS: keywords,
        Const.META: meta_attrs
    }

def result_data(collections, dataobjects, id, attrs=[]):
    return {
        Const.COLLECTIONS: collections,
        Const.DATAOBJECTS: dataobjects,
        Const.ATTRS: attrs,
        Const.ID: id
    }

@bp.route('_searchtable', methods=['POST'])
def searchtable():
    data = request.json
    id = data.get('id', 0)
    tabledef = {
        'id': id,
        'pagination': 'true'
    }
    _, colls, attrs = search_collections(data)
    columns = [{
        'field': 'collection',
        'title': 'Collection'
    }]
    # We need different collection links depending on the data['format'] parameter
    dataformat = data.get('format', TableFormat.html)
    if dataformat == TableFormat.html:
        tabledata = [{ 'collection': datafield("collection", c, 'irods_collection').htmlstring } for c in colls ]
    elif dataformat == TableFormat.plain:
        tabledata = [{ 'collection': c } for c in colls ]
    tabledef |= {'columns': columns, 'data': tabledata, 'attrs': attrs}
    return jsonify(tabledef), 200

@bp.route('_search')
def search():
    """This just fills the search modal"""
    return render_template('search2.html')

@bp.route('_x32', methods=['POST'])
def api_available_attrs():
    """Get available attributes depending on search result

    Returns:
        list: attr names
    """
    data = request.json
    keywords = data.get(Const.KEYWORDS)
    meta = data.get(Const.META)
    # Handle the case where there is no query yet
    if not(meta or keywords):
        return jsonify(all_collection_meta_attrs())
    _, _, attrs = search_collections(data)
    return jsonify(attrs)

@bp.route('_searchcolls', methods=['GET'])
def api_searchcolls_kw():
    keywords = request.args.get(Const.KEYWORDS, '').split(' ')
    id = request.args.get(Const.ID, 0)
    _, colls, attrs = search_collections(search_dict(keywords, {}))
    return jsonify(result_data(colls, [], id, attrs=attrs))

@bp.route('_attrvalues', methods=['GET'])
def api_attrvalues():
    attr = request.args.get('attr')
    if attr is not None:
        return jsonify(dataset_attr_values(attr))
    return jsonify([])

@bp.route('_attrvalues', methods=['POST'])
def api_attrvalues_for_search():
    data = request.json
    attr = data.get('attr')
    ids, colls, attrs = search_collections(data)
    if ids:
        XX = search_values_by_collection_ids_and_attr(ids, attr)
        return jsonify(XX)
    else:
        XX = dataset_attr_values(attr)
        return jsonify(XX)


def search_collections(data):
    ids = None
    all_colls = {}
    # Find keywords in collection paths
    for keyword in data.get(Const.KEYWORDS, []):
        if keyword:
            colls = search_collections_by_keyword(keyword)
            all_colls = all_colls | colls
            if ids is None:
                ids = set(colls)
            else:
                ids = ids & set(colls)
    # Find metadata
    for attr, value in data.get(Const.META, {}).items():
        colls = collections_by_meta(attr, value)
        all_colls = all_colls | colls
        if ids is None:
            ids = set(colls)
        else:
            ids = ids & set(colls)
    if ids is None:
        ids = []
        collections = []
        attrs = all_collection_meta_attrs()
    else:
        collections = [ all_colls.get(id) for id in ids ]
        attrs = [ a for a in search_attrs_by_collection_ids(list(ids)) if a not in data.get(Const.META, {}).keys() ]
    return list(ids), list(collections), list(attrs)

def search_attrs_by_collection_ids(ids):
    return sorted(list(_search_attrs_by_sorted_collection_ids(sorted(ids[:1000]))))

@cache.memoize(timeout=3600, make_name=dep_zone)
def _search_attrs_by_sorted_collection_ids(ids):
    '''
    Search unique attribute_names for a selected list of collections
    '''
    CHUNK_SIZE = 50
    if len(ids) > CHUNK_SIZE:
        splitpoint = len(ids) // 2
        result = _search_attrs_by_sorted_collection_ids(ids[:splitpoint])
        result.update(_search_attrs_by_sorted_collection_ids(ids[splitpoint:]))
        return result
    with irods_manager.session(current_user) as session:
        result = set()
        for i in range(0, len(ids), CHUNK_SIZE):
            sql = f"""
select meta_attr_name from { Tables.meta } M
inner join { Tables.metamap } OM on M.meta_id=OM.meta_id
where OM.object_id IN({','.join(ids[i:i+CHUNK_SIZE])}) and meta_attr_name not like 'sys%';
"""
            result.update({ c[0] for c in runsql(session, sql) })
    return result

def search_values_by_collection_ids_and_attr(ids, attr):
    return sorted(list(_search_values_by_sorted_collection_ids_and_attr(sorted(ids), attr)))

@cache.memoize(timeout=3600, make_name=dep_zone)
def _search_values_by_sorted_collection_ids_and_attr(ids, attr):
    '''
    Select metadata values for a specific attribute and a selected list of collections
    '''
    CHUNK_SIZE = 50
    if len(ids) > CHUNK_SIZE:
        splitpoint = len(ids) // 2
        result = _search_values_by_sorted_collection_ids_and_attr(ids[:splitpoint], attr)
        result.update(_search_values_by_sorted_collection_ids_and_attr(ids[splitpoint:], attr))
        return result
    with irods_manager.session(current_user) as session:
        result = set()
        for i in range(0, len(ids), CHUNK_SIZE):
            sql = f"""
select meta_attr_value from { Tables.meta } M
inner join {Tables.metamap } OM on M.meta_id=OM.meta_id
WHERE M.meta_attr_name = '{attr}' AND
OM.object_id IN ({','.join(ids[i:i+CHUNK_SIZE])});
"""
            result.update({ c[0] for c in runsql(session, sql) })
    return result


@cache.memoize(timeout=3600, make_name=dep_zone)
def search_collections_by_keyword(keyword):
    colls = datasets_with_text(keyword)
    # colls = colls.union(set(all_datasets_meta(keyword, Const.NAME)))
    # colls = colls.union(set(all_datasets_meta(keyword, Const.VALUE)))
    return colls



########################
# CACHED BASE FUNCTIONS
########################

def runsql(session, sql):
    alias = f'ngsweb_search_{time.time()}'
    query = SpecificQuery(session, sql, alias)
    # try:
    #     query.remove()
    # except:
    #     pass
    query.register()
    try:
        result = list(query)
    except (CAT_NO_ROWS_FOUND, CAT_SQL_ERR):
        result = []
    query.remove()
    return result

@cache.memoize(timeout=3600, make_name=dep_zone)
def collections_by_meta(attr, value):
    with irods_manager.session(current_user) as session:
        sql = f"""
select coll_id, coll_name from { Tables.coll } C
inner join { Tables.metamap } OM on C.coll_id=OM.object_id
inner join { Tables.meta } M on OM.meta_id = M.meta_id
where meta_attr_name='{attr}' and meta_attr_value='{value}';
"""
        result = { c[0]: c[1] for c in runsql(session, sql) }
    return result

@cache.memoize(timeout=3600, make_name=dep_zone)
def datasets_with_text(text):
    if len(text) > 3:
        subresults = datasets_with_text(text[:-1])
        results = { k: v for k, v in subresults.items() if text in v }
    else:
        results = _datasets_with_text(text)
    return results

@cache.memoize(timeout=3600, make_name=dep_zone)
def _datasets_with_text(text):
    with irods_manager.session(current_user) as session:

        sql = f"""
select coll_id, coll_name from { Tables.coll } C
inner join { Tables.metamap } M on C.coll_id = M.object_id
inner join { Tables.meta } E on M.meta_id = E.meta_id
where meta_attr_name = 'sys::dataset_id' and coll_name like '%{text}%';
"""
        result = { c[0]: c[1] for c in runsql(session, sql) }
    return result


@cache.memoize(timeout=3600, make_name=dep_zone)
def _datasets_by_text_with_meta(text):
    with irods_manager.session(current_user) as session:

        sql = f"""
select coll_id, coll_name, meta_attr_name, meta_attr_value
from
(select coll_id, coll_name from { Tables.coll } C
inner join { Tables.metamap } M on C.coll_id = M.object_id
inner join { Tables.meta } E on M.meta_id = E.meta_id
where meta_attr_name = 'sys::dataset_id' and coll_name like '%{text}%'
) selected_datasets
inner join { Tables.metamap } M2 on selected_datasets.coll_id = M2.object_id
inner join { Tables.meta } E2 on M2.meta_id = E2.meta_id;
"""
        results = {}
        for c in runsql(session, sql):
            results.setdefault(c[1], {})[c[2]] = c[3]
    return results


@cache.memoize(timeout=3600, make_name=dep_zone)
def all_datasets_meta(meta, key):
    columns = {
        Const.NAME: 'meta_attr_name',
        Const.VALUE: 'meta_attr_value'
    }
    column = columns.get(key)
    with irods_manager.session(current_user) as session:
        sql = f"""
select coll_id, coll_name from (select coll_id, coll_name from { Tables.coll } C
inner join { Tables.metamap } M on C.coll_id = M.object_id
inner join { Tables.meta } E on M.meta_id = E.meta_id where meta_attr_name = 'sys::dataset_id') datasets
inner join { Tables.metamap } M on datasets.coll_id = M.object_id
where M.meta_id in
(SELECT meta_id FROM { Tables.meta } where {column} like '%{meta}%');
"""
        result = { c[0]: c[1] for c in runsql(session, sql) }
    return result

@cache.memoize(timeout=600, make_name=dep_zone)
@bp.route('_allmeta')
def all_meta_attrs():
    with irods_manager.session(current_user) as session:
        sql = f"select distinct meta_attr_name from { Tables.meta } where meta_attr_name not like 'sys%';"
        result = [ x[0] for x in runsql(session, sql) ]
    return result

@cache.memoize(timeout=600, make_name=dep_zone)
@bp.route('_allmeta')
def all_collection_meta_attrs():
    with irods_manager.session(current_user) as session:
        sql = f"""
select distinct meta_attr_name from { Tables.meta } M
inner join { Tables.metamap } O on M.meta_id=O.meta_id
inner join (select coll_id from { Tables.coll } C
inner join { Tables.metamap } M on C.coll_id = M.object_id
inner join { Tables.meta } E on M.meta_id = E.meta_id
where meta_attr_name = 'sys::dataset_id') C on O.object_id=C.coll_id
where meta_attr_name not like 'sys%'
order by meta_attr_name;
"""
        result = [ x[0] for x in runsql(session, sql) ]
    return result

@cache.memoize(timeout=3600, make_name=dep_zone)
def dataset_attr_values(attr):
    with irods_manager.session(current_user) as session:
        sql = f"""
select distinct meta_attr_value from { Tables.meta } EE inner join { Tables.metamap } MM on EE.meta_id = MM.meta_id inner join (select coll_id from { Tables.coll } C
inner join { Tables.metamap } M on C.coll_id = M.object_id
inner join { Tables.meta } E on M.meta_id = E.meta_id
where meta_attr_name = 'sys::dataset_id') subq on MM.object_id=subq.coll_id where meta_attr_name='{attr}';
"""
        result = [ x[0] for x in runsql(session, sql)]
    return result
