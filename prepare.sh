#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" > /dev/null 2>&1 && pwd )"

cd $DIR

source activate myflask
if [ $? -ne 0 ] ; then
conda env update -f myflask.yaml
source activate myflask
fi

. db_migrate.sh

if [ ! -d migrations ] ; then 
    flask db init
fi
flask db migrate
flask db upgrade
