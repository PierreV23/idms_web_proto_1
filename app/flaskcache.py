
from flask import request
from flask_caching import Cache
from flask_login import current_user

cache = Cache()

def init(app):
    global cache
    cache.init_app(app)

def dep_zone(funcname):
    if hasattr(current_user, 'irods_zone'):
        return f'{current_user.irods_zone}{funcname}'
    else:
        return funcname

def dep_userzone(funcname):
    return f'{current_user.username}{current_user.irods_zone}{funcname}'

def key_zone():
    return f'{current_user.irods_zone}{request.full_path}'

def key_userzone():
    return f'{current_user.username}{current_user.irods_zone}{request.full_path}'

# These two functions can be used to push and pop a flag on to the cache
def push_cache(flag, value=True):
    cache.set(f'{current_user.irods_zone}{current_user.username}{flag}', value)

def pop_cache(flag):
    key = f'{current_user.irods_zone}{current_user.username}{flag}'
    value = cache.get(key)
    cache.delete(key)
    return value

def cache_report(prefix=''):
    print('############### CACHE #######################')
    k_prefix = cache.cache.key_prefix
    keys = cache.cache._write_client.keys(k_prefix + '*')
    keys = [k.decode('utf8') for k in keys]
    keys = [k.replace(k_prefix, '') for k in keys]
    values = cache.get_many(*keys)
    for key in keys:
        if key.startswith(prefix):
            print(f'{key:30} -> {str(cache.get(key))}' )