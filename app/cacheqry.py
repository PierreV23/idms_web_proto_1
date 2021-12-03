import random
from flask_login import current_user, login_required
from irods.models import Collection, CollectionMeta, DataObject, DataObjectMeta
from irods.column import Criterion

from . import flaskcache
from . import stats

@login_required
@stats.stats
@flaskcache.cache.memoize(timeout=60)
@stats.stats2
def qcollmeta(collection):
    query = current_user.irods_session.query(CollectionMeta.name, CollectionMeta.value,
                CollectionMeta.units).filter(
                Criterion('=', Collection.name, collection))
    return [ r for r in query ]

@login_required
@stats.stats
@flaskcache.cache.memoize(timeout=60)
@stats.stats2
def qcollmetadict(collection):
    query = current_user.irods_session.query(CollectionMeta.name, CollectionMeta.value,
                CollectionMeta.units).filter(
                Criterion('=', Collection.name, collection))
    return { r[CollectionMeta.name]: r[CollectionMeta.value] for r in query }

# @login_required
# @stats.stats
# @flaskcache.cache.memoize(timeout=60)
# @stats.stats2
# def qcollidmetadict(collectionid):
#     query = current_user.irods_session.query(CollectionMeta.name, CollectionMeta.value,
#                 CollectionMeta.units).filter(
#                 Criterion('=', Collection.id, collectionid))
#     return { r[CollectionMeta.name]: r[CollectionMeta.value] for r in query }

@login_required
@stats.stats
@flaskcache.cache.memoize(timeout=120)
@stats.stats2
def qcollchildren(collection):
    query = current_user.irods_session.query(Collection.name).filter(
        Criterion('=', Collection.parent_name, collection))
    return [ r for r in query ]

@login_required
@stats.stats
@flaskcache.cache.memoize(timeout=120)
@stats.stats2
def qcollbymeta(attr, value):
    query = current_user.irods_session.query(Collection.name).filter(
                Criterion('=', CollectionMeta.name, attr)).filter(
                    Criterion('=', CollectionMeta.value, value))
    return [ r for r in query ]

# @login_required
# @stats.stats
# @flaskcache.cache.memoize(timeout=3600)
# @stats.stats2
# def qcollidfromname(collection):
#     query = current_user.irods_session.query(Collection.id).filter(
#                 Criterion('=', Collection.name, collection))
#     r = query.execute()
#     if r:
#         return r[0][Collection.id]
#     else:
#         return None    

# @login_required
# @stats.stats
# @flaskcache.cache.memoize(timeout=60)
# @stats.stats2
# def qcollidmetavals(collectionid, attr):
#     query = current_user.irods_session.query(CollectionMeta.value).filter(
#                 Criterion('=', Collection.id, collectionid)).filter(
#                 Criterion('=', CollectionMeta.name, attr))
#     return [ r for r in query ]

@login_required
@stats.stats
@flaskcache.cache.memoize(timeout=60)
@stats.stats2
def qcollmetavals(collection, attr):
    q = qcollmeta(collection)
    return [ r for r in q if r[CollectionMeta.name] == attr ]

@login_required
@stats.stats
@flaskcache.cache.memoize(timeout=60)
@stats.stats2
def qcollmetaval(collection, attr, default=None):
    m = qcollmetadict(collection)
    return m.get(attr, default)


