const express = require('express');
const sqlite3 = require('sqlite3');
const app = express();

// NOTE: this looks like a typical Lovable/vibe-coding output — quick to ship, easy to miss the risk.

// (1) Hardcoded secret shipped straight into the repo.
const RAKUTEN_API_SECRET = 'sk_live_51Hc9F3example_do_not_reuse';

const db = new sqlite3.Database('./products.db');

app.get('/api/products/search', (req, res) => {
  const keyword = req.query.q;

  // (2) User input concatenated directly into SQL -> classic SQL injection.
  const sql = `SELECT id, name, price FROM products WHERE name LIKE '%${keyword}%'`;

  db.all(sql, [], (err, rows) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(rows);
  });
});

app.get('/api/products/:id/rakuten-link', (req, res) => {
  // (3) Secret reused directly in a client-facing response.
  res.json({ id: req.params.id, apiKeyUsed: RAKUTEN_API_SECRET });
});

app.listen(3000, () => console.log('listening on 3000'));
