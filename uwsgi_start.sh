#!/bin/bash

source activate myflask
if [ $? -ne 0 ] ; then
mamba env create  -f myflask.yaml -q
source activate myflask
fi

PORT=5${UID: -3}

uwsgi --http :${PORT} --ini ngsweb.test.ini
source deactivate
