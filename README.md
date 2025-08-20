
# Currency Converter (Third-Party API Mini-Project)

A hands-on practice project to learn how to call and use a **third-party API** from Python.

**What it does**
- Fetches live FX rates from a free public API (base = USD).
- Converts between any two currencies.
- Caches results locally for 24h to reduce API calls.
- Works in interactive mode or via CLI flags.

## Requirements
- Python 3.9+
- Install dependency:
  ```bash
  pip install requests
  ```

## Run (Interactive)
```bash
python currency_converter.py
```

## Run (Non-Interactive)
```bash
python currency_converter.py --from USD --to UZS --amount 25
python currency_converter.py --from AED --to USD --amount 100
python currency_converter.py --list
```

## How it uses a Third-Party API
- Endpoint: `https://api.exchangerate-api.com/v4/latest/USD`
- Your code sends an **HTTP GET** request and receives **JSON**.
- JSON contains a `rates` dict with codes → rate vs USD.
- Conversion formula: `amount_in_usd = amount / rates[from]` then `* rates[to]`.

## Next steps (Vanta integration idea)
- Move fetching into a Flask route `/rates` with caching.
- Add a front-end dropdown for currencies; convert prices dynamically.
- Optionally switch to a provider with hourly updates.


# Vanta Inventory

Flask app for simple stock & sales with dual-currency display, Excel export, and Postgres/SQLite storage.

## Features
- Add / Sell / Return / Edit / Delete items
- Today’s revenue & profit + 7-day revenue
- Currency helpers (USD/AED/UZS) with cached FX (offline-safe)
- Excel export (DB currency + UI currency) via `openpyxl`
- Postgres ZIP backup (CSV per table)
- Auth via env-configurable admin users (case-insensitive)
- Health endpoint: `GET /__health`

---

## Quick Start (Windows / local)

```powershell
# 1) Create & activate venv
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# 2) Install deps
pip install --upgrade pip
pip install -r requirements.txt

# 3) Set env (PowerShell)
$env:SECRET_KEY = "dev-key-change"
$env:ADMIN_USERS = "vanta:beastmode,jasur:jasur2025"
# optional: work offline for FX/Geo
# $env:OFFLINE = "1"

# 4) Run (Windows-friendly server)
waitress-serve --listen=127.0.0.1:5000 app:app
