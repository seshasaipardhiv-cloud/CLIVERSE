@echo off
setlocal
set "PYTHONPATH=%~dp0src;%~dp0"
python -m cliverse.cli %*
