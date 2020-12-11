#!/bin/bash
if [ -z "$1" ] 
	then
	echo "Use tkwordlist_package.sh <path_to_work_dir>"
	exit 1
fi

mkdir -p $1/testrepo_pkg
cd $1


