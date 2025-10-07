#!/bin/bash

source activate myflask
if [ $? -ne 0 ] ; then
mamba env create  -f myflask.yaml -q
source activate myflask
fi

mkdir -p metrics

PORT=5${UID: -3}

echo Listening on port ${PORT}

uwsgi --http :${PORT} --ini ngsweb.test.ini --metrics-dir metrics
source deactivate
