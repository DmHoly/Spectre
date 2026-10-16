@echo off
setlocal

rem Construit l'image Docker de Spectre et l'exporte en .tar pour l'installer ailleurs.
rem Resultat : dist\spectre-image.tar (a transmettre tel quel a l'IT).

cd /d "%~dp0"

set IMAGE=spectre
set TAR=dist\spectre-image.tar

docker version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Docker ne repond pas. Lancez Docker Desktop puis relancez ce script.
    pause
    exit /b 1
)

rem Tag de version : hash git court si disponible, sinon "latest" seul.
set VERSION=
for /f %%i in ('git rev-parse --short HEAD 2^>nul') do set VERSION=%%i

echo === Construction de l'image %IMAGE% ===
echo (necessite l'acces reseau vers GitHub et le GitLab interne pour les dependances)
echo.

if defined VERSION (
    docker build -t %IMAGE%:latest -t %IMAGE%:%VERSION% .
) else (
    docker build -t %IMAGE%:latest .
)
if errorlevel 1 (
    echo.
    echo [ERREUR] La construction a echoue.
    pause
    exit /b 1
)

if not exist dist mkdir dist
if exist "%TAR%" del "%TAR%"

echo.
echo === Export vers %TAR% ===
docker save -o "%TAR%" %IMAGE%:latest
if errorlevel 1 (
    echo.
    echo [ERREUR] L'export a echoue.
    pause
    exit /b 1
)

copy /y ".env.example" "dist\.env.example" >nul

echo.
echo === Termine ===
for %%f in ("%TAR%") do echo Fichier : %%~ff ^(%%~zf octets^)
if defined VERSION echo Version : %VERSION%
echo.
echo Installation sur le serveur cible :
echo   1. copier dist\.env.example en .env et y mettre PRISM_USER / PRISM_PASSWORD
echo      ^(le mot de passe n'est jamais dans l'image^)
echo   2. docker load -i spectre-image.tar
echo   3. docker run -d --name spectre --restart unless-stopped -p 8000:8000 -v spectre-data:/data --env-file .env -e SPECTRE_BASE_URL=https://URL_PUBLIQUE spectre:latest
echo.
pause
