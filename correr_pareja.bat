@echo off
chcp 65001 >NUL
cd /d "%~dp0"
set PY=
where py >NUL 2>&1 && set PY=py -3
if not defined PY where python >NUL 2>&1 && set PY=python
if not defined PY (
  echo No encontre Python. Instala Python 3 desde python.org
  pause
  exit /b 1
)
echo BENCHMARK PAREJA (modelo local escribe, Claude revisa)
echo Deja LM Studio abierto con el servidor encendido. Se probara el modelo que este cargado.
echo.
%PY% -u pareja_benchmark.py %*
echo.
pause
