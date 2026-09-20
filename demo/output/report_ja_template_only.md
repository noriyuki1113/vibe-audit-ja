# セキュリティ監査レポート（かんたん版）

確認済みの問題: **2件** ／ 要確認: **0件**

⚠️ このうち **2件** は緊急〜重要レベルです。まずここから対応してください。

---

## 1. 🔴 緊急：SQL injection in /api/products/search via unsanitized 'q' parameter

**何が起きているか**：The product search endpoint builds a SQL query by directly concatenating the raw 'q' query-string parameter into a LIKE clause. Any client can inject arbitrary SQL, allowing data exfiltration (e.g. dumping unrelated tables) or database corruption.

**なぜ危ないか**：今すぐ対応が必要です。放置すると実害が出る可能性が高いレベルです。

**関係するファイル**：app.js

**直し方（ざっくり）**：Use sqlite3's parameterized query placeholders so user input is always bound as data, never concatenated into SQL text.

**修正コードの例**：
- `app.js`
```
const sql = 'SELECT id, name, price FROM products WHERE name LIKE ?';
db.all(sql, [`%${keyword}%`], (err, rows) => { ... });
```

<details><summary>技術者向けの詳細（クリックで開く）</summary>

- root cause: User-controlled input is interpolated into a SQL string with template literals instead of being passed as a bound parameter to sqlite3's parameterized query API.
- 再現方法: GET /api/products/search?q=x%25' UNION SELECT username, password, 1 FROM users -- 
- confidence: high（The vulnerable data flow from request parameter to raw SQL execution is fully visible in a single file with no intervening sanitization.）

</details>

## 2. 🟠 重要：Live-looking API secret hardcoded in source and exposed via a public endpoint

**何が起きているか**：A secret-shaped constant (RAKUTEN_API_SECRET) is committed directly in app.js and is also returned verbatim in the JSON response of a public endpoint, exposing it to any client and to anyone with repository access.

**なぜ危ないか**：できるだけ早く対応することを強くおすすめします。

**関係するファイル**：app.js

**直し方（ざっくり）**：Move the secret to an environment variable (or a secret manager) loaded at runtime, remove it from source and git history, rotate the exposed key immediately, and stop returning it in any API response.

**修正コードの例**：
- `app.js`
```
const RAKUTEN_API_SECRET = process.env.RAKUTEN_API_SECRET;
// ...and never include RAKUTEN_API_SECRET in a res.json(...) response.
```

<details><summary>技術者向けの詳細（クリックで開く）</summary>

- root cause: The secret is stored as a literal in source code instead of an environment variable or secret manager, and is additionally echoed back in an API response instead of being kept server-side only.
- 再現方法: GET /api/products/1/rakuten-link
- confidence: high（The secret literal and its exposure point are both directly visible in a few lines of source with no ambiguity.）

</details>

