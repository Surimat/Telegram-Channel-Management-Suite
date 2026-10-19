@echo off
REM ============================================================
REM  ОБНОВЛЕНИЕ существующей установки с сохранением данных.
REM
REM  Просто дважды щёлкните по этому файлу (Windows 10).
REM  Ничего вводить не нужно.
REM
REM  Что произойдёт:
REM    1. Программа найдёт вашу установку сама. Если найти не
REM       удалось — откроется обычное окно выбора папки.
REM    2. Автоматически сделает резервную копию всех данных и
REM       секретов (папка backups\preupdate-...).
REM    3. Обновит файлы программы, НЕ трогая ваши настройки,
REM       токены и ключ шифрования (.env остаётся прежним).
REM    4. Аккуратно применит обновления базы данных.
REM    5. Проверит, что данные и секреты на месте.
REM
REM  Старая копия и резервная копия остаются на месте.
REM  В Telegram ничего не отправляется и не публикуется.
REM ============================================================
setlocal enableextensions
cd /d "%~dp0"

REM Русские буквы в окне консоли.
chcp 65001 >nul

REM Код новой версии лежит в app\ ; делаем его видимым для Python.
set "PYTHONPATH=%~dp0app"

REM Берём встроенный Python из новой сборки; если его нет — системный.
set "PYTHON=%~dp0runtime\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

set "UPDATER=%~dp0app\scripts\update_existing.py"
if not exist "%UPDATER%" (
  echo ОШИБКА: не найден файл обновления:
  echo   %UPDATER%
  echo Возможно, архив распакован не полностью.
  pause
  exit /b 1
)

echo ============================================================
echo  Обновление Telegram Channel Management Suite
echo  с сохранением настроек и секретов
echo ============================================================
echo.

REM Шаг 1: попробовать найти установку автоматически.
"%PYTHON%" "%UPDATER%" --auto
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" goto done

REM Код 3 = установка не найдена или их несколько: показать окно выбора папки.
if "%RC%"=="3" (
  echo.
  echo Выберите папку с уже установленной программой
  echo (внутри неё должны лежать run.bat и файл .env^).
  echo.
  set "TARGET="
  for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $f=New-Object System.Windows.Forms.FolderBrowserDialog; $f.Description='Выберите папку установленной программы (где run.bat и .env)'; $f.ShowNewFolderButton=$false; if($f.ShowDialog() -eq 'OK'){Write-Output $f.SelectedPath}"`) do set "TARGET=%%I"
  if not defined TARGET (
    echo Папка не выбрана. Обновление отменено. Ничего не изменено.
    pause
    exit /b 1
  )
  echo Выбрана папка: %TARGET%
  echo.
  "%PYTHON%" "%UPDATER%" --root "%TARGET%"
  set "RC=%ERRORLEVEL%"
)

:done
echo.
echo ============================================================
if "%RC%"=="0" (
  echo  ГОТОВО. Обновление выполнено успешно.
  echo  Теперь запустите программу как обычно — файлом run.bat
  echo  в папке установки.
) else (
  echo  ВНИМАНИЕ: обновление не завершено.
  echo  Ваши данные не изменены. Подробности — выше в этом окне.
  echo  Резервная копия лежит в папке установки: backups\preupdate-...
)
echo ============================================================
pause
endlocal
exit /b %RC%
