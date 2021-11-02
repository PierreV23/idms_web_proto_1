#
##

def getmetaitem(irods_obj, attr, default=None): 
    try:
        value = irods_obj.metadata.get_one(attr).value
    except KeyError:
        value = default
    return value