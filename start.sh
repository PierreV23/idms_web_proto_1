#!/bin/sh

source activate myflask
if [ $? -ne 0 ] ; then
conda env create  -f myflask.yaml -q
source activate myflask
fi

export FLASK_APP=hello.py
export FLASK_ENV=development
flask run --host=0.0.0.0
source deactivate
