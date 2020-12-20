#!/bin/bash
if [ "$#" -ne 3 ] 
	then
	echo "Use testrepo_build.sh <path_to_work_dir> <commit_ver> <build_num>"
	exit 1
fi

# Stop and return error code on failure
set -e

# keep track of the last executed command
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
# echo an error message before exiting
trap 'echo "\"${last_command}\" failed with exit code $?."' EXIT

# Actual build steps here
mkdir -p $1/build
cd $1/build
cmake .. -DCOMMIT:STRING=$2 -DBUILDNUM:STRING=$3
make VERBOSE=1


