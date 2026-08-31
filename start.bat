@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERREUR] Environnement virtuel introuvable.
    echo Lancez d'abord install.bat.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

if "%SPECTRE_DATA_DIR%"=="" set SPECTRE_DATA_DIR=%~dp0data

echo === Spectre demarre sur http://127.0.0.1:8000/ ===
echo Donnees ecrites sous : %SPECTRE_DATA_DIR%
echo Une nouvelle fenetre va s'ouvrir avec les journaux du serveur - fermez-la ^(ou Ctrl+C^) pour l'arreter.
echo.

start "Spectre" cmd /k "call .venv\Scripts\activate.bat && set SPECTRE_DATA_DIR=%SPECTRE_DATA_DIR% && spectre --port 8000"

timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8000/
