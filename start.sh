#!/bin/sh

source activate myflask
if [ $? -ne 0 ] ; then
conda env create  -f myflask.yaml -q
source activate myflask
fi

export FLASK_APP=app
export FLASK_ENV=development
PORT=5${UID: -3}
flask run --host=0.0.0.0 --port=$PORT
source deactivate
