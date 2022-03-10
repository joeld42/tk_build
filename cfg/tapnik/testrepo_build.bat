echo ON
@call "%VS150COMNTOOLS%VsDevCmd.bat"
mkdir %1\build
cd %1\build
cmake .. -DCOMMIT:STRING=%2 -DBUILDNUM:STRING=%3
devenv puzzle3.sln /build Release /Project puzzle3