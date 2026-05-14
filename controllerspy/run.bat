@echo off
set WEBOTS_HOME=C:\Program Files\Webots
set PYTHONPATH=%WEBOTS_HOME%\lib\controller\python;%PYTHONPATH%
echo Webots'i baslat ve my_world.wbt yi ac.
echo Sonra bu terminalde Enter'a bas...
pause
python controllers\my_controller\my_controller.py
pause
