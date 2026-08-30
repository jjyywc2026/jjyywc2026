@echo off
chcp 65001 >nul
set JAVA_HOME=C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot
set PATH=%JAVA_HOME%\bin;%PATH%
cd /d "C:\Users\happy time\PycharmProjects\app"
echo [APK BUILD] Starting at %DATE% %TIME% > apk_build.log
echo [APK BUILD] JAVA_HOME=%JAVA_HOME% >> apk_build.log
"C:\Users\happy time\AppData\Local\Programs\Python\Python39\Scripts\flet.exe" -v build apk --project wordlearning --org com.wordlearning --product WordLearning --build-number 1 --build-version 1.0.0 >> apk_build.log 2>&1
echo [APK BUILD] Exit code: %ERRORLEVEL% >> apk_build.log
echo [APK BUILD] Finished at %DATE% %TIME% >> apk_build.log
