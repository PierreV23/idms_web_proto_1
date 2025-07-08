import sys
import os
import time
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject, DataObjectMeta, User, UserMeta, Resource, ResourceMeta
from irods.meta import iRODSMeta, AVUOperation
from irods.column import Criterion
from irods.exception import CAT_NO_ACCESS_PERMISSION, CollectionDoesNotExist, DataObjectDoesNotExist

from . import flaskcache
from app.irodssessions import irods_manager


def invalidate(collection):
    flaskcache.cache.delete_memoized(qcollmeta, collection=collection)
    flaskcache.cache.delete_memoized(qcollchildren, collection=collection)
    flaskcache.cache.delete_memoized(qcolldataobjects, collection=collection)

@flaskcache.cache.memoize(timeout=600, make_name=flaskcache.dep_zone)
def qusermeta(user):
    with irods_manager.session() as session:
        q = session.query(UserMeta.name, UserMeta.value, UserMeta.units).filter(
            Criterion('=', User.name, user))
        result = [r for r in q]
    return result

def qusermetadict(user):
    q = qusermeta(user)
    return {r[UserMeta.name]: r[UserMeta.value] for r in q}

def qusermetaval(user, attr, default=None):
    m = qusermetadict(user)
    return m.get(attr, default)

def susermetaval(user, attr, value, unit=None):
    with irods_manager.session() as session:
        u = session.users.get(user)
        u.metadata[attr] = iRODSMeta(attr, value, unit)
    flaskcache.cache.delete_memoized(qusermeta)

@flaskcache.cache.memoize(timeout=300, make_name=flaskcache.dep_zone)
def qresmeta(resource):
    with irods_manager.session() as session:
        q = session.query(ResourceMeta.name, ResourceMeta.value, ResourceMeta.units).filter(
            Criterion('=', Resource.name, resource))
        result = [r for r in q]
    return result

def qresmetadict(resource):
    q = qresmeta(resource)
    return {r[ResourceMeta.name]: r[ResourceMeta.value] for r in q}

@flaskcache.cache.memoize(timeout=60, make_name=flaskcache.dep_zone)
def qcollmeta(collection):
    with irods_manager.session() as session:
        q = session.query(CollectionMeta.name, CollectionMeta.value, CollectionMeta.units).filter(
            Criterion('=', Collection.name, collection))
        result = [r for r in q]
    return result

def scollmetaval(coll, attr, value, unit=None):
    if value == '':
        raise ValueError( 'Empty-string not allowed as value of AVU!')
    if qcollmetaval(coll, attr) == value:
        return
    with irods_manager.session() as session:
        u = session.collections.get(coll)
        old_avus = [ m for m in u.metadata.items() if m.name == attr ]
        new_avu = iRODSMeta(attr, value, unit)

        # The atomic metadata operations are preferred, but require a higher permission level
        try:
            u.metadata.apply_atomic_operations(
                *[AVUOperation(operation='remove', avu=i) for i in old_avus],
                AVUOperation(operation='add', avu=new_avu)
            )
        except CAT_NO_ACCESS_PERMISSION:
            for oa in old_avus:
                u.metadata.remove(oa)
            u.metadata[attr] = new_avu

    flaskcache.cache.delete_memoized(qcollmeta, coll)

def addcollmetaval(coll, attr, value, unit=None):
    if qcollmetaval(coll, attr) == value:
        return
    with irods_manager.session() as session:
        u = session.collections.get(coll)
        new_avu = iRODSMeta(attr, value, unit)
        u.metadata.add(new_avu)
    flaskcache.cache.delete_memoized(qcollmeta, coll)

def rmallcollmetaattr(coll, attr):
    with irods_manager.session() as session:
        u = session.collections.get(coll)
        u.metadata._delete_all_values(attr)
    flaskcache.cache.delete_memoized(qcollmeta, coll)

def delcollmeta(coll, attr, value=None, unit=None):
    q = qcollmeta(coll)
    with irods_manager.session() as session:
        u = session.collections.get(coll)
        for m in q:
            if m[CollectionMeta.name] == attr:
                if value is None or m[CollectionMeta.value] == value:
                    if unit is None or m[CollectionMeta.units] == unit:
                        u.metadata.remove(m[CollectionMeta.name], m[CollectionMeta.value], m[CollectionMeta.units])
    flaskcache.cache.delete_memoized(qcollmeta, coll)

def restore_type( str_value, type_name=None ):
    if type_name:
        try:
            # https://stackoverflow.com/questions/11775460/lexical-cast-from-string-to-type
            #t = getattr(__builtins__, type_name)
            t = __builtins__[type_name]
            if not isinstance( t, type):
                raise ValueError( f"the unit: '{type_name}' is not a type!")
            value = t(str_value)
            return value
        except Exception as e:
            print( f"for value: {str_value} and type: {type_name} got Exception {e}" )
    return str_value


def qcollmetadict(collection):
    q = qcollmeta(collection)
    return {r[CollectionMeta.name]: r[CollectionMeta.value] for r in q}

def qcollmetadict_typed(collection):
    q = qcollmeta(collection)
    return {r[CollectionMeta.name]: restore_type(r[CollectionMeta.value], r[CollectionMeta.units]) for r in q}


