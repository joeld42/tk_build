echo ON

@call "%VS150COMNTOOLS%VsDevCmd.bat"
cd %1
@call fips set config win64-vs2017-release
@call fips gen

REM Set the version number and the build number eg tag_version GITHUB_HASH BUILD_NUM
python ./scripts/tag_version.py %2 %3

@call fips make civclicker




