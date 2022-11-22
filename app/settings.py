JOB_FIELDS = {
    'refresh_time': {'title': 'Last Refresh', 'format': 'timestamp', 'field': 'refresh_time', 'sortable': 'false', 'visible': 'true'},
    'sys::runsheet::id': {'title': 'Name', 'format': 'runsheet', 'field': 'id', 'sortable': 'true', 'visible': 'true'},
    'sys::runsheet::state': {'title': 'State', 'format': 'text', 'field': 'state', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'sys::runsheet::description': {'title': 'Description', 'format': 'text', 'field': 'description', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'},
    'sys::runsheet::processgroupid': {'title': 'Group ID', 'format': 'processgroupid', 'field': 'processgroupid', 'sortable': 'true', 'visible': 'true'},
    'sys::run::start_time': {'title': 'Start time', 'format': 'timestamp', 'field': 'start_time', 'sortable': 'true', 'visible': 'true'},
    'sys::run::finish_time': {'title': 'End time', 'format': 'timestamp', 'field': 'finish_time', 'sortable': 'true', 'visible': 'true'},
    'sys::runsheet::projectID': {'title': 'Project', 'format': 'projectid', 'field': 'projectid', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'sys::run::exit_code': {'title': 'Result', 'format': 'int', 'field': 'exit_code', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'sys::runsheet::input_collection': {'title': 'Input Collection', 'format': 'irods_collection', 'field': 'input_collection', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'}
}

PG_FIELDS = {
    'processgroupid': {'title': 'Group ID', 'format': 'processgroupid', 'field': 'processgroupid', 'sortable': 'true', 'visible': 'true'},
    'state': {'title': 'Group state', 'format': 'text', 'field': 'state', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'states': {'title': 'Process states', 'format': 'text', 'field': 'states', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'},
    'process_count': {'title': '#', 'format': 'int', 'field': 'count', 'sortable': 'true', 'visible': 'true'},
    'project': {'title': 'Project', 'format': 'projectid', 'field': 'projectid', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'start': {'title': 'Start Time', 'format': 'timestamp', 'field': 'start_time', 'sortable': 'true', 'visible': 'true'},
    'finish': {'title': 'End Time', 'format': 'timestamp', 'field': 'finish_time', 'sortable': 'true', 'visible': 'true'},
    'input_collection': {'title': 'First Input Collection', 'format': 'irods_collection', 'field': 'first_input_collection', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'}
}

PG_JOB_FIELDS = {
    'sys::runsheet::id': {'title': 'Name', 'format': 'runsheet', 'field': 'id', 'sortable': 'true', 'visible': 'true'},
    'sys::runsheet::state': {'title': 'State', 'format': 'text', 'field': 'state', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'sys::runsheet::description': {'title': 'Description', 'format': 'text', 'field': 'description', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'},
    'sys::runsheet::processgroupid': {'title': 'Group ID', 'format': 'processgroupid', 'field': 'processgroupid', 'sortable': 'true', 'visible': 'false'},
    'sys::run::start_time': {'title': 'Start time', 'format': 'timestamp', 'field': 'start_time', 'sortable': 'true', 'visible': 'true'},
    'sys::run::finish_time': {'title': 'End time', 'format': 'timestamp', 'field': 'finish_time', 'sortable': 'true', 'visible': 'true'},
    'sys::runsheet::projectID': {'title': 'Project', 'format': 'projectid', 'field': 'projectid', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'user::run::exit_code': {'title': 'Result', 'format': 'int', 'field': 'exit_code', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'sys::runsheet::input_collection': {'title': 'Input Collection', 'format': 'irods_collection', 'field': 'input_collection', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'},
}