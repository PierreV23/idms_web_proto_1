#
##
import uuid
from . import iqry
from instance.constants import ATTR_DATASETID

def getmetaitem(irods_obj, attr, default=None): 
    try:
        value = irods_obj.metadata.get_one(attr).value
    except KeyError:
        value = default
    return value

def get_or_set_uid(collection):
    """If the referred collection has no dataset_id, generate one
    Return the dataset_id
    """
    uid = iqry.qcollmetaval(collection, ATTR_DATASETID)
    if not uid:
        uid = str(uuid.uuid4())
        iqry.scollmetaval(collection, ATTR_DATASETID, uid)
    return uid