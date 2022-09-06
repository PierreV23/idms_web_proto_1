from irods.models import Collection, DataObject

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