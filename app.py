# app.py — Vanta Inventory (FINAL, merged, advanced)
# - Clean imports & logging
# - Robust currency/i18n helpers (USD/AED/UZS) with caching FX
# - Search + filter + 6-way sort (server param → in-memory)
# - Sell / Add / Edit / Delete / Return sale
# - Excel export (dual currency) with number formats
# - DB backup to ZIP (CSV per table) for Postgres
# - Health/version + GEO/Rates APIs (offline-safe)
# - Hardened login/logout (env-configurable admins, case-insensitive)
# - Advanced Stock Overview API for the chart (JSON + 401 if unauth)

import os, io, time, json, zipfile, logging, sys
from decimal import Decimal
from urllib.parse import urlparse
from datetime import datetime, date

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, jsonify, g
)

# Optional Babel for pretty money format (fallback below)
try:
    from babel.numbers import format_currency as _format_currency
except Exception:  # fallback if babel not installed
    def _format_currency(value, currency, locale=None):
        try:
            return f"{float(value or 0):,.2f} {currency}"
        except Exception:
            return f"{value} {currency}"

import requests

# Your DB helpers (SQLAlchemy wrapper):
# must expose: db_all(sql, params=None), db_one(sql, params=None), db_exec(sql, params=None), DATABASE_URL
import database_sqlalchemy as db
from database_sqlalchemy import ensure_schema

from i18n import t  # your translation helper

# Offline mode (skip all external HTTP and use safe defaults)
OFFLINE = os.getenv("OFFLINE", "0").lower() in ("1", "true", "yes")


# =========================
# App bootstrap + logging
# =========================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Ensure DB schema at boot
with app.app_context():
    try:
        ensure_schema()
        app.logger.info("✅ Database schema ensured at startup.")
    except Exception:
        app.logger.exception("⚠️ Failed to ensure schema")

# Global error guard (keep simple response, log stack)
@app.errorhandler(Exception)
def handle_error(e):
    app.logger.exception("Unhandled exception")
    return "Internal Server Error", 500


# =========================
# Env tweaks
# =========================
ENV = os.getenv("ENV", "dev").lower()
if ENV == "dev":
    app.config.update(
        DEBUG=True, TEMPLATES_AUTO_RELOAD=True, SERVER_NAME=None,
        SESSION_COOKIE_SECURE=False, SESSION_COOKIE_SAMESITE="Lax",
    )
else:
    app.config.update(
        TEMPLATES_AUTO_RELOAD=False, SEND_FILE_MAX_AGE_DEFAULT=31536000,
        SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax",
    )


# =========================
# Version / Health
# =========================
def get_version():
    try:
        return open("VERSION", encoding="utf-8").read().strip()
    except Exception:
        return os.getenv("APP_VERSION", "v1.0.0")

@app.context_processor
def inject_version():
    return {"APP_VERSION": get_version()}

@app.get("/__health")
def __health():
    return jsonify(status="ok", version=get_version()), 200


# =========================
# Currency / i18n helpers
# =========================
BASE_CCY = "UZS"          # DB-stored currency
DEFAULT_LANG = "en"
DEFAULT_CURR = "USD"
_SUPPORTED = {"USD", "AED", "UZS"}

def get_lang():
    return session.get("LANG", DEFAULT_LANG)

def get_curr():
    return session.get("CURR", DEFAULT_CURR)

def fmt_money(value, curr=None, lang=None):
    curr = curr or get_curr()
    lang = lang or get_lang()
    locale = "en_US" if lang == "en" else "uz_UZ"
    try:
        return _format_currency(float(value or 0), curr, locale=locale)
    except Exception:
        try:
            return f"{float(value):.2f} {curr}"
        except Exception:
            return f"{value} {curr}"

