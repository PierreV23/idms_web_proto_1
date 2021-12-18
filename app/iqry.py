import random
import sys
import time
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject, DataObjectMeta, User, UserMeta
from irods.meta import iRODSMeta
from irods.column import Criterion

from . import flaskcache
from . import stats


@login_required
@flaskcache.cache.memoize(timeout=600)
def qusermeta(user):
    print('QUSER')
    q = current_user.irods_session.query(UserMeta.name,
                                         UserMeta.value, UserMeta.units).filter(
        Criterion('=', User.name, user))
    return [r for r in q]

@login_required
def qusermetadict(user):
    q = qusermeta(user)
    return {r[UserMeta.name]: r[UserMeta.value] for r in q}

def qusermetaval(user, attr, default=None):
    m = qusermetadict(user)
    return m.get(attr, default)

def susermetaval(user, attr, value, unit=None):
    u = current_user.irods_session.users.get(user)
    u.metadata[attr] = iRODSMeta(attr, value, unit)
    flaskcache.cache.delete_memoized(qusermeta)

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


@login_required
@flaskcache.cache.memoize(timeout=86400, response_filter=lambda arg: bool(arg))
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


@flaskcache.cache.memoize(timeout=86400, response_filter=lambda arg: bool(arg))
def qcollmetavalstatic(collection, attr, default=None):
    m = qcollmetadict(collection)
    return m.get(attr, default)
