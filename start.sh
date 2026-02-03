#!/bin/bash

source activate myflask
if [ $? -ne 0 ] ; then
mamba env create  -f myflask.yaml -q
source activate myflask
fi

export FLASK_APP="app.ngsweb:create_app"
PORT=55${UID: -3}
echo RUN on $PORT
flask --debug run --host=0.0.0.0 --port=$PORT --with-threads
conda deactivate
