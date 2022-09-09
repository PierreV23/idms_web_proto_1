from irods.models import Collection, DataObject

ATTR_TIERING_GROUP = 'sys::tiering::group'
ATTR_RESOURCE_PREFIX = 'sys::resource::'
ATTR_RESOURCE_ENABLED = 'sys::resource::enabled'
ATTR_RESOURCE_AVAILABLE = 'sys::resource::available'
ATTR_RESOURCE_TAR = 'sys::resource::tar'
ATTR_RESOURCE_ONLINE = 'sys::resource::online'

COLL_KEY_MAP = {
    'name': Collection.name,
    'create_time': Collection.create_time,
    'size': Collection.name, # Collections do not have a size property
    'owner_name': Collection.owner_name
}

DATA_KEY_MAP = {
    'name': DataObject.name,
    'create_time': DataObject.create_time,
    'size': DataObject.size,
    'owner_name': DataObject.owner_name
}