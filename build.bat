@echo off
chcp 65001 >nul
cd /d "C:\Users\happy time\PycharmProjects\app"
echo [BUILD] Starting PyInstaller...
"C:\Users\happy time\AppData\Local\Programs\Python\Python39\Scripts\pyinstaller.exe" ^
  --noconfirm ^
  --onefile ^
  --name "WordLearning" ^
  --collect-all flet ^
  --collect-all libsql ^
  --hidden-import pages ^
  --hidden-import pages.admin ^
  --hidden-import pages.admin.base ^
  --hidden-import pages.admin.reward_service ^
  --hidden-import pages.admin.users ^
  --hidden-import pages.admin.tasks ^
  --hidden-import pages.admin.exchange ^
  --hidden-import pages.admin.words_settings ^
  --hidden-import pages.admin.time_limits ^
  --hidden-import pages.admin.guoxue ^
  --hidden-import pages.admin.reward_rules ^
  --hidden-import pages.admin.reward_distribution ^
  --hidden-import pages.admin.gift_config ^
  --hidden-import pages.admin.item_management ^
  --hidden-import pages.admin.reward_history ^
  --hidden-import pages.admin.operation_history ^
  --hidden-import pages.admin.backpack ^
  --hidden-import pages.admin.score_history ^
  --hidden-import pages.heatmap ^
  --hidden-import pages.barchart ^
  --hidden-import pages.overview ^
  --hidden-import pages.home ^
  --hidden-import pages.login ^
  --hidden-import pages.my ^
  --hidden-import pages.english ^
  --hidden-import pages.cihai ^
  --hidden-import pages.guoxue ^
  --hidden-import pages.word_scoring ^
  main.py > build.log 2>&1
echo [BUILD] Exit code: %ERRORLEVEL%
echo [BUILD] Done. Check build.log for details.
