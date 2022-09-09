import random
import sys
import time
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject, DataObjectMeta, User, UserMeta, Resource, ResourceMeta
from irods.meta import iRODSMeta
from irods.column import Criterion

from . import flaskcache
from app.irodssessions import irods_manager

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
    with irods_manager.session() as session:
        u = session.collections.get(coll)
        u.metadata[attr] = iRODSMeta(attr, value, unit)
    flaskcache.cache.delete_memoized(qcollmeta, coll)

def rmallcollmetaattr(coll, attr):
    with irods_manager.session():
        u = session.collections.get(coll)
        u.metadata._delete_all_values(attr)
    flaskcache.cache.delete_memoized(qcollmeta, coll)

def qcollmetadict(collection):
    q = qcollmeta(collection)
    return {r[CollectionMeta.name]: r[CollectionMeta.value] for r in q}


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


def qcollmetaval(collection, attr, default=None):
    m = qcollmetadict(collection)
    return m.get(attr, default)


@flaskcache.cache.memoize(timeout=86400, make_name=flaskcache.dep_zone, response_filter=lambda arg: bool(arg))
def qcollmetavalstatic(collection, attr, default=None):
    m = qcollmetadict(collection)
    return m.get(attr, default)
