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

# Constansts that define the JOB VIEW

JOB_PAGE_SIZE = 25

JOB_FIELDS = {
    'sys::runsheet::description': ('Description', 'text'),
    'sys::runsheet::processgroupid': ('GroupInstance', 'processgroupid'),
    'sys::run::start_time': ('Start time', 'timestamp'),
    'sys::run::finish_time': ('End time', 'timestamp'),
    'sys::runsheet::projectID': ('projectID', 'projectid'),
    'user::run::exit_code': ('Result', 'int'),
    'sys::runsheet::input_collection': ('Input Collection', 'irods_collection')
}

# Constants for graphic layout, shapes and colors

SHAPE1 = 'shape1'
SHAPE2 = 'shape2'
COLOR1 = 'color1'
COLOR2 = 'color2'
TABLECLASS = 'tableclass'

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
    'queued': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#bdbdbd',
        COLOR2: '#bdbdbd',
        TABLECLASS : 'table-queued'    
    },
    'startup': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#bee5eb',
        COLOR2: '#bee5eb',
        TABLECLASS : 'table-startup'    
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
    'done':  {
        SHAPE1 : 'box3d',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        TABLECLASS : 'table-done'
    },
    'notrun':  {
        SHAPE1 : 'box3d',
        SHAPE2 : 'cds',
        COLOR1: '#ebd9c6',
        COLOR2: '#ebd9c6',
        TABLECLASS : 'table-notrun'
    },
    'valid':  {
        SHAPE1: 'box3d',
        SHAPE2: 'cds',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        TABLECLASS : 'table-done'
    },
    'distributed': {
        SHAPE1 : 'box3d',
        COLOR1: '#c3e6cb:gray',
        COLOR2: '#c3e6cb',
        TABLECLASS : 'table-white'
    },
    'imported': {
        SHAPE1: 'cylinder',
        COLOR1: 'skyblue1',
        COLOR2: '#87CEFF',
        TABLECLASS : 'table-white'       
    },
    'temporary': {
        SHAPE1 : 'note',
        COLOR1: 'gold2',
        COLOR2: '#EEC900',
        TABLECLASS : 'table-white'  
    },
    'error': {
        SHAPE1: 'box3d',
        SHAPE2: 'cds',
        COLOR1: '#f5c6cb',
        COLOR2: '#f5c6cb',
        TABLECLASS : 'table-error'  
    },
    'invalid': {
        SHAPE1: 'box3d',
        SHAPE2: 'cds',
        COLOR1: '#f5c6cb',
        COLOR2: '#f5c6cb',
        TABLECLASS : 'table-error'  
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
        TABLECLASS : 'table-tomato'
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
    }  
}

COLL_SHAPES = {
    'unknown':    ('cds', 'white'),
    'error':   ('cds', 'orange'),
    'done':  ('cds',  'darkolivegreen1'),
    'notrun' : ('cds', 'gray91')}

COLL_SHAPES = {
    'valid':      ('box3d', 'springgreen1'),
    'invalid':    ('box3d', 'tomato'),
    'imported':   ('cylinder', 'skyblue1'),
    'temporary':  ('note',  'gold2'),
    'distributed':('box3d','springgreen1:gray'),
    'unknown'    :('ellipse', 'gray'),
}