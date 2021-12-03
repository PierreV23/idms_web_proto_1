from flask_caching import Cache

cache = Cache()

def init(app):
    global cache
    cache.init_app(app)

def cache_report():
    print('############### CACCHE #######################')
    k_prefix = cache.cache.key_prefix
    keys = cache.cache._write_client.keys(k_prefix + '*')
    keys = [k.decode('utf8') for k in keys]
    keys = [k.replace(k_prefix, '') for k in keys]
    values = cache.get_many(*keys)
    for key in keys:
        print(f'{key:25} -> {str(cache.get(key))[:50]}' )