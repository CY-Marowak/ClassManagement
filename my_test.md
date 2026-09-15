已完成安裝與資料庫初始化，確認 .venv 和前後端的 node_modules 都還在。這次只需啟動三個服務。

  Git remote 用來備份程式碼；目前仍是在你電腦上啟動網站試用。

  ### 1. 第一個 PowerShell：啟動資料庫與後端

  cd "C:\Users\user\Documents\Brain\Side Projects\CM\app"
  npm.cmd run db:start
  node scripts/backend.mjs

  看到後端在 127.0.0.1:8000 啟動後，保持終端機開著。腳本會自動設定 CM_DEBUG。

  ### 2. 第二個 PowerShell：啟動前端

  cd "C:\Users\user\Documents\Brain\Side Projects\CM\app"
  npm.cmd run dev

  開啟 http://127.0.0.1:5173，統一使用這個網址，不要混用 localhost。

  ### 3. 開始試用

  註冊 → Email 驗證 → 登出／登入 → 忘記密碼。

  本機不會真的寄信。註冊後，另開第三個 PowerShell，在 app 資料夾執行：

  .\.venv\Scripts\python.exe scripts/read-mail.py teacher@example.com verify

  將 Email 換成你註冊的地址，開啟輸出的連結完成驗證。測試忘記密碼時，把 verify 換成 reset。

  ### 試完後

  在前端、後端終端機各按 Ctrl+C，再於 app 資料夾執行：

  npm.cmd run db:stop

  帳號和班級資料會保留，下次啟動可繼續使用。