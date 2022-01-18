

JOB_FIELDS = {
    'sys::runsheet::id': ('Name', 'runsheet', 'name', 'true', None),
    'sys::runsheet::state': ('State', 'text', 'state', 'true', 'select'),
    'sys::runsheet::description': ('Description', 'text', 'description', 'true', 'input'),
    'sys::runsheet::processgroupid': ('GroupInstance', 'processgroupid', 'processgroupid', 'false', None),
    'sys::run::start_time': ('Start time', 'timestamp', 'start_time', 'true', None),
    'sys::run::finish_time': ('End time', 'timestamp', 'finish_time', 'true', None),
    'sys::runsheet::projectID': ('projectID', 'projectid', 'projectid', 'true', 'select'),
    'sys::run::exit_code': ('Result', 'int', 'exit_code', 'true', 'select'),
    'sys::runsheet::input_collection': ('Input Collection', 'irods_collection', 'input_collection', 'true', None),
}

PG_FIELDS = {
    'pgid': ('PG Instance ID', 'processgroupid', 'pgid', 'true', None),
    'input_collection': ('Input Collection', 'irods_collection', 'input_collection', 'true', None),
    'project': ('Project', 'projectid', 'projectid', 'true', 'select'),
    'process_count': ('Processes', 'int', 'process_count', 'true', None),
    'state': ('State', 'text', 'state', 'true', None),
    'start': ('Start Time', 'timestamp', 'pgstart', 'true', None),
    'finish': ('End Time', 'timestamp', 'pgfinish', 'true', None)
}