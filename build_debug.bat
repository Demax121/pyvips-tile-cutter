@echo off
echo ========================================
echo Building Tile Cutter - Debug Version
echo ========================================
echo.

echo Cleaning old build files...
if exist build rmdir /s /q build
if exist dist\tile-cutter-debug.exe del /q dist\tile-cutter-debug.exe

echo.
echo Building with PyInstaller (debug mode)...
pyinstaller tile-cutter-debug.spec

echo.
if exist dist\tile-cutter-debug.exe (
    echo ========================================
    echo SUCCESS! Debug version built.
    echo ========================================
    echo.
    echo Location: dist\tile-cutter-debug.exe
    echo.
    echo This version shows a console window with detailed logs.
    echo Use it to see what's happening and debug any issues.
    echo.
) else (
    echo ========================================
    echo ERROR! Build failed.
    echo ========================================
    echo Check the output above for errors.
)

pause
