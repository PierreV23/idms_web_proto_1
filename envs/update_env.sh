#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" > /dev/null 2>&1 && pwd )"

mamba env remove -n myflask
mamba env update -f ${DIR}/myflask.source.yaml 
mamba env export --no-builds -n myflask | grep -v ^prefix | sed 's/python-graphviz/graphviz/' > ${DIR}/myflask.yaml

grep extra-index-url ${DIR}/myflask.source.yaml >> ${DIR}/myflask.yaml
