@echo off
rem Arranca el servidor del formulario con el Python del .venv, FUERA de Resolve.
rem Uso manual (doble clic o terminal). El lanzador normal es flet_form.py.
setlocal
cd /d "%~dp0"

set "RESOLVE_SCRIPT_API=C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
set "RESOLVE_SCRIPT_LIB=C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
set "PYTHONPATH=%RESOLVE_SCRIPT_API%\Modules;%PYTHONPATH%"

"..\.venv\Scripts\python.exe" flet_form.py

endlocal

rem (?:\b(?:label|text|value|title|subtitle|tooltip|hint_text|helper_text|error_text|prefix_text|suffix_text|caption|content)\s*=|\b(?:ft\.)?(?:Text|Markdown|ElevatedButton|FilledButton|OutlinedButton|TextButton)\s*\()\s*[fFrRbBuU]{0,2}(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*')
