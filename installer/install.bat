@echo off
chcp 65001 >nul 2>&1

setlocal enabledelayedexpansion

echo ==========================================
echo   Forester Installer (Windows)
echo ==========================================
echo.

set "INSTALLER_DIR=%~dp0"
set "BINARY_DIR=%INSTALLER_DIR%forester\windows\bin"
set "BINARY_PATH=%BINARY_DIR%\forester.exe"

if not exist "%BINARY_PATH%" (
    echo [ERROR] Binary not found: %BINARY_PATH%
    echo Check folder: %BINARY_DIR%
    pause
    exit /b 1
)

echo [OK] Binary found: %BINARY_PATH%
echo.

set "DEFAULT_INSTALL_PATH=C:\Program Files\Forester"
echo Installation path [%DEFAULT_INSTALL_PATH%]:
set /p "INSTALL_PATH=Enter path or press Enter for default: "
if "!INSTALL_PATH!"=="" set "INSTALL_PATH=%DEFAULT_INSTALL_PATH%"

echo.
echo Installing to: %INSTALL_PATH%
echo.

echo === Creating directories ===
mkdir "%INSTALL_PATH%\bin" 2>nul
copy "%BINARY_PATH%" "%INSTALL_PATH%\bin\forester.exe" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy binary
    echo Administrator rights may be required
    echo Try running as administrator
    pause
    exit /b 1
)

echo [OK] Binary installed: %INSTALL_PATH%\bin\forester.exe
echo.

echo === Verifying installation ===
"%INSTALL_PATH%\bin\forester.exe" --version >nul 2>&1
if errorlevel 1 (
    "%INSTALL_PATH%\bin\forester.exe" --help >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] Could not verify binary
    ) else (
        echo [OK] Binary is working
    )
) else (
    echo [OK] Binary is working
)
echo.

if exist "%INSTALLER_DIR%addons\blender" (
    echo === Installing Blender addon ===
    set /p "INSTALL_BLENDER=Install addon for Blender? [Y/n]: "
    if /i "!INSTALL_BLENDER!"=="" set "INSTALL_BLENDER=Y"
    if /i "!INSTALL_BLENDER!"=="Y" (
        set "BLENDER_ADDON_PATH=%APPDATA%\Blender Foundation\Blender"
        
        if exist "!BLENDER_ADDON_PATH!" (
            echo Found Blender versions:
            for /d %%v in ("!BLENDER_ADDON_PATH!\*") do (
                echo   %%v
            )
            echo.
            
            set /p "INSTALL_ALL=Install for all versions? [Y/n]: "
            if /i "!INSTALL_ALL!"=="" set "INSTALL_ALL=Y"
            
            if /i "!INSTALL_ALL!"=="Y" (
                for /d %%v in ("!BLENDER_ADDON_PATH!\*") do (
                    set "ADDON_DEST=%%v\extensions\user_default\difference_machine"
                    mkdir "!ADDON_DEST!" 2>nul
                    xcopy /E /I /Y "%INSTALLER_DIR%addons\blender\difference_machine\*" "!ADDON_DEST!\" >nul
                    if errorlevel 1 (
                        echo [WARNING] Failed to install for %%~nv
                    ) else (
                        echo [OK] Installed for Blender %%~nv
                    )
                )
            ) else (
                set /p "BLENDER_VERSION=Enter Blender version (e.g. 5.0): "
                set "ADDON_DEST=!BLENDER_ADDON_PATH!\!BLENDER_VERSION!\extensions\user_default\difference_machine"
                if exist "!BLENDER_ADDON_PATH!\!BLENDER_VERSION!" (
                    mkdir "!ADDON_DEST!" 2>nul
                    xcopy /E /I /Y "%INSTALLER_DIR%addons\blender\difference_machine\*" "!ADDON_DEST!\" >nul
                    if errorlevel 1 (
                        echo [ERROR] Failed to install addon
                    ) else (
                        echo [OK] Installed for Blender !BLENDER_VERSION!
                    )
                ) else (
                    echo [ERROR] Blender version !BLENDER_VERSION! not found
                )
            )
        ) else (
            echo [WARNING] Blender not found in standard location
            echo.
            set /p "CUSTOM_BLENDER_PATH=Enter path to extensions\user_default Blender folder: "
            if exist "!CUSTOM_BLENDER_PATH!" (
                set "ADDON_DEST=!CUSTOM_BLENDER_PATH!\difference_machine"
                mkdir "!ADDON_DEST!" 2>nul
                xcopy /E /I /Y "%INSTALLER_DIR%addons\blender\difference_machine\*" "!ADDON_DEST!\" >nul
                if errorlevel 1 (
                    echo [ERROR] Failed to install addon
                ) else (
                    echo [OK] Installed to: !ADDON_DEST!
                )
            ) else (
                echo [ERROR] Path not found: !CUSTOM_BLENDER_PATH!
            )
        )
    )
)

echo.
echo === Creating configuration file ===
set "DFM_SETUP_DIR=%USERPROFILE%\.dfm-setup"
set "DFM_CONFIG_FILE=%DFM_SETUP_DIR%\setup.cfg"

mkdir "%DFM_SETUP_DIR%" 2>nul

(
    echo [forester]
    echo path = %INSTALL_PATH%
) > "%DFM_CONFIG_FILE%"

if exist "%DFM_CONFIG_FILE%" (
    echo [OK] Configuration file created: %DFM_CONFIG_FILE%
) else (
    echo [WARNING] Failed to create configuration file
    echo Create manually: %DFM_CONFIG_FILE%
)

echo.
echo ==========================================
echo [OK] Installation completed!
echo ==========================================
echo.
echo Forester CLI installed to: %INSTALL_PATH%\bin\forester.exe
echo Addon configuration: %DFM_CONFIG_FILE%
echo.
echo To add to PATH for convenience, run:
echo   setx PATH "%%PATH%%;!INSTALL_PATH!\bin"
echo.
pause
