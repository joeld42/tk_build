echo ON

mkdir %1\civclicker_dist

xcopy /y %1\..\fips-deploy\%2\win64-vs2017-release\civclicker.exe %1\civclicker_dist\
xcopy /y %1\README.md %1\civclicker_dist\
robocopy /s /e %1\gamedata %1\civclicker_dist\gamedata

cd %1
c:\Toolkits\7-Zip\7z a -tzip civclicker_%3_build_%4.zip civclicker_dist
