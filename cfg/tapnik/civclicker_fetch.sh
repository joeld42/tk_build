#!/bin/bash
if [ -z "$1" ] 
	then
	echo "Use civclicker_fetch.sh <path_to_work_dir>"
	exit 1
fi

# Stop and return error code on failure
set -e

# keep track of the last executed command
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
# echo an error message before exiting
trap 'echo "\"${last_command}\" failed with exit code $?."' EXIT

# Repo has been fetched into the workdir ($1), use fips to fetch the deps
# and initialize the targets
cd $1
./fips fetch


