# CM · 班級日常

任務 01：教師註冊、Email 驗證、登入／登出、忘記密碼、建立與編輯自己的班級。

追加任務 01a：導師永久刪除自己的班級。

前端 React／TypeScript／Vite，後端 Django／DRF，資料庫 PostgreSQL。此資料夾為獨立 Git repo，遠端為 [CY-Marowak/ClassManagement](https://github.com/CY-Marowak/ClassManagement)。Brain 不備份這裡的程式碼；請在 app 資料夾提交後執行 `git push`，將產品提交推送至 GitHub。

## 第一次啟動（Windows PowerShell）

在本資料夾開啟終端機。需要 Python 3.12 與 Node.js 22.22 或相容版本。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
npm.cmd ci
Set-Location frontend
npm.cmd ci
Set-Location ..
npm.cmd run db:start
$env:CM_DEBUG='1'
.\.venv\Scripts\python.exe backend/manage.py migrate
node scripts/backend.mjs
```

另開一個終端機，在 app 資料夾執行：

```powershell
npm.cmd run dev
```

開啟 <http://127.0.0.1:5173>。保持使用同一個主機名稱，不要混用 localhost 與 127.0.0.1。

本機 PostgreSQL 監聽 `127.0.0.1:55432`，資料庫 cm，開發帳號 cm／cm-local-only。這組設定僅供本機開發，資料保存在 `.local/postgres/`。不會安裝系統服務，也不會自動刪除資料。停止資料庫：`npm.cmd run db:stop`。

## 如何試用註冊及忘記密碼

開發環境不寄真實郵件。提交註冊後，開啟 `.local/mail/` 最新的 `.log` 信件；由於 MIME 編碼，可用以下命令取得連結：

```powershell
.\.venv\Scripts\python.exe scripts/read-mail.py teacher@example.com verify
```

將 Email 換成你剛註冊的地址；忘記密碼時把 `verify` 換成 `reset`。開啟連結後，按畫面按鈕確認。連結 30 分鐘內有效、只能使用一次；重新寄送會讓舊連結失效。

Email 不需要真實存在就能本機試用。正式上線前必須配置 SMTP、寄件地址、HTTPS、秘密金鑰與正式資料庫。不要把 `.local`、`.env` 或 `.venv` 提交到 Git。

## 如何永久刪除班級

在「我的班級」選擇該班的「編輯班級」，於危險操作區點選「永久刪除班級」。閱讀刪除範圍與無法復原提示，輸入完整且相同的班級名稱後，才可按「確認永久刪除」；取消不改變資料。

僅該班導師可操作。班級、教師成員關係、學生檔案、專屬登入帳號、建立事件與學生 Session 會從 PostgreSQL 真正刪除，教師帳號與其他班級保留。分數紀錄與分數查核也會一起清除；後續點數、公告及吉祥物加入時必須同步支援刪除。此操作不提供復原，也不會清除外部資料庫備份。

## 建立學生與首次登入

導師在班級卡片選「學生名單」，點開預設收合的「加入學生」，從試算表複製座號、姓名、學號三欄並貼上。每次最多 200 筆，顯示新增／略過／待修正與原始行號；修正錯誤後可再貼一次。完全相同資料略過，衝突不覆寫；學號保留前導零，既有資料可使用名單內的「修改資料」。

逐行結果會帶出本次送入的座號、姓名、學號；缺少或多出欄位時改顯示原始該行，不猜欄位。有錯誤時預設「只看待修正」，可切成全部結果；重新匯入會依新結果重設篩選。匯入後保持展開供確認，下次進入學生名單時「加入學生」重新預設收合。

複製頁面上的學生登入連結分享給該班，連結預填固定班級登入碼。學生以學號及初始密碼（學號）登入，首次必須設定至少 10 字元、非常見／純數字／過度相似的密碼，才可查看自己的班級、姓名、座號及角色。教師 Email 登入與學生登入分開。

角色為建立時隨機固定的貓、狗、兔，同班可以重複，不可更換。`frontend/src/AnimalAvatar.tsx` 使用原創基本幾何 SVG；Lucide 只作簡單造型程度參考，沒有複製外部路徑或引入圖庫。學生角色與後續班級吉祥物不同。

## 修正學生資料、重設密碼與操作紀錄

在「學生名單」找到學生，選「修改資料」可更新姓名、座號與學號。同班座號或學號重複時，整次修改拒絕。改學號後使用新學號登入，密碼不會跟著改變；尚未首次改密碼者也保留原初始密碼，可另用重設功能協助。學生 ID、固定角色與既有紀錄保留。

「重設密碼」會先顯示學生與影響，按「確認重設密碼」後，密碼重設為目前學號，所有原登入失效，重新登入必須改密碼。

「操作紀錄」僅該班已批准導師可查看，含建立學生、修改資料與重設密碼，按新到舊每頁 25 筆；顯示當時操作者／學生姓名、時間與修改欄位前後差異。重設只記事件，不保存密碼或雜湊。沒有資料變更時不新增紀錄。

修改／重設與紀錄在同一交易完成；查核寫入失敗時操作回滾。永久刪班會清除該班所有學生查核紀錄，其他班級保留。更新既有環境時，啟動前執行 `backend/manage.py migrate`（同上設定 `CM_DEBUG=1`）；0006 將既有建立事件延伸為查核事件並保留原 ID、操作者及時間。

## 永久刪除學生

導師在學生名單選擇該列的「刪除學生」，確認座號、姓名、學號及危險提示，輸入完整學號後按「確認永久刪除學生」。後端再次核對目前學號，若另一個視窗已修改學號，會拒絕舊確認，請取消並重新進入名單。

此操作會從資料庫真正刪除學生、專屬帳號、本人全部歷史（含建立、修改資料、重設密碼的操作紀錄）及全部登入 Session，無法復原；不保留學生歷史副本。其他學生、教師與班級保留。取消或確認錯誤不會刪除，交易中任何步驟失敗時全部回滾。重新匯入相同座號／學號會建立全新身分，不恢復舊資料。外部備份不會隨此操作清除。

單次僅一位學生。任務 05 已擴充分數及分數查核的真正刪除回歸測試；後續點數等學生資料加入時仍須同步擴充。

## 共同教師申請、審核與移除

更新既有環境時先執行 `backend/manage.py migrate`（設定 `CM_DEBUG=1`）。0007 為每個既有班級分別產生教師申請碼，保留既有 membership、學生固定登入碼與資料。

1. 導師在班級卡片進入「教師管理」，複製教師申請碼並分享。
2. 另一個已驗證 Email 的教師登入，在「加入班級」輸入代碼並送出。等待審核時只能看班級、導師名稱及自己的狀態；點「更新申請狀態」取得最新結果。
3. 導師按「重新整理教師」，對待審申請選「批准」或「拒絕」。批准後該班出現在共同教師的班級列表；可進入「記分與紀錄」使用單筆記分及查看全班紀錄。
4. 導師可「重產申請碼」，確認後舊碼立即失效，但待審申請、已加入教師及學生登入碼不變。
5. 對已加入教師選「移除」，確認後立即撤銷該班後端存取。教師帳號、其他班級、既有 membership 身分與操作歷史保留。

待審／已加入時再次輸入有效碼，不重建申請或重複寫事件；已拒絕／移除者可持目前有效碼重新申請，必須再次審核。舊頁面的審核或重產請求會被拒絕，重新整理後再操作。教師申請碼以 `T-` 開頭，與學生登入碼分開。

「教師操作紀錄」僅導師可查看，按新到舊每頁 25 筆，顯示申請、批准、拒絕、移除及重產碼的操作者、當時姓名、時間與狀態變更，不記代碼原文。操作與事件在同一交易內完成，共用班級鎖；永久刪班會真正刪除該班申請、membership 與教師事件，教師帳號及其他班級保留。

可用兩個獨立瀏覽器視窗（其中一個為 InPrivate）自行測試上述流程。自動流程在 `e2e/membership.spec.ts`，畫面保存在 `.local/teachers-desktop.png` 與 `.local/teachers-mobile.png`。

## 單筆記分與學生分數

更新既有環境時設定 `CM_DEBUG=1` 並執行 `backend/manage.py migrate`，套用 0008／0009。既有學生總分初始化為 0，原帳號及資料保留。

1. 導師或已批准共同教師，在班級卡片選「記分與紀錄」。
2. 按座號選擇學生，選加分／扣分、原因模板、整數分數，必要時補充原因，再按「送出記分」。加分預設 +1、接受 0～100；扣分預設 −1、接受 −100～0。0 分保留加扣種類並留下紀錄。
3. 固定模板可補文字；選「其他」又留白時顯示待補原因，仍可記錄。補充上限 1000 字。記分不發點數。
4. 下方可看全班紀錄，或選一位學生看總分及明細。總分從 0 累計，可為負數；每頁 25 筆，最新在前。
5. 學生完成首次改密碼後，在個人頁看到自己的總分、原因、待補標記、教師姓名與時間；按「更新分數紀錄」取得最新結果。

送出按鈕在處理時停用；同一表單內容失敗後重試沿用操作識別，若伺服器其實已完成，不會再次計分。重新整理網頁或離開記分頁會失去表單暫存；不確定結果時先查看紀錄。後端以班級、操作者及 UUID 去重，相同識別卻換內容會拒絕。不同新操作即使內容相同也可再次記分。

記分、總分與建立查核在同一 PostgreSQL 交易中提交，班級鎖避免併發漏加及撤權競爭。保留建立教師當時姓名；學生改名後一般紀錄顯示目前姓名，建立查核保留當時快照。導師可由 `GET /api/classes/<id>/score-events/` 查詢建立查核；完整查核介面、修改／軟刪除屬任務 07。

永久刪除學生或班級會真正清除所屬分數與查核，其他學生／班級保留。任務 05 尚未建立點數或吉祥物模型，沒有自動獎勵交易。自動流程見 `e2e/scores.spec.ts`，涵蓋共同教師、0 分、網路回應遺失重試、學生隔離與撤權；截圖在 `.local/scores-desktop.png`、`scores-mobile.png`、`student-scores-mobile.png`。

## 驗證指令

```powershell
$env:CM_DEBUG='1'
.\.venv\Scripts\python.exe backend/manage.py test core --keepdb --noinput
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m mypy
npm.cmd run build
npm.cmd run test:e2e
```

API 測試使用獨立的 `test_cm` PostgreSQL 資料庫。瀏覽器測試使用本機開發資料庫與每次唯一的假 Email，會保留測試資料；不要對正式資料庫執行測試。預設使用已安裝的 Microsoft Edge（headless）；其他平台可調整 playwright.config.ts 的 channel 或安裝 Playwright Chromium。

瀏覽器截圖保存在 `.local/classroom-desktop.png` 與 `.local/classroom-mobile.png`。每次測試使用獨立輸出資料夾，不批量刪除舊結果。

## 從一次請求理解 Django

以建立班級為例：

1. `frontend/src/Classroom.tsx` 收集班級名稱、入學年度與目前年級。
2. `frontend/src/api.ts` 取得 CSRF token，使用登入 Cookie 送出 `POST /api/classes/`。
3. `backend/config/urls.py` 將網址交給 `core/cohorts.py` 的 View。
4. View 確認教師已驗證 Email；Serializer 驗證輸入。
5. Django ORM 在同一個資料庫交易內建立班級與導師 membership。
6. 回傳班級資料，React 更新列表。

`Model` 定義資料及約束；`Migration` 將模型變更套用到資料庫；`Serializer` 驗證 API 輸入及整理輸出；`View` 協調一次操作；`Session` 保存登入狀態。導師是班級角色，不是 Django 超級使用者。

## 範圍與實作選擇

- 已實作任務 01、01a、02、03、03a、04、05；批次記分、修改／軟刪除、點數與餵食依後續任務完成。
- 班級權限繼續以 membership 的 `approved` 判斷；未批准時由 `inactive_status` 區分 pending／rejected／removed。`revision` 防止舊頁面對已變更的身分狀態重新審核。新申請每個教師每 15 分鐘最多 30 次嘗試。
- 學生登入按班級碼＋學號每 15 分鐘 5 次、IP 每 15 分鐘 30 次限流。改密碼保留目前 Session，舊密碼 Session 失效。
- 名單匯入、學生資料修改、登入／改密碼／導師重設、刪除學生與刪班共用班級交易鎖；查核事件與資料修改一起保存。重設、刪除學生及刪班共用 Session 撤銷流程，目前逐筆解碼找出目標帳號，成本隨 Session 數量增加；大量使用前應加入可索引的帳號 Session 關聯。
- 登入依帳號每 15 分鐘 5 次，註冊／復原／重寄各每帳號 3 次；每類操作另有 IP 30 次上限。計數保存在 PostgreSQL 並以鎖保護，多個後端程序共用限制。正式反向代理需規劃可信來源 IP；程式不直接相信外部傳入的 X-Forwarded-For。
- 密碼至少 10 字元，框架拒絕常見、純數字及過度相似密碼。開發與正式環境均使用 Django 密碼雜湊。
- 驗證與重設 token 只儲存雜湊；信件連結放在 URL fragment，避免送到 HTTP access log。
- 欄位輸入邊界：班級名稱最多 80 字，入學年度 1900–2100，目前年級 1–12；這些為本次介面邊界，可依實際學制調整。
- 上線設定由環境變數提供，見 `.env.example`；檔案只供參考，Django 不會自動讀取它。

領域與決策來源：上層 `instructions.md`、`Implementation-decisions.md`、`CONTEXT.md`、`planning/cm-v1/spec.md` 與 `planning/cm-v1/issues/01-teacher-login-class.md`。
