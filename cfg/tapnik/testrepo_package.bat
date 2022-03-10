echo ON
mkdir %1\testrepo
cd %1
xcopy build\Release\puzzle3.exe .\testrepo\
xcopy README.md .\testrepo\
c:\Toolkits\7-Zip\7z a -tzip testrepo_%2_build_%3.zip testrepo