# FX cache: 1 USD = rate[currency]
_FX_CACHE = {"rates": None, "ts": 0}
def _fetch_usd_rates():
    # Always return something usable
    if OFFLINE:
        return {"USD": 1.0, "AED": 3.6725, "UZS": 12600.0}

    now = time.time()
    if _FX_CACHE["rates"] and (now - _FX_CACHE["ts"]) < 3600:
        return _FX_CACHE["rates"]

    providers = [
        ("exchangerate.host", lambda: requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": "USD,AED,UZS"},
            headers={"User-Agent": "VantaInventory/1.0"}, timeout=8
        ).json().get("rates", {})),
        ("open.er-api.com", lambda: requests.get(
            "https://open.er-api.com/v6/latest/USD",
            headers={"User-Agent": "VantaInventory/1.0"}, timeout=8
        ).json().get("rates", {})),
        ("frankfurter.app", lambda: requests.get(
            "https://api.frankfurter.dev/v1/latest",
            params={"from": "USD", "to": "AED,USD,UZS"},
            headers={"User-Agent": "VantaInventory/1.0"}, timeout=8
        ).json().get("rates", {})),
    ]

    rates = None
    for _, fn in providers:
        try:
            r = fn() or {}
            out = {
                "USD": float(r.get("USD", 1.0)),
                "AED": float(r.get("AED")) if r.get("AED") is not None else None,
                "UZS": float(r.get("UZS")) if r.get("UZS") is not None else None,
            }
            if out["AED"] is None and "AED" in r and r["AED"]:
                out["AED"] = float(r["AED"])
            if out["UZS"] is None and "UZS" in r and r["UZS"]:
                out["UZS"] = float(r["UZS"])
            if out["AED"] is not None:
                if out["UZS"] is None:
                    prev = _FX_CACHE.get("rates") or {}
                    out["UZS"] = float(prev.get("UZS", 12600.0))
                rates = out
                break
        except Exception:
            continue

    if not rates:
        rates = {"USD": 1.0, "AED": 3.6725, "UZS": 12600.0}

    _FX_CACHE.update({"rates": rates, "ts": time.time()})
    return rates


def _derive_rates_from_usd(base):
    R = _fetch_usd_rates()
    base = (base or "USD").upper()
    if base not in R:
        base = "USD"
    out = {}
    for x in _SUPPORTED:
        if x == base:
            out[x] = 1.0
        else:
            try:
                out[x] = float(R[x]) / float(R[base])
            except Exception:
                out[x] = 0.0
    return base, out

def convert_amount(value, from_curr=None, to_curr=None):
    try:
        v = float(value or 0)
    except Exception:
        return 0.0
    from_curr = (from_curr or BASE_CCY).upper()
    to_curr   = (to_curr or get_curr()).upper()
    if from_curr == to_curr:
        return v

    R = _fetch_usd_rates()
    if from_curr not in R or to_curr not in R:
        return v

    amount_usd = v / float(R[from_curr])
    return amount_usd * float(R[to_curr])

def fmt_money_auto(value, from_curr=None):
    return fmt_money(convert_amount(value, from_curr=from_curr, to_curr=get_curr()))

# Money parsing helpers (for “1,234” inputs)
def money_plain(v, decimals=0):
    try:
        v = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return v
    return f"{v:,.{decimals}f}"

