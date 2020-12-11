#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" > /dev/null 2>&1 && pwd )"

cd $DIR

if [ -d /opt/miniconda3 ] ; then
export PATH=/opt/miniconda3/bin:$PATH
fi

if [ ! -d migrations ] ; then
    flask db init
fi
flask db migrate
flask db upgrade
                                           
