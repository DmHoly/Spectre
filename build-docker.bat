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

rem Le GitLab interne demande un compte : jeton d'acces personnel (portee read_repository), lu dans la
rem variable GITLAB_TOKEN ou demande ici. Il est transmis a docker comme secret de build : jamais
rem ecrit dans l'image.
if not defined GITLAB_TOKEN (
    echo Jeton d'acces GitLab ^(gitlab-it.aledia.com ^> Preferences ^> Access tokens, portee read_repository^)
    set /p GITLAB_TOKEN=Jeton :
)

echo === Construction de l'image %IMAGE% ===
echo (necessite l'acces reseau vers GitHub et le GitLab interne pour les dependances)
echo.

if defined VERSION (
    docker build --secret id=gitlab_token,env=GITLAB_TOKEN -t %IMAGE%:latest -t %IMAGE%:%VERSION% .
) else (
    docker build --secret id=gitlab_token,env=GITLAB_TOKEN -t %IMAGE%:latest .
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
copy /y "docker-compose.yml" "dist\docker-compose.yml" >nul

echo.
echo === Termine ===
for %%f in ("%TAR%") do echo Fichier : %%~ff ^(%%~zf octets^)
if defined VERSION echo Version : %VERSION%
echo.
echo Installation sur le serveur cible : voir DEPLOIEMENT.md
echo   Copier dans un meme dossier : spectre-image.tar, docker-compose.yml, .env.example
echo   puis : docker load -i spectre-image.tar  ^&^&  docker compose up -d   ^(port 8000^)
echo.
pause
