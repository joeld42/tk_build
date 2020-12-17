#!/bin/bash
if [ "$#" -ne 3 ] 
	then
	echo "Use testrepo_package.sh <path_to_work_dir> <version> <build_num>"
	exit 1
fi

# Stop and return error code on failure
set -e

# keep track of the last executed command
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
# echo an error message before exiting
trap 'echo "\"${last_command}\" failed with exit code $?."' EXIT

# Actual build steps here
mkdir -p $1/testrepo
cd $1
cp build/puzzle3 testrepo/
cp README.md testrepo/
zip -r -X testrepo_$2_build_$3.zip testrepo


