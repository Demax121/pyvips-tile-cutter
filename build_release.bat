@echo off
echo ========================================
echo Building Tile Cutter - Release Version
echo ========================================
echo.

echo Cleaning old build files...
if exist build rmdir /s /q build
if exist dist\tile-cutter.exe del /q dist\tile-cutter.exe

echo.
echo Building with PyInstaller (release mode)...
pyinstaller tile-cutter.spec

echo.
if exist dist\tile-cutter.exe (
    echo ========================================
    echo SUCCESS! Release version built.
    echo ========================================
    echo.
    echo Location: dist\tile-cutter.exe
    echo.
    echo This is the final version without console window.
    echo Distribute this file to end users.
    echo.
) else (
    echo ========================================
    echo ERROR! Build failed.
    echo ========================================
    echo Check the output above for errors.
)

pause