def parse_money(s):
    try:
        return float(str(s).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


# =========================
# Auth (hardened)
# =========================
def _load_admins():
    """
    Load admins from env:
      ADMIN_USERS_JSON='{"admin":"admin","jasur":"jasur2025"}'
      -or-
      ADMIN_USERS='admin:admin,jasur:jasur2025'
    Fallback includes 'vanta:beastmode' + 'jasur:jasur2025'.
    Keys stored casefold() for case-insensitive matching.
    """
    raw_json = os.environ.get("ADMIN_USERS_JSON", "").strip()
    if raw_json:
        try:
            data = json.loads(raw_json)
            return { (k or "").casefold(): str(v) for k, v in data.items() }
        except Exception:
            pass

    raw_pairs = os.environ.get("ADMIN_USERS", "").strip()
    if raw_pairs:
        try:
            pairs = dict(pair.split(":", 1) for pair in raw_pairs.split(","))
            return { (k or "").casefold(): str(v) for k, v in pairs.items() }
        except Exception:
            pass

    return {"vanta": "beastmode", "jasur": "jasur2025"}

ADMIN_USERS = _load_admins()
ADMIN_ADMINS = set(ADMIN_USERS.keys())  # allow-list

def is_logged_in():
    return bool(session.get("logged_in"))

def is_admin_user():
    return (session.get("user") or "").casefold() in ADMIN_ADMINS


# =========================
# Jinja filters / context
# =========================
@app.before_request
def _inject_currency():
    g.CURRENCY = get_curr()

@app.template_filter("ccy")
def ccy(amount):
    # DB currency (UZS) → UI currency
    return convert_amount(amount, from_curr=BASE_CCY, to_curr=get_curr())

@app.template_filter("fmtmoney")
def fmtmoney(amount):
    return fmt_money(amount, curr=get_curr(), lang=get_lang())

# extra helpers for tables
@app.template_filter("comma")
def comma(x):
    try:
        return f"{int(x):,}"
    except Exception:
        return x

@app.template_filter("moneyfmt")
def moneyfmt(x, currency=""):
    try:
        return f"{int(float(x)):,} {currency}" if currency else f"{int(float(x)):,}"
    except Exception:
        return x

@app.context_processor
def inject_helpers():
    lang = get_lang()
    return {
        "fmt_money": fmt_money,
        "fmt_money_auto": fmt_money_auto,
        "convert": convert_amount,
        "USER_LANG": lang,
        "USER_CURR": get_curr(),
        "CURRENCY": get_curr(),
        "t": lambda key, _lang=None: t(key, lang if _lang is None else _lang),
    }

@app.template_filter("money")
def money_filter(v):
    # show plain number with thousand separators, no currency symbol
    try:
        return money_plain(v, decimals=0)
    except Exception:
        return v

# =========================
# Data access
# =========================
def get_inventory():
    rows = db.db_all("""
        SELECT
            id,
            name,
            buying_price,
            selling_price,
            quantity,
            CASE
              WHEN profit IS NULL OR profit = 0
                THEN (selling_price - buying_price) * quantity
              ELSE profit
            END AS profit,
            COALESCE(currency, :c) AS currency
        FROM inventory
        ORDER BY id
    """, {"c": BASE_CCY})
    return [tuple(r) for r in rows]


# =========================
# Pages / Routes
# =========================
@app.route("/")
def index():
    if not is_logged_in():
        return redirect(url_for("login"))

    # ----- params -----
    search_query    = (request.values.get("search", "") or "").strip().lower()
    selected_filter = request.values.get("filter", "")
    sort_by         = request.args.get("sort_by", "id")
    direction       = request.args.get("direction", "asc")

    # support ?sort=name_asc|name_desc|qty_asc|qty_desc|price_asc|price_desc
    sort_param = request.args.get("sort")
    if sort_param:
        mapping = {
            "name_asc":  ("name", "asc"),
            "name_desc": ("name", "desc"),
            "qty_asc":   ("quantity", "asc"),
            "qty_desc":  ("quantity", "desc"),
            "price_asc": ("price", "asc"),
            "price_desc":("price", "desc"),
        }
        sort_by, direction = mapping.get(sort_param, (sort_by, direction))

       # ----- data -----
    inventory = get_inventory()  # (id, name, buy, sell, qty, profit, currency)
    using_sqlite = db.DATABASE_URL.startswith("sqlite")

    # --- Today revenue/profit ---
    if using_sqlite:
        row = db.db_one("""
            SELECT
              COALESCE(SUM(qty * sell_price), 0),
              COALESCE(SUM(profit), 0)
            FROM sales
            WHERE DATE(sold_at, 'localtime') = DATE('now','localtime')
        """)
    else:
        row = db.db_one("""
            SELECT
              COALESCE(SUM(qty * sell_price), 0),
              COALESCE(SUM(profit), 0)
            FROM sales s
            WHERE DATE(s.sold_at) = CURRENT_DATE
        """)
    today_revenue = row[0] if row else 0
    today_profit  = row[1] if row else 0

    # Filtering
    if search_query:
        inventory = [it for it in inventory if search_query in (it[1] or "").lower()]
    if selected_filter == "low_stock":
        inventory = [it for it in inventory if (it[4] or 0) <= 5]
    elif selected_filter == "high_profit":
        inventory = [it for it in inventory if (it[5] or 0) >= 100]

    # Sorting
    sort_map = {"name": 1, "quantity": 4, "profit": 5, "price": 3}
    if sort_by in sort_map:
        idx = sort_map[sort_by]
        inventory = sorted(
            inventory,
            key=lambda x: (x[idx] is None, x[idx]),
            reverse=(direction == "desc"),
        )

    # Totals
    def nz_dec(x): return x if x is not None else Decimal(0)
    def nz_int(x): return x if x is not None else 0
    total_quantity = sum(nz_int(it[4]) for it in inventory)
    total_profit   = sum(nz_dec(it[5]) for it in inventory)

    # Top/Low lists
    top_profit_items = sorted(inventory, key=lambda x: (x[5] is None, x[5]), reverse=True)[:5]
    low_stock_items  = sorted(inventory, key=lambda x: (x[4] is None, x[4]))[:5]

    # --- Last 7 days revenue ---
    if using_sqlite:
        rows = db.db_all("""
            WITH days AS (
              SELECT DATE('now','localtime','-6 day') AS d
              UNION ALL SELECT DATE('now','localtime','-5 day')
              UNION ALL SELECT DATE('now','localtime','-4 day')
              UNION ALL SELECT DATE('now','localtime','-3 day')
              UNION ALL SELECT DATE('now','localtime','-2 day')
              UNION ALL SELECT DATE('now','localtime','-1 day')
              UNION ALL SELECT DATE('now','localtime')
            )
            SELECT d AS day,
                   COALESCE((
                     SELECT SUM(qty*sell_price)
                     FROM sales s
                     WHERE DATE(s.sold_at,'localtime') = d
                   ),0) AS revenue
            FROM days
            ORDER BY d
        """)
    else:
        rows = db.db_all("""
            WITH days AS (
              SELECT generate_series(current_date - interval '6 day',
                                     current_date,
                                     interval '1 day')::date AS d
            )
            SELECT d AS day,
                   COALESCE((
                     SELECT SUM(qty*sell_price)
                     FROM sales s
                     WHERE DATE(s.sold_at) = d
                   ),0) AS revenue
            FROM days
            ORDER BY d
        """)

    sales_labels = [str(r[0]) for r in rows]
    sales_values = [float(r[1] or 0) for r in rows]

    # Stock tracker arrays (optional legacy)
    stock_labels = [it[1] for it in inventory]
    stock_values = [nz_int(it[4]) for it in inventory]

    # --- Sold Items — Today (JOIN for item name) ---
    if using_sqlite:
        sales_today = db.db_all("""
            SELECT s.id,
                   s.item_id,
                   i.name,
                   s.qty        AS quantity,
                   s.sell_price AS sell_price,
                   s.profit     AS profit,
                   s.sold_at    AS sold_at
            FROM sales s
            JOIN inventory i ON i.id = s.item_id
            WHERE DATE(s.sold_at,'localtime') = DATE('now','localtime')
            ORDER BY s.sold_at DESC
        """)
    else:
        sales_today = db.db_all("""
            SELECT s.id,
                   s.item_id,
                   i.name,
                   s.qty        AS quantity,
                   s.sell_price AS sell_price,
                   s.profit     AS profit,
                   s.sold_at    AS sold_at
            FROM sales s
            JOIN inventory i ON i.id = s.item_id
            WHERE DATE(s.sold_at) = CURRENT_DATE
            ORDER BY s.sold_at DESC
        """)

    # FX for footer
    _base, _rates = _derive_rates_from_usd("USD")
    usd_to_aed = _rates.get("AED", 0)
    usd_to_uzs = _rates.get("UZS", 0)

    return render_template(
        "index.html",
        inventory=inventory,
        # state
        search_query=search_query,
        sort_by=sort_by,
        direction=direction,
        selected_filter=selected_filter,
        # totals
        total_quantity=total_quantity,
        total_profit=total_profit,
        # top/low
        top_profit_labels=[it[1] for it in top_profit_items],
        top_profit_values=[float(nz_dec(it[5])) for it in top_profit_items],
        low_stock_labels=[it[1] for it in low_stock_items],
        low_stock_values=[nz_int(it[4]) for it in low_stock_items],
        # charts
        sales_labels=sales_labels,
        sales_values=sales_values,
        stock_labels=stock_labels,
        stock_values=stock_values,
        # sales today table
        sales_today=sales_today,
        # kpis
        today_revenue=today_revenue,
        today_profit=today_profit,
        # fx
        usd_to_aed=usd_to_aed,
        usd_to_uzs=usd_to_uzs,
    )



# ➕ Add Item (UPSERT by name)
@app.post("/add")
def add_item():
    if not is_logged_in():
        return redirect(url_for("login"))

    name_raw = (request.form.get("name") or "").strip()
    if not name_raw:
        flash("Name is required.", "error"); return redirect(url_for("index"))
    name = name_raw.capitalize()

    try:
        quantity = int((request.form.get("quantity") or "").strip())
    except Exception:
        flash("Quantity must be a number.", "error"); return redirect(url_for("index"))
    if quantity <= 0:
        flash("Quantity must be greater than 0.", "error"); return redirect(url_for("index"))

    try:
        buying_price_ui  = parse_money(request.form.get("buying_price"))
        selling_price_ui = parse_money(request.form.get("selling_price"))
        bp_ui, sp_ui = float(buying_price_ui), float(selling_price_ui)
    except Exception:
        flash("Prices must be numeric.", "error"); return redirect(url_for("index"))
    if bp_ui < 0 or sp_ui < 0:
        flash("Prices must be non-negative.", "error"); return redirect(url_for("index"))

    # UI → DB currency
    buying_price  = convert_amount(bp_ui, from_curr=get_curr(), to_curr=BASE_CCY)
    selling_price = convert_amount(sp_ui, from_curr=get_curr(), to_curr=BASE_CCY)

    try:
        existing = db.db_one("SELECT id, quantity FROM inventory WHERE name=:n", {"n": name})
        if existing:
            item_id, existing_qty = existing[0], int(existing[1] or 0)
            new_qty = existing_qty + quantity
            db.db_exec("""
                UPDATE inventory
                   SET buying_price=:bp, selling_price=:sp, quantity=:q, updated_at=CURRENT_TIMESTAMP
                 WHERE id=:id
            """, {"bp": buying_price, "sp": selling_price, "q": new_qty, "id": item_id})
            flash(f"Updated '{name}': quantity +{quantity} → {new_qty}.", "success")
        else:
            db.db_exec("""
                INSERT INTO inventory (name, buying_price, selling_price, quantity)
                VALUES (:n, :bp, :sp, :q)
            """, {"n": name, "bp": buying_price, "sp": selling_price, "q": quantity})
            flash(f"Added '{name}' (qty {quantity}).", "success")
    except Exception as e:
        flash(f"Failed to save item: {e}", "error")

    return redirect(url_for("index"))


# 🛒 Sell Item
@app.post("/sell")
def sell_item():
    if not is_logged_in():
        return redirect(url_for("login"))

    try:
        item_id = int(request.form["item_id"])
        qty     = int(request.form["qty"])
    except Exception:
        flash("Invalid item or quantity.", "error")
        return redirect(url_for("index"))

    # price (UI) → DB currency
    raw_price = request.form.get("sell_price") or request.form.get("price") or request.form.get("sell")
    sell_price_ui = parse_money(raw_price)
    sell_price    = convert_amount(sell_price_ui, from_curr=get_curr(), to_curr=BASE_CCY)

    row = db.db_one("SELECT quantity, buying_price FROM inventory WHERE id=:id", {"id": item_id})
    if not row:
        flash("Item not found!", "error")
        return redirect(url_for("index"))

    stock_qty, buy_price = int(row[0] or 0), float(row[1] or 0)
    if qty <= 0:
        flash("Quantity must be greater than 0.", "error")
        return redirect(url_for("index"))
    if qty > stock_qty:
        flash("Not enough stock!", "error")
        return redirect(url_for("index"))

    profit = (sell_price - buy_price) * qty

    # record sale + reduce stock
    db.db_exec("""
        INSERT INTO sales (item_id, qty, sell_price, profit, sold_at)
        VALUES (:id, :q, :sp, :pf, CURRENT_TIMESTAMP)
    """, {"id": item_id, "q": qty, "sp": sell_price, "pf": profit})
    db.db_exec("UPDATE inventory SET quantity = quantity - :q WHERE id = :id",
               {"q": qty, "id": item_id})

    flash(f"Sold {qty} unit(s). Profit: {fmt_money(profit)}", "success")
    return redirect(url_for("index"))


# ↩️ Return sale (restock + remove record)
@app.post("/sales/<int:sale_id>/return")
def return_sale(sale_id):
    if not is_logged_in():
        return redirect(url_for("login"))
    try:
        sale = db.db_one("SELECT id, item_id, qty FROM sales WHERE id=:id", {"id": sale_id})
        if not sale:
            flash("Sale not found.", "error"); return redirect(url_for("index"))

        qty = int(sale[2] or 0)
        if qty <= 0:
            db.db_exec("DELETE FROM sales WHERE id=:id", {"id": sale_id})
            flash("Sale removed (no quantity to return).", "warning")
            return redirect(url_for("index"))

        inv = db.db_one("SELECT id FROM inventory WHERE id=:id", {"id": sale[1]})
        if not inv:
            flash("Linked inventory item not found.", "error"); return redirect(url_for("index"))

        db.db_exec("UPDATE inventory SET quantity = quantity + :q WHERE id = :id",
                   {"q": qty, "id": sale[1]})
        db.db_exec("DELETE FROM sales WHERE id=:id", {"id": sale_id})
        flash("Item returned to inventory and sale removed.", "success")
    except Exception as e:
        flash(f"Return failed: {e}", "error")
    return redirect(url_for("index"))


# 🗑️ Delete a sale record (no restock)
@app.post("/sales/<int:sale_id>/delete")
def delete_sale(sale_id):
    if not is_logged_in():
        return redirect(url_for("login"))
    db.db_exec("DELETE FROM sales WHERE id=:id", {"id": sale_id})
    flash("Sale record deleted.", "success")
    return redirect(url_for("index"))


# ❌ Delete Item
@app.get("/delete/<int:item_id>")
def delete_item(item_id):
    if not is_logged_in():
        return redirect(url_for("login"))
    db.db_exec("DELETE FROM inventory WHERE id = :id", {"id": item_id})
    flash("Item deleted successfully!", "warning")
    return redirect(url_for("index"))


# ✏️ Edit Item
@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
def edit_item(item_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        name_raw = (request.form.get("name") or "").strip()
        if not name_raw:
            flash("Name is required.", "error"); return redirect(url_for("edit_item", item_id=item_id))
        name = name_raw.capitalize()

        try:
            quantity = int((request.form.get("quantity") or "").strip())
        except Exception:
            flash("Quantity must be a number.", "error"); return redirect(url_for("edit_item", item_id=item_id))
        if quantity < 0:
            flash("Quantity must be ≥ 0.", "error"); return redirect(url_for("edit_item", item_id=item_id))

        try:
            buying_price_ui  = parse_money(request.form.get("buying_price"))
            selling_price_ui = parse_money(request.form.get("selling_price"))
            bp_ui, sp_ui = float(buying_price_ui), float(selling_price_ui)
        except Exception:
            flash("Prices must be numeric.", "error"); return redirect(url_for("edit_item", item_id=item_id))
        if bp_ui < 0 or sp_ui < 0:
            flash("Prices must be non-negative.", "error"); return redirect(url_for("edit_item", item_id=item_id))

        try:
            buying_price  = convert_amount(bp_ui, from_curr=get_curr(), to_curr=BASE_CCY)
            selling_price = convert_amount(sp_ui, from_curr=get_curr(), to_curr=BASE_CCY)
        except Exception as e:
            flash(f"Currency conversion failed: {e}", "error"); return redirect(url_for("edit_item", item_id=item_id))

        try:
            db.db_exec("""
                UPDATE inventory
                   SET name=:n, buying_price=:bp, selling_price=:sp, quantity=:q
                 WHERE id=:id
            """, {"n": name, "bp": buying_price, "sp": selling_price, "q": quantity, "id": item_id})
            flash(f"Item '{name}' updated.", "success")
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Failed to update item: {e}", "error")
            return redirect(url_for("edit_item", item_id=item_id))

    # GET
    item = db.db_one("SELECT * FROM inventory WHERE id=:id", {"id": item_id})
    if not item:
        flash("Item not found!", "error")
        return redirect(url_for("index"))
    return render_template("edit.html", item=item)


# 📊 API — Stock Overview (for advanced chart)
@app.get("/api/stock/overview")
def api_stock_overview():
    # Return JSON even when unauthenticated so the front-end doesn't crash
    if not is_logged_in():
        return jsonify({"items": [], "low_threshold": 5, "totals": {"qty": 0, "value": 0.0}}), 401

    rows = db.db_all("""
        SELECT id, name,
               COALESCE(quantity,0)       AS qty,
               COALESCE(buying_price,0)   AS buy,
               COALESCE(selling_price,0)  AS sell
        FROM inventory
        ORDER BY name
    """)

    items, totals_qty, totals_value = [], 0, 0.0
    low_threshold = 5
    ui = get_curr()

    for r in rows:
        iid, name, qty, buy, sell = int(r[0]), r[1], int(r[2]), float(r[3]), float(r[4])
        value_db = qty * sell
        value_ui = convert_amount(value_db, from_curr=BASE_CCY, to_curr=ui)
        items.append({
            "id": iid, "name": name, "qty": qty,
            "buy": convert_amount(buy,  from_curr=BASE_CCY, to_curr=ui),
            "sell": convert_amount(sell, from_curr=BASE_CCY, to_curr=ui),
            "value": value_ui,
            "profit_per": max(convert_amount(sell - buy, from_curr=BASE_CCY, to_curr=ui), 0),
            "is_low": qty <= low_threshold
        })
        totals_qty   += qty
        totals_value += value_ui

    return jsonify({
        "items": items,
        "low_threshold": low_threshold,
        "totals": {"qty": totals_qty, "value": totals_value}
    })


# 📊 Export to Excel (dual currency) — polished formatting
@app.get("/export")
def export_excel():
    if not is_logged_in():
        return redirect(url_for("login"))

    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.formatting.rule import CellIsRule

    ui_curr = get_curr()
    base_ccy = BASE_CCY
    inventory = get_inventory()

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.title = "Inventory"

    sh["A1"] = "Vanta Inventory Export"
    sh["A2"] = f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    sh["A3"] = f"Stored currency (DB): {base_ccy}"
    sh["A4"] = f"UI currency: {ui_curr}"

    start_row = 6
    headers = [
        "ID", "Name",
        f"Buying ({base_ccy})", f"Selling ({base_ccy})", "Quantity", f"Profit ({base_ccy})",
        f"Buying ({ui_curr})",  f"Selling ({ui_curr})",  f"Profit ({ui_curr})",
    ]

    for c, h in enumerate(headers, start=1):
        cell = sh.cell(row=start_row, column=c, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")  # premium blue header
        cell.alignment = Alignment(horizontal="center", vertical="center")

    sh.freeze_panes = f"A{start_row+1}"
    sh.auto_filter.ref = f"A{start_row}:{get_column_letter(len(headers))}{start_row}"

    fmt_int      = '#,##0'
    fmt_ccy_base = f'#,##0 "{base_ccy}"'
    fmt_ccy_ui   = f'#,##0 "{ui_curr}"'

    rowi = start_row + 1
    first_row = rowi
    for it in inventory:
        _id, name, buy_uzs, sell_uzs, qty, profit_uzs, _curr = it
        buy_ui  = convert_amount(buy_uzs,  from_curr=base_ccy, to_curr=ui_curr)
        sell_ui = convert_amount(sell_uzs, from_curr=base_ccy, to_curr=ui_curr)
        prof_ui = convert_amount(profit_uzs, from_curr=base_ccy, to_curr=ui_curr)

        sh.cell(row=rowi, column=1, value=int(_id))
        sh.cell(row=rowi, column=2, value=name)

        c3 = sh.cell(row=rowi, column=3, value=float(buy_uzs or 0));    c3.number_format = fmt_ccy_base
        c4 = sh.cell(row=rowi, column=4, value=float(sell_uzs or 0));   c4.number_format = fmt_ccy_base
        c5 = sh.cell(row=rowi, column=5, value=int(qty or 0));          c5.number_format = fmt_int
        c6 = sh.cell(row=rowi, column=6, value=float(profit_uzs or 0)); c6.number_format = fmt_ccy_base

        c7 = sh.cell(row=rowi, column=7, value=float(buy_ui or 0));     c7.number_format = fmt_ccy_ui
        c8 = sh.cell(row=rowi, column=8, value=float(sell_ui or 0));    c8.number_format = fmt_ccy_ui
        c9 = sh.cell(row=rowi, column=9, value=float(prof_ui or 0));    c9.number_format = fmt_ccy_ui

        rowi += 1

    last_row = rowi - 1

    sh.cell(row=rowi, column=2, value="TOTALS").font = Font(bold=True)
    t_qty   = sh.cell(row=rowi, column=5, value=f"=SUM(E{first_row}:E{last_row})");  t_qty.number_format   = fmt_int
    t_pB    = sh.cell(row=rowi, column=6, value=f"=SUM(F{first_row}:F{last_row})");  t_pB.number_format    = fmt_ccy_base
    t_pU    = sh.cell(row=rowi, column=9, value=f"=SUM(I{first_row}:I{last_row})");  t_pU.number_format    = fmt_ccy_ui

    thin = Side(style="thin", color="DDDDDD")
    rng = sh[f"A{start_row}:I{rowi}"]
    for rw in rng:
        for c in rw:
            c.border = Border(top=thin, bottom=thin, left=thin, right=thin)

    sh.conditional_formatting.add(
        f"E{first_row}:E{last_row}",
        CellIsRule(operator="lessThanOrEqual", formula=["5"],
                   fill=PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"))
    )

    for col in range(1, len(headers) + 1):
        letter = get_column_letter(col)
        maxlen = 0
        for r in range(1, rowi + 1):
            v = sh.cell(row=r, column=col).value
            vlen = len(str(v)) if v is not None else 0
            maxlen = max(maxlen, vlen)
        sh.column_dimensions[letter].width = min(max(10, maxlen + 2), 42)

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    fname = f"inventory_export_{ui_curr}_and_{base_ccy}.xlsx"
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# 📦 Data backup (ZIP of CSVs, Postgres)
@app.get("/admin/backup")
def admin_backup():
    if not (is_logged_in() and is_admin_user()):
        return redirect(url_for("login"))

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return "DATABASE_URL not set", 500

    try:
        import psycopg2
    except Exception as e:
        return f"psycopg2 not available on this environment: {e}", 500

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    parsed = urlparse(db_url)
    user = parsed.username
    pwd = parsed.password
    host = parsed.hostname
    port = parsed.port or 5432
    dbname = parsed.path.strip("/")

    conn = psycopg2.connect(dbname=dbname, user=user, password=pwd, host=host, port=port)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE'
            ORDER BY table_name;
        """)
        tables = [r[0] for r in cur.fetchall()]

    ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "generated_at_utc": ts,
            "database": dbname,
            "host": host,
            "tables": tables,
            "note": "Data-only backup (CSV per table). Schema ensured at startup.",
        }
        zf.writestr("metadata.json", json.dumps(meta, indent=2))
        for tname in tables:
            with conn.cursor() as c2:
                s = io.StringIO()
                c2.copy_expert(f'COPY (SELECT * FROM "{tname}") TO STDOUT WITH CSV HEADER', s)
                zf.writestr(f"{tname}.csv", s.getvalue())

    conn.close()
    buf.seek(0)
    fname = f"vanta_inventory_backup_{ts}.zip"
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=fname)


# =========================
# Prefs & small APIs
# =========================
@app.get("/api/rates")
def api_rates():
    try:
        base = (request.args.get("base") or get_curr()).upper()
        base, rates = _derive_rates_from_usd(base)
        return jsonify({"base": base, "rates": rates})
    except Exception as e:
        return jsonify({
            "base": "USD",
            "rates": {"USD": 1.0, "AED": 3.6725, "UZS": 12600.0},
            "_note": "fallback",
            "_error": str(e)
        })

@app.get("/api/geo")
def api_geo():
    # Always 200 so the UI doesn't break
    if OFFLINE:
        return jsonify({"country": "US", "languages": "en", "_note": "offline default"})

    try:
        r = requests.get("https://ipapi.co/json", timeout=6)
        r.raise_for_status()
        j = r.json()
        if not isinstance(j, dict):
            raise ValueError("bad geo json")
        return jsonify(j)
    except Exception as e:
        # Fallback and keep status 200
        return jsonify({"country": "US", "languages": "en", "_note": "fallback", "_error": str(e)})

@app.post("/prefs")
def set_prefs():
    lang = (request.form.get("lang") or DEFAULT_LANG).strip()
    curr = (request.form.get("curr") or DEFAULT_CURR).strip().upper()
    session["LANG"] = "uz" if lang == "uz" else "en"
    session["CURR"] = curr if curr in _SUPPORTED else DEFAULT_CURR
    flash(t("preferences_saved", session["LANG"]), "success")
    return redirect(url_for("login"))

@app.post("/settings/currency")
def set_currency():
    cur = (request.form.get("currency") or DEFAULT_CURR).upper()
    if cur not in _SUPPORTED:
        flash("Unsupported currency.", "error")
        return redirect(url_for("index"))
    session["CURR"] = cur
    flash(f"Currency set to {cur}.", "success")
    return redirect(url_for("index"))


# =========================
# Auth pages (hardened)
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().casefold()
        password = (request.form.get("password") or "").strip()

        ok = ADMIN_USERS.get(username) == password
        if ok:
            session["logged_in"] = True
            session["user"] = username
            flash("Welcome back.", "success")
            return redirect(url_for("index"))

        if app.debug:
            app.logger.info(f"[login] failed for user='{username}'  known={list(ADMIN_USERS.keys())}")
        flash("Invalid username or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html", APP_VERSION=get_version())

@app.get("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("user", None)
    flash("You’ve been logged out.", "success")
    return redirect(url_for("login"))

@app.get("/forgot")
def forgot_password():
    return render_template("forgot.html", APP_VERSION=get_version())

@app.post("/forgot")
def forgot_password_post():
    email = (request.form.get("email") or "").strip()
    if not email:
        flash("Please enter your email.", "error")
        return redirect(url_for("forgot_password"))
    # TODO: Implement email reset flow
    flash("If that email exists, we’ve sent reset instructions.", "success")
    return redirect(url_for("login"))


@app.get("/__debug/now")
def __debug_now():
    using_sqlite = db.DATABASE_URL.startswith("sqlite")
    server_now = datetime.utcnow().isoformat() + "Z"
    if using_sqlite:
        r = db.db_one("SELECT datetime('now'), date('now')")
        return jsonify({"server_utc": server_now, "sqlite_datetime_now": r[0], "sqlite_date_now": r[1]})
    else:
        r = db.db_one("SELECT NOW() AT TIME ZONE 'UTC', CURRENT_DATE")
        return jsonify({"server_utc": server_now, "pg_now_utc": str(r[0]), "pg_current_date": str(r[1])})

@app.get("/__debug/sales")
def __debug_sales():
    rows = db.db_all("SELECT id, item_id, qty, sell_price, profit, sold_at FROM sales ORDER BY id DESC LIMIT 10")
    return jsonify([{
        "id": r[0], "item_id": r[1], "qty": r[2], "sell_price": float(r[3] or 0),
        "profit": float(r[4] or 0), "sold_at": str(r[5])
    } for r in rows])

@app.post("/__admin/wipe")
def __admin_wipe():
    # dev-only guard: must be logged in AND in debug
    if not (app.debug and is_logged_in()):
        return "Forbidden", 403
    try:
        db.db_exec("DELETE FROM sales")
        db.db_exec("DELETE FROM inventory")
        if db.DATABASE_URL.startswith("sqlite"):
            # shrink file
            db.db_exec("VACUUM")
        flash("Local DB wiped.", "success")
    except Exception as e:
        flash(f"Failed to wipe DB: {e}", "error")
    return redirect(url_for("index"))

@app.get("/__debug_sales_today")
def __debug_sales_today():
    using_sqlite = db.DATABASE_URL.startswith("sqlite")
    if using_sqlite:
        q = """
        SELECT COUNT(*), COALESCE(SUM(qty*sell_price),0), COALESCE(SUM(profit),0)
        FROM sales
        WHERE sold_at >= DATETIME('now','start of day')
          AND sold_at <  DATETIME('now','start of day','+1 day')
        """
    else:
        q = """
        SELECT COUNT(*), COALESCE(SUM(qty*sell_price),0), COALESCE(SUM(profit),0)
        FROM sales
        WHERE sold_at >= CURRENT_DATE
          AND sold_at <  CURRENT_DATE + INTERVAL '1 day'
        """
    row = db.db_one(q)
    return {"rows": row[0], "revenue_base": float(row[1] or 0), "profit_base": float(row[2] or 0)}


# =========================
# Dev entry
# =========================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=(ENV=="dev"))
