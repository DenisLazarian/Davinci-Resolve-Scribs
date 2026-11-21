@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem =====================================================================
rem  UTF-8: consola, Python y este fichero usan UTF-8 para representar
rem  U+2715 (✕) en la salida y en los .pot/.po sin mojibake.
rem  Guardar este .bat como UTF-8 (sin BOM).
rem =====================================================================

rem Usar para buscar string en prints, logs o elementos de representacion flet.
rem (?:\b(?:label|text|value|title|subtitle|tooltip|hint_text|helper_text|error_text|prefix_text|suffix_text|caption|content)\s*=|\b(?:ft\.)?(?:Text|Markdown|ElevatedButton|FilledButton|OutlinedButton|TextButton)\s*\()\s*[fFrRbBuU]{0,2}(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*')


rem =====================================================================
rem  Genera/actualiza locales\dialogs.pot a partir de ficheros .py
rem  y compila los dialogs*.po de cada LC_MESSAGES a dialogs.mo.
rem
rem  Uso:
rem    build_i18n.bat archivo.py       -> usa ese archivo (obligatorio)
rem    build_i18n.bat a.py b.py        -> varios archivos
rem    Si no se pasa ninguno, se muestra un error y se pide la ruta.
rem    Tambien puedes arrastrar archivos .py sobre el .bat.
rem =====================================================================

set "BASE=%~dp0"
set "TOOLS=%BASE%py314-tools-i18n"
set "PYGETTEXT=%TOOLS%\pygettext.py"
set "MSGFMT=%TOOLS%\msgfmt.py"
set "POT=%BASE%locales\dialogs.pot"

set "PY=%BASE%..\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if not exist "%PYGETTEXT%" goto :no_tools
if not exist "%MSGFMT%" goto :no_tools
if not exist "%BASE%locales\" mkdir "%BASE%locales\"

rem --- reunir los ficheros de entrada -----------------------------------
set "FUENTES="
set "HUBO_PARAM="
if "%~1"=="" goto :pedir_source

:args
set "HUBO_PARAM=1"
if /i not "%~x1"==".py" (
    echo ✕ ERROR: "%~1" no es un fichero .py. Debe pasar archivos .py.
    echo.
    goto :pedir_source
)
if not exist "%~1" (
    echo ✕ ERROR: no existe "%~1".
    echo.
    goto :pedir_source
)
set "FUENTES=%FUENTES% "%~1""
shift
if not "%~1"=="" goto :args
goto :have_sources

:pedir_source
if defined HUBO_PARAM (
    echo Introduce una ruta valida, o pulsa Enter para cancelar.
) else (
    echo ✕ ERROR: no se ha pasado ningun archivo .py.
    echo.
)
:pedir
set "FUENTE="
set /p "FUENTE=Introduce la ruta del archivo .py (Enter para cancelar): "
if not defined FUENTE goto :no_source
set "FUENTE=%FUENTE:"=%"
if /i not "%FUENTE:~-3%"==".py" (
    echo ✕ ERROR: la extension debe ser .py.
    goto :pedir
)
if not exist "%FUENTE%" (
    echo ✕ ERROR: no existe "%FUENTE%".
    goto :pedir
)
set "FUENTES="%FUENTE%""

:have_sources
if not defined FUENTES goto :no_source

echo.
echo [1/3] Generando "%POT%"
"%PY%" "%PYGETTEXT%" -v -o "%POT%" %FUENTES%
if errorlevel 1 goto :error

rem --- la cabecera de pygettext dice cp1252; la pasamos a UTF-8 ----------
echo [2/3] Ajustando charset a UTF-8
"%PY%" -c "from pathlib import Path; p=Path(r'%POT%'); t=p.read_text(encoding='utf-8'); p.write_text(t.replace('charset=cp1252','charset=UTF-8'), encoding='utf-8')"
if errorlevel 1 goto :error

rem --- compilar los .po que estan dentro de LC_MESSAGES ------------------
echo [3/3] Compilando .mo desde LC_MESSAGES
for /d %%L in ("%BASE%locales\*") do (
    if exist "%%~L\LC_MESSAGES\" (
        for %%P in ("%%~L\LC_MESSAGES\dialogs*.po") do (
            if exist "%%~P" (
                echo   %%~nxL / %%~nxP  -^>  dialogs.mo
                "%PY%" "%MSGFMT%" -o "%%~L\LC_MESSAGES\dialogs.mo" "%%~P"
                if errorlevel 1 goto :error
            )
        )
    )
)

echo.
echo Listo.
echo.
pause
exit /b 0

:no_tools
echo ✕ ERROR: no encuentro pygettext.py / msgfmt.py en "%TOOLS%"
goto :fail

:no_source
echo ✕ ERROR: no hay ficheros .py de entrada.
goto :fail

:error
echo ✕ ERROR: fallo al generar los catalogos.
goto :fail

:fail
echo.
pause
exit /b 1
