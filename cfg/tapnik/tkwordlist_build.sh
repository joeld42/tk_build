#!/bin/bash
if [ -z "$1" ] 
	then
	echo "Use tkwordlist_build.sh <path_to_work_dir>"
	exit 1
fi

mkdir -p $1/build
cd $1/build
cmake ..
make VERBOSE=1


