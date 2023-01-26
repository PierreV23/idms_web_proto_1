JOB_FIELDS = {
    'sys::runsheet::id': {'title': 'Name', 'format': 'runsheet', 'field': 'id', 'sortable': 'true', 'visible': 'true'},
    'sys::runsheet::state': {'title': 'State', 'format': 'text', 'field': 'state', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'sys::runsheet::description': {'title': 'Description', 'format': 'text', 'field': 'description', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'},
    'sys::runsheet::processgroupid': {'title': 'Group ID', 'format': 'processgroupid', 'field': 'processgroupid', 'sortable': 'true', 'visible': 'true'},
    'sys::runsheet::create_time': {'title': 'Create time', 'format': 'timestamp', 'field': 'create_time', 'sortable': 'true', 'visible': 'true'},
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
    'exit_code': {'title': 'Result', 'format': 'int', 'field': 'exit_code', 'sortable': 'false', 'visible': 'true'},
    'process_count': {'title': '#', 'format': 'int', 'field': 'count', 'sortable': 'true', 'visible': 'true'},
    'project': {'title': 'Project', 'format': 'projectid', 'field': 'projectid', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'create_time': {'title': 'Create time', 'format': 'timestamp', 'field': 'create_time', 'sortable': 'true', 'visible': 'true'},
    'start': {'title': 'Start Time', 'format': 'timestamp', 'field': 'start_time', 'sortable': 'true', 'visible': 'true'},
    'finish': {'title': 'End Time', 'format': 'timestamp', 'field': 'finish_time', 'sortable': 'true', 'visible': 'true'},
    'input_collection': {'title': 'First Input Collection', 'format': 'irods_collection', 'field': 'first_input_collection', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'}
}

PG_JOB_FIELDS = {
    'sys::runsheet::id': {'title': 'Name', 'format': 'runsheet', 'field': 'id', 'sortable': 'true', 'visible': 'true'},
    'sys::runsheet::state': {'title': 'State', 'format': 'text', 'field': 'state', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'sys::runsheet::description': {'title': 'Description', 'format': 'text', 'field': 'description', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'},
    'sys::runsheet::processgroupid': {'title': 'Group ID', 'format': 'processgroupid', 'field': 'processgroupid', 'sortable': 'true', 'visible': 'false'},
    'sys::runsheet::create_time': {'title': 'Create time', 'format': 'timestamp', 'field': 'create_time', 'sortable': 'true', 'visible': 'true'},
    'sys::run::start_time': {'title': 'Start time', 'format': 'timestamp', 'field': 'start_time', 'sortable': 'true', 'visible': 'true'},
    'sys::run::finish_time': {'title': 'End time', 'format': 'timestamp', 'field': 'finish_time', 'sortable': 'true', 'visible': 'true'},
    'sys::runsheet::projectID': {'title': 'Project', 'format': 'projectid', 'field': 'projectid', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'user::run::exit_code': {'title': 'Result', 'format': 'int', 'field': 'exit_code', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'sys::runsheet::input_collection': {'title': 'Input Collection', 'format': 'irods_collection', 'field': 'input_collection', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'},
}

NGSRUN_FIELDS = {
    'id': {'title': 'Item ID', 'format': 'text', 'field': 'id', 'sortable': 'true', 'visible': 'false', 'align': 'center'},
    'creation_date': {'title': 'Creation Date', 'format': 'timestamp', 'field': 'creation_date', 'sortable': 'true', 'visible': 'false'},
    'name': {'title': 'Name', 'format': 'text', 'field': 'name', 'sortable': 'true', 'visible': 'true', 'align': 'center', 'filtercontrol': 'input'},
    'flowcell': {'title': 'Flowcell', 'format': 'text', 'field': 'flowcell', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'input'},
    'project': {'title': 'Project', 'format': 'projectid', 'field': 'project', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'owner': {'title': 'User', 'format': 'text', 'field': 'owner', 'sortable': 'true', 'visible': 'true', 'filtercontrol': 'select'},
    'datacoll': {'title': 'Collection', 'format': 'irods_collection', 'field': 'datacoll', 'sortable': 'false', 'visible': 'true'},
    'description': {'title': 'Description', 'format': 'text', 'field': 'description', 'sortable': 'false', 'visible': 'false', 'filtercontrol': 'input'}
}

BARCODE_FIELDS = {
    'barcode': {'title': 'Barcode', 'field': 'barcode', 'sortable': 'true'},
    'sampleid': {'title': 'ID', 'field': 'sampleid', 'sortable': 'true'},
    'virus_target': {'title': 'Virus Target', 'field': 'virus_target', 'sortable': 'true'},
    'primer_set': {'title': 'Primer Set', 'field': 'primer_set', 'sortable': 'true'},
    'description': {'title': 'Description', 'field': 'description', 'sortable': 'true'}
}