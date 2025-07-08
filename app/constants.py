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
    'treeview': 'Use treeview in collection browser instead of project list',
    'swappanes': 'Show content pane on top, graph on bottom'
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
STYLE = 'style'

SYS_INVALID_COLOR = '#FF3333'
USER_INVALID_COLOR = "#B51C1C"

DEFAULT_SHAPE = {
        SHAPE1 : 'box',
        SHAPE2 : 'circle',
        COLOR1: 'white',
        COLOR2: '#FFFFFF',
        STYLE: 'filled',
        TABLECLASS : 'table-white'
}

LAYOUT = {
    'depends': {
        SHAPE1 : 'box',
        SHAPE2: 'cds',
        COLOR1: '#e0ebeb',
        COLOR2: '#e0ebeb',
        STYLE: 'filled',
        TABLECLASS : 'table-depends'
    },
    'incoming': {
        SHAPE1 : 'box3d',
        SHAPE2: 'cds',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        STYLE: 'filled',
        TABLECLASS : 'table-done'
    },
    'choose': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#bee5eb',
        COLOR2: '#bee5eb',
        STYLE: 'filled',
        TABLECLASS : 'table-choose'
    },
    'prepare': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#B0E0E6',
        COLOR2: '#B0E0E6',
        STYLE: 'filled',
        TABLECLASS : 'table-prepare'
    },
    'stage': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#B0C4DE',
        COLOR2: '#B0C4DE',
        STYLE: 'filled',
        TABLECLASS : 'table-stage'
    },
    'spacecheck': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#D4B3F5',
        COLOR2: '#D4B3F5',
        STYLE: 'filled',
        TABLECLASS : 'table-spacecheck'
    },
    'download': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#dcccde',
        COLOR2: '#dcccde',
        STYLE: 'filled',
        TABLECLASS : 'table-download'
    },
    'queued': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#bdbdbd',
        COLOR2: '#bdbdbd',
        STYLE: 'filled',
        TABLECLASS : 'table-queued'
    },
    'active': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#99caff',
        COLOR2: '#99caff',
        STYLE: 'filled',
        TABLECLASS : 'table-jobactive'
    },
    'finishing': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#33cccc',
        COLOR2: '#33cccc',
        STYLE: 'filled',
        TABLECLASS : 'table-finishing'
    },
    'postprocessing': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#99ffcc',
        COLOR2: '#99ffcc',
        STYLE: 'filled',
        TABLECLASS : 'table-postprocessing'
    },
    'notify': {
        SHAPE1 : 'underline',
        SHAPE2 : 'cds',
        COLOR1: '#c9d3cb',
        COLOR2: '#c9d3cb',
        STYLE: 'filled',
        TABLECLASS : 'table-notify'
    },
    'done':  {
        SHAPE1 : 'box3d',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        STYLE: 'filled',
        TABLECLASS : 'table-done'
    },
    'NOTRUN':  {
        SHAPE1 : 'box3d',
        SHAPE2 : 'cds',
        COLOR1: '#ebd9c6',
        COLOR2: '#ebd9c6',
        STYLE: 'filled',
        TABLECLASS : 'table-notrun'
    },
    'distributed': {
        SHAPE1 : 'box3d',
        COLOR1: '#c3e6cb:gray',
        COLOR2: '#c3e6cb',
        STYLE: 'filled',
        TABLECLASS : 'table-distributed'
    },
    'imported': {
        SHAPE1: 'cylinder',
        COLOR1: 'skyblue1',
        COLOR2: '#87CEFF',
        STYLE: 'filled',
        TABLECLASS : 'table-imported'
    },
    'temporary': {
        SHAPE1 : 'note',
        COLOR1: 'gold2',
        COLOR2: '#EEC900',
        STYLE: 'filled',
        TABLECLASS : 'table-temporary'
    },
    'error': {
        SHAPE1: 'box3d',
        SHAPE2: 'cds',
        COLOR1: '#ff9980',
        COLOR2: '#ff9980',
        STYLE: 'filled',
        TABLECLASS : 'table-error'
    },
    'unknown': {
        SHAPE1: 'box',
        SHAPE2: 'cds',
        COLOR1: '#ffffff',
        COLOR2: '#ffffff',
        STYLE: 'filled',
        TABLECLASS : 'table-white'
    },
    'OK': {
        SHAPE1: 'cds',
        SHAPE2: 'cds',
        COLOR1: 'palegreen2',
        COLOR2: '#90EE90',
        STYLE: 'filled',
        TABLECLASS : 'table-done'
    },
    'FAILED': {
        SHAPE1: 'cds',
        SHAPE2: 'cds',
        COLOR1: 'tomato',
        COLOR2: '#FF6347',
        STYLE: 'filled',
        TABLECLASS : 'table-error'
    },
    'source': {
        SHAPE1: 'box3d',
        SHAPE2: 'box3d',
        COLOR1: 'white',
        COLOR2: '#FFFFFF',
        STYLE: 'filled',
        TABLECLASS: 'table-white'
    },
    'qc_report': {
        SHAPE1: 'box3d',
        SHAPE2: 'box3d',
        COLOR1: 'yellow',
        COLOR2: '#FFFF00',
        STYLE: 'filled',
        TABLECLASS: 'table-white'
    },
    'refsamp_report': {
        SHAPE1: 'box3d',
        SHAPE2: 'box3d',
        COLOR1: 'yellow',
        COLOR2: '#FFFF00',
        STYLE: 'filled',
        TABLECLASS: 'table-white'
    },
    'data': {
        SHAPE1: 'box3d',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        STYLE: 'filled',
        TABLECLASS : 'table-data'
    },
    'uploaded': {
        SHAPE1: 'folder',
        SHAPE2: 'folder',
        COLOR1: 'skyblue1',
        COLOR2: '#87CEFF',
        STYLE: 'filled',
        TABLECLASS : 'table-data'
    },
    'invalid': {
        SHAPE1: 'cds',
        SHAPE2: 'cds',
        COLOR1: 'tomato',
        COLOR2: '#FF6347',
        STYLE: 'filled',
        TABLECLASS : 'table-error'
    },
    'reference_data': {
        SHAPE1: 'folder',
        COLOR1: '#fdaa48',
        STYLE: 'filled',
        COLOR2: '#fdaa48',
        TABLECLASS : 'table-data'
    },
    # shapes and colours like https://www.w3.org/TR/prov-o/diagrams/starting-points.svg
    'file': {
        SHAPE1: 'rect',
        SHAPE2: 'rect',
        COLOR1: "#fffedf",
        COLOR2: "#fffedf",
        STYLE: 'filled, rounded',
        TABLECLASS : 'table-data'
    },
    'collection': {
        SHAPE1: 'box3d',
        SHAPE2: 'cds',
        COLOR1: '#c3e6cb',
        COLOR2: '#c3e6cb',
        STYLE: 'filled',
        TABLECLASS : 'table-done'
    },    
    'database': {
        SHAPE1: 'cylinder',
        SHAPE2: 'cylinder',
        COLOR1: "#eb9494",
        COLOR2: "#eb9494",
        STYLE: 'filled',
        TABLECLASS : 'table-data'
    },
    'not_file': {
        SHAPE1: 'rect',
        SHAPE2: 'rect',
        COLOR1: "#ffffff",
        COLOR2: "#ffffff",
        STYLE: 'filled',
        TABLECLASS : 'table-data'
    },
    'entity': {
        SHAPE1: 'rect',
        SHAPE2: 'rect',
        COLOR1: "#fffedf",
        COLOR2: "#fffedf",
        STYLE: 'filled, rounded',
        TABLECLASS : 'table-data'
    },
    # activity acording to PROV should be a rectangle with double lines on the side, but for now we use cds.
    'activity': {
        SHAPE1: 'cds',
        SHAPE2: 'cds',
        COLOR1: "#cfceff",
        COLOR2: "#0460C3",
        STYLE: 'filled',
        TABLECLASS : 'table-data'
    },
    'process': {
        SHAPE1: 'cds',
        SHAPE2: 'cds',
        COLOR1: "#ffffff",
        COLOR2: "#003e80", # use for links
        STYLE: 'filled',
        TABLECLASS : 'table-data'
    },
    'agent': {
        SHAPE1: 'house',
        SHAPE2: 'house',
        COLOR1: "#ffebc4",
        COLOR2: "#ffebc4",
        STYLE: 'filled',
        TABLECLASS : 'table-data'
    },
    'xsd:datetime': {
        SHAPE1: 'rect',
        SHAPE2: 'rect',
        COLOR1: "#e6e6e6",
        COLOR2: "#e6e6e6",
        STYLE: 'filled',
        TABLECLASS : 'table-data'
    },
}
