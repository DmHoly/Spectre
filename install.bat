@echo off
setlocal

cd /d "%~dp0"

echo === Spectre - installation ===
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Git n'est pas installe ou pas dans le PATH.
    echo Installez Git ^(https://git-scm.com/download/win^) puis relancez ce script.
    pause
    exit /b 1
)

set PYTHON_CMD=
py -3.11 --version >nul 2>nul
if not errorlevel 1 set PYTHON_CMD=py -3.11
if "%PYTHON_CMD%"=="" (
    python --version >nul 2>nul
    if not errorlevel 1 set PYTHON_CMD=python
)
if "%PYTHON_CMD%"=="" (
    echo [ERREUR] Python 3.11+ introuvable.
    echo Installez-le depuis https://www.python.org/downloads/ ^(cochez "Add python.exe to PATH"^)
    echo puis relancez ce script.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creation de l'environnement virtuel .venv ...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERREUR] La creation de l'environnement virtuel a echoue.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo Mise a jour de pip ...
python -m pip install --upgrade pip

echo Installation de Spectre et de ses dependances ^(StructureForge, Follow^) ...
echo Cette etape telecharge du code depuis GitHub, elle peut prendre quelques minutes.
pip install -e ".[dev]"
if errorlevel 1 (
    echo [ERREUR] L'installation a echoue - voir le message ci-dessus.
    pause
    exit /b 1
)

echo.
echo === Installation terminee ===
echo Lancez start.bat pour demarrer Spectre.
pause