@flaskcache.cache.memoize(timeout=300, make_name=flaskcache.dep_zone)
def qcollchildren(collection):
    with irods_manager.session() as session:
        q = session.query(Collection).filter(
            Criterion('=', Collection.parent_name, collection))
        result = [r for r in q]
    return result


@flaskcache.cache.memoize(timeout=120, make_name=flaskcache.dep_zone)
def qcolldataobjects(collection):
    with irods_manager.session() as session:
        q = session.query(DataObject.name, DataObject.owner_name, DataObject.size).min(
            DataObject.create_time).filter(
            Criterion('=', Collection.name, collection))
        result = [r for r in q]
    return result

@flaskcache.cache.memoize(timeout=120, make_name=flaskcache.dep_zone)
def qcollbymetaattr(attr):
    with irods_manager.session() as session:
        q = session.query(Collection).filter(
            Criterion('=', CollectionMeta.name, attr))
        result = [r for r in q]
    return result

@flaskcache.cache.memoize(timeout=120, make_name=flaskcache.dep_zone)
def qcollbymeta(attr, value):
    with irods_manager.session() as session:
        q = session.query(Collection).filter(
            Criterion('=', CollectionMeta.name, attr)).filter(
            Criterion('=', CollectionMeta.value, value))
        result = [r for r in q]
    return result


@flaskcache.cache.memoize(timeout=86400, make_name=flaskcache.dep_zone, response_filter=lambda arg: bool(arg))
def qcollbystaticmeta(attr, value):
    with irods_manager.session() as session:
        q = session.query(Collection).filter(
            Criterion('=', CollectionMeta.name, attr)).filter(
            Criterion('=', CollectionMeta.value, value))
        result = [r for r in q]
    return result


def qcollmetavals(collection, attr):
    q = qcollmeta(collection)
    return [r for r in q if r[CollectionMeta.name] == attr]


def qcollmetavals_with_placeholder(collection, attr, placeholder='[0]'):
    result = []
    q = qcollmeta(collection)
    attr_parts = attr.split(placeholder)
    #fallback in case there is no placeholder
    if len(attr_parts) == 1:
        return qcollmetavals(collection, attr)
    for i in range(1000):
        concrete_attr = f"{attr_parts[0]}{i}{attr_parts[1]}"
        matches = [r for r in q if r[CollectionMeta.name] == concrete_attr]
        result += matches
        if len(matches) == 0:
            return result
    return result


def qcollmetaval(collection, attr, default=None):
    m = qcollmetadict(collection)
    return m.get(attr, default)


@flaskcache.cache.memoize(timeout=86400, make_name=flaskcache.dep_zone, response_filter=lambda arg: bool(arg))
def qcollmetavalstatic(collection, attr, default=None):
    m = qcollmetadict(collection)
    return m.get(attr, default)

@flaskcache.cache.memoize(timeout=86400, make_name=flaskcache.dep_zone)
def qcollproperty(collection, property):
    with irods_manager.session() as session:
        c = session.collections.get(collection)
    return getattr(c, property)

@flaskcache.cache.memoize(timeout=60, make_name=flaskcache.dep_zone)
def qdataobjmeta(dataobject):
    with irods_manager.session() as session:
        # split in dataobject_name and collection
        coll, dataobject_name = os.path.split(dataobject)
        q = session.query(DataObjectMeta.name, DataObjectMeta.value, DataObjectMeta.units).filter(
            Criterion('=', DataObject.name, dataobject_name)).filter(
            Criterion('=', Collection.name, coll))
        result = [r for r in q]
    return result

@flaskcache.cache.memoize(timeout=120, make_name=flaskcache.dep_zone)
def qdataobjbymeta(attr, value):
    with irods_manager.session() as session:
        q = session.query(Collection.name, DataObject.name).filter(
            Criterion('=', DataObjectMeta.name, attr)).filter(
            Criterion('=', DataObjectMeta.value, value))
        result = [r for r in q]
    return result

@flaskcache.cache.memoize(timeout=120, make_name=flaskcache.dep_zone)
def qcolldataobjectpaths(collection):
    '''
    Query to fetch dataobject names for a collection.
    Returns paths of data objects in a given collection'''
    with irods_manager.session() as session:
        q = session.query(Collection.name, DataObject.name).min(
            DataObject.create_time).filter(
            Criterion('=', Collection.name, collection))
        dataobject_paths = [list(d.values())[0] + '/' + list(d.values())[1] for d in q]
    return dataobject_paths

def qpathobjecttype(path):
    '''
    Check whether an iRODS path is a collection or a data_object
    
    params:
        path to be checked
    return:
        'path', 'dataobject' or 'not_found'
    '''
    with irods_manager.session() as session:
        try:
            # Try to get it as a DataObject
            obj = session.data_objects.get(path)
            return 'dataobject'
        except DataObjectDoesNotExist:
            pass

        try:
            # Try to get it as a Collection
            coll = session.collections.get(path)
            return 'path'
        except CollectionDoesNotExist:
            pass

    return 'not_found'