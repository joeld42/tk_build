#!/bin/bash
if [ "$#" -ne 3 ] 
	then
	echo "Use civclicker_package.sh <path_to_work_dir> <version> <build_num>"
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
mkdir -p $1/export
./fips set config metal-ios-xcode-release

xcodebuild -project $1/../fips-build/${PWD##*/}/metal-ios-xcode-release/civclicker.xcodeproj \
	-scheme civclicker -archivePath $1/civclicker_archive archive

xcodebuild -exportArchive -archivePath $1/civclicker_archive.xcarchive \
	-exportOptionsPlist /opt/tkbuild/civclickerExportOptions.plist \
	-exportPath $1/export

mv $1/export/civclicker.ipa $1/export/civclicker_$2_$3.ipa

