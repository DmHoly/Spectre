@echo off
setlocal

cd /d "%~dp0"

echo === Spectre - mise a jour ===
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Git n'est pas installe ou pas dans le PATH.
    echo Installez Git ^(https://git-scm.com/download/win^) puis relancez ce script.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo [ERREUR] Environnement virtuel introuvable.
    echo Lancez d'abord install.bat.
    pause
    exit /b 1
)

echo Recuperation des dernieres modifications de Spectre ...
git pull --ff-only
if errorlevel 1 (
    echo [ERREUR] "git pull" a echoue - probablement des modifications locales non enregistrees.
    echo Mettez-les de cote ^(git stash^) ou annulez-les, puis relancez ce script.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo.
echo Mise a jour des dependances Python (Spectre) ...
pip install -e ".[dev]" --upgrade
if errorlevel 1 (
    echo [ERREUR] La mise a jour des dependances a echoue - voir le message ci-dessus.
    pause
    exit /b 1
)

echo.
echo Recuperation des dernieres versions de StructureForge et Follow depuis GitHub ...
echo ^(pip garde sinon la version deja installee meme si le depot a change^)
pip install --upgrade --force-reinstall --no-deps "structureforge[follow] @ git+https://github.com/dmholy/structureforge.git@claude/spectre-integration-metier-d1qjdw"
if errorlevel 1 (
    echo [ERREUR] La mise a jour de StructureForge a echoue - voir le message ci-dessus.
    pause
    exit /b 1
)
pip install --upgrade --force-reinstall --no-deps "follow @ git+https://github.com/DmHoly/Follow.git"
if errorlevel 1 (
    echo [ERREUR] La mise a jour de Follow a echoue - voir le message ci-dessus.
    pause
    exit /b 1
)

echo.
echo === Mise a jour terminee ===
echo Lancez start.bat pour demarrer Spectre.
pause
