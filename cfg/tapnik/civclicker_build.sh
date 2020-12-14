#!/bin/bash
if [ -z "$1" ] 
	then
	echo "Use civclicker_build.sh <path_to_work_dir>"
	exit 1
fi

# Stop and return error code on failure
set -e

# keep track of the last executed command
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
# echo an error message before exiting
trap 'echo "\"${last_command}\" failed with exit code $?."' EXIT

# Actual build steps here
cd $1
./fips gen
./fips build


