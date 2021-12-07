import random
import sys
import time
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject, DataObjectMeta
from irods.column import Criterion

from . import flaskcache
from . import stats


@login_required
@flaskcache.cache.memoize(timeout=60)
def qcollmeta(collection):
    q = current_user.irods_session.query(CollectionMeta.name,
                                         CollectionMeta.value, CollectionMeta.units).filter(
        Criterion('=', Collection.name, collection))
    return [r for r in q]


@login_required
def qcollmetadict(collection):
    q = qcollmeta(collection)
    return {r[CollectionMeta.name]: r[CollectionMeta.value] for r in q}


@login_required
@flaskcache.cache.memoize(timeout=300)
def qcollchildren(collection):
    query = current_user.irods_session.query(Collection).filter(
        Criterion('=', Collection.parent_name, collection))
    return [r for r in query]


@login_required
@flaskcache.cache.memoize(timeout=120)
def qcolldataobjects(collection):
    query = current_user.irods_session.query(DataObject.name, DataObject.owner_name, DataObject.size).min(
        DataObject.create_time).filter(
        Criterion('=', Collection.name, collection))
    return [r for r in query]


@login_required
@flaskcache.cache.memoize(timeout=120)
def qcollbymeta(attr, value):
    query = current_user.irods_session.query(Collection).filter(
        Criterion('=', CollectionMeta.name, attr)).filter(
        Criterion('=', CollectionMeta.value, value))
    return [r for r in query]


def no_empty(arg):
    return bool(arg)


@login_required
@flaskcache.cache.memoize(timeout=86400, response_filter=no_empty)
def qcollbystaticmeta(attr, value):
    query = current_user.irods_session.query(Collection).filter(
        Criterion('=', CollectionMeta.name, attr)).filter(
        Criterion('=', CollectionMeta.value, value))
    return [r for r in query]


@login_required
def qcollmetavals(collection, attr):
    q = qcollmeta(collection)
    return [r for r in q if r[CollectionMeta.name] == attr]


@login_required
def qcollmetaval(collection, attr, default=None):
    m = qcollmetadict(collection)
    return m.get(attr, default)


@flaskcache.cache.memoize(timeout=86400, response_filter=no_empty)
def qcollmetavalstatic(collection, attr, default=None):
    m = qcollmetadict(collection)
    return m.get(attr, default)
