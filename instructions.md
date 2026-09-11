# CM 產品程式碼

先讀上層 `../instructions.md`、`../Implementation-decisions.md`、`../CONTEXT.md`。現行規格與任務位於 `../planning/cm-v1/`，tracker 配置見 `../docs/agents/issue-tracker.md`。

本目錄為獨立 Git repo，只提交產品程式碼與執行文件，不使用 Brain remote。禁止批量刪除。使用根目錄 Skills/ 的 implement、tdd、code-review。

採 React／TypeScript／Vite、Django／DRF、PostgreSQL。以 Django Session 與 CSRF 實作同源登入。班級角色依 membership 判斷，不把導師變成 Django 超級使用者。

測試邊界已確認：HTTP 工作流 API → PostgreSQL，以及 Playwright 登入／角色隔離流程。先寫失敗測試，再完成最小功能。Review 比較本次工作開始前的 baseline commit 與本次完成的 commits。
