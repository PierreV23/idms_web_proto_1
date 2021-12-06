
from flask import request
from flask_caching import Cache
from flask_login import current_user

cache = Cache()

def init(app):
    global cache
    cache.init_app(app)

def makename(funcname):
    return f'{current_user.irods_zone}{funcname}'

def makekey():
    return f'{current_user.irods_zone}{request.full_path}'


def cache_report(prefix=''):
    print('############### CACCHE #######################')
    k_prefix = cache.cache.key_prefix
    keys = cache.cache._write_client.keys(k_prefix + '*')
    keys = [k.decode('utf8') for k in keys]
    keys = [k.replace(k_prefix, '') for k in keys]
    values = cache.get_many(*keys)
    for key in keys:
        if key.startswith(prefix):
            print(f'{key:30} -> {str(cache.get(key))}' )