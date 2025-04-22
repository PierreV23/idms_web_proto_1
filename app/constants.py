from irods.models import Collection, DataObject

ATTR_TIERING_GROUP = 'sys::tiering::group'
ATTR_RESOURCE_PREFIX = 'sys::resource::'
ATTR_RESOURCE_ENABLED = 'sys::resource::enabled'
ATTR_RESOURCE_AVAILABLE = 'sys::resource::available'
ATTR_RESOURCE_TAR = 'sys::resource::tar'
ATTR_RESOURCE_ONLINE = 'sys::resource::online'

FEATURES = {
    'actions': 'Show actions pane',
    'jobs': 'Show process configuration and job status page',
    'projects': 'Show project configuration pages',
    'provenance': 'Show and manage data provenance',
    'reference': 'Show reference data configuration',
    'sharing': 'Configure datasets that need to be shared externally',
    'minilims': 'Show ONT samplesheet configuration interface',
    'treeview': 'Use treeview in collection browser instead of project list'
}

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

# Constansts that define the JOB VIEW

JOB_PAGE_SIZE = 25

JOB_FIELDS = {
    'sys::runsheet::description': ('Description', 'text'),
    'sys::runsheet::processgroupid': ('GroupInstance', 'processgroupguid'),
    'sys::run::start_time': ('Start time', 'timestamp'),
    'sys::run::finish_time': ('End time', 'timestamp'),
    'sys::runsheet::projectID': ('projectID', 'projectid'),
    'sys::run::exit_code': ('Result', 'int'),
    'sys::runsheet::input_collection': ('Input Collection', 'irods_collection')
}

# Constants for graphic layout, shapes and colors

SHAPE1 = 'shape1'
SHAPE2 = 'shape2'
COLOR1 = 'color1'
COLOR2 = 'color2'
TABLECLASS = 'tableclass'

SYS_INVALID_COLOR = '#FF3333'
USER_INVALID_COLOR = 'darkred'

DEFAULT_SHAPE = {
        SHAPE1 : 'box',
        SHAPE2 : 'circle',
        COLOR1: 'white',
        COLOR2: '#FFFFFF',
        TABLECLASS : 'table-white'
}

LAYOUT = {
    'depends': {
        SHAPE1 : 'box',
        SHAPE2: 'cds',
        COLOR1: '#e0ebeb',
        COLOR2: '#e0ebeb',
        TABLECLASS : 'table-depends'        
    },
    'incoming': {
        SHAPE1 : 'box3d',
        SHAPE2: 'cds',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        TABLECLASS : 'table-done'        
    },
    'choose': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#bee5eb',
        COLOR2: '#bee5eb',
        TABLECLASS : 'table-choose'    
    },    
    'prepare': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#B0E0E6',
        COLOR2: '#B0E0E6',
        TABLECLASS : 'table-prepare'        
    },
    'stage': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#B0C4DE',
        COLOR2: '#B0C4DE',
        TABLECLASS : 'table-stage'    
    },
    'spacecheck': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#D4B3F5',
        COLOR2: '#D4B3F5',
        TABLECLASS : 'table-spacecheck'    
    },    
    'download': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#dcccde',
        COLOR2: '#dcccde',
        TABLECLASS : 'table-download'    
    },
    'queued': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#bdbdbd',
        COLOR2: '#bdbdbd',
        TABLECLASS : 'table-queued'    
    },
    'active': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#99caff',
        COLOR2: '#99caff',
        TABLECLASS : 'table-jobactive' 
    },
    'finishing': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#33cccc',
        COLOR2: '#33cccc',
        TABLECLASS : 'table-finishing' 
    },
    'postprocessing': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#99ffcc',
        COLOR2: '#99ffcc',
        TABLECLASS : 'table-postprocessing' 
    },
    'notify': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#c9d3cb',
        COLOR2: '#c9d3cb',
        TABLECLASS : 'table-notify' 
    },
    'done':  {
        SHAPE1 : 'box3d',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        TABLECLASS : 'table-done'
    },
    'NOTRUN':  {
        SHAPE1 : 'box3d',
        SHAPE2 : 'cds',
        COLOR1: '#ebd9c6',
        COLOR2: '#ebd9c6',
        TABLECLASS : 'table-notrun'
    },
    'distributed': {
        SHAPE1 : 'box3d',
        COLOR1: '#c3e6cb:gray',
        COLOR2: '#c3e6cb',
        TABLECLASS : 'table-distributed'
    },
    'imported': {
        SHAPE1: 'cylinder',
        COLOR1: 'skyblue1',
        COLOR2: '#87CEFF',
        TABLECLASS : 'table-imported'       
    },
    'temporary': {
        SHAPE1 : 'note',
        COLOR1: 'gold2',
        COLOR2: '#EEC900',
        TABLECLASS : 'table-temporary'  
    },
    'error': {
        SHAPE1: 'box3d',
        SHAPE2: 'cds',
        COLOR1: '#ff9980',
        COLOR2: '#ff9980',
        TABLECLASS : 'table-error'  
    },
    'unknown': {
        SHAPE1: 'box',
        SHAPE2: 'cds',
        COLOR1: '#ffffff',
        COLOR2: '#ffffff',
        TABLECLASS : 'table-white'  
    },
    'OK': {
        SHAPE1: 'cds',
        SHAPE2: 'cds',
        COLOR1: 'palegreen2',
        COLOR2: '#90EE90',
        TABLECLASS : 'table-done'
    },
    'FAILED': {
        SHAPE1: 'cds',
        SHAPE2: 'cds',
        COLOR1: 'tomato',
        COLOR2: '#FF6347',
        TABLECLASS : 'table-error'
    },
    'source': {
        SHAPE1: 'box3d',
        SHAPE2: 'box3d',
        COLOR1: 'white',
        COLOR2: '#FFFFFF',
        TABLECLASS: 'table-white'
    },
    'qc_report': {
        SHAPE1: 'box3d',
        SHAPE2: 'box3d',
        COLOR1: 'yellow',
        COLOR2: '#FFFF00',
        TABLECLASS: 'table-white'
    },
    'refsamp_report': {
        SHAPE1: 'box3d',
        SHAPE2: 'box3d',
        COLOR1: 'yellow',
        COLOR2: '#FFFF00',
        TABLECLASS: 'table-white'
    },
    'data': {
        SHAPE1: 'box3d',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        TABLECLASS : 'table-data'
    },
    'uploaded': {
        SHAPE1: 'folder',
        SHAPE2: 'folder',
        COLOR1: 'skyblue1',
        COLOR2: '#87CEFF',
        TABLECLASS : 'table-data'
    },
    'invalid': {
        SHAPE1: 'cds',
        SHAPE2: 'cds',
        COLOR1: 'tomato',
        COLOR2: '#FF6347',
        TABLECLASS : 'table-error'
    },
    'reference_data': {
        SHAPE1: 'folder',
        COLOR1: '#fdaa48',
        COLOR2: '#fdaa48',
        TABLECLASS : 'table-data'
    },
}
