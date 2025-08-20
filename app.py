# app.py — Vanta Inventory (FINAL, merged, advanced)
# - Cleaned imports & datetime usage
# - Robust currency/i18n helpers (USD/AED/UZS)
# - Search + filter + 6-way sort (server param → in-memory)
# - Sold Items (Today) with Return (restock) & Delete
# - Excel export (dual currency) + DB backup (CSV ZIP)
# - Health/version + GEO/Rates APIs
# - Login/logout + edit/add/sell
# - Works with sqlite or Postgres via database_sqlalchemy

import os, io, time, json, zipfile, logging, sys
from decimal import Decimal
from urllib.parse import urlparse

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, jsonify, g
)

# Optional Babel currency formatting
try:
    from babel.numbers import format_currency as _format_currency
except Exception:
    def _format_currency(value, currency, locale=None):
        try:
            return f"{float(value or 0):,.2f} {currency}"
        except Exception:
            return f"{value} {currency}"

import requests

# Your DB helpers (must expose db_all, db_one, db_exec, DATABASE_URL)
import database_sqlalchemy as db
from database_sqlalchemy import ensure_schema
from i18n import t

import sqlite3  # kept for local helpers (optional)
from datetime import datetime, date

# =========================
# Optional local sqlite helpers
# =========================
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "local.db"))

def get_conn():
    """Local sqlite connector (not used by main path, kept for local ops if needed)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_today_bounds():
    today = date.today()
    start = datetime.combine(today, datetime.min.time()).isoformat()
    end   = datetime.combine(today, datetime.max.time()).isoformat()
    return start, end


# =========================
# Currency / i18n helpers
# =========================
BASE_CCY = "UZS"          # Stored DB currency
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

# Live USD-based FX with caching (1 USD = rates[currency])
_FX_CACHE = {"rates": None, "ts": 0}
def _fetch_usd_rates():
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

    _FX_CACHE.update({"rates": rates, "ts": now})
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
    # amount[from_curr] -> USD -> to_curr
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

# Legacy numeric helpers (renamed to avoid clashing with Jinja filter name)
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
# App bootstrap
# =========================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")

# Logging (works on Render)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Ensure DB schema
with app.app_context():
    try:
        ensure_schema()
        app.logger.info("✅ Database schema ensured at startup.")
    except Exception:
        app.logger.exception("⚠️ Failed to ensure schema")

# Global error handler
@app.errorhandler(Exception)
def handle_error(e):
    app.logger.exception("Unhandled exception")
    return "Internal Server Error", 500

# Jinja filters / context
@app.before_request
def _inject_currency():
    g.CURRENCY = get_curr()

@app.after_request
def _force_utf8(resp):
    if resp.content_type and resp.content_type.startswith("text/html"):
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@app.template_filter("ccy")
def ccy(amount):
    # Convert from DB currency -> current UI currency.
    return convert_amount(amount, from_curr=BASE_CCY, to_curr=get_curr())

@app.template_filter("fmtmoney")
def fmtmoney(amount):
    return fmt_money(amount, curr=get_curr(), lang=get_lang())

# Back-compat: 'money' filter → currency formatter
app.jinja_env.filters["money"] = fmtmoney

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


# =========================
# Version / Health
# =========================
def get_version():
    try:
        return open("VERSION", encoding="utf-8").read().strip()
    except Exception:
        return "dev"

@app.context_processor
def inject_version():
    return {"APP_VERSION": get_version()}

@app.get("/__health")
def __health():
    return jsonify(status="ok", version=get_version()), 200


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
# Auth
# =========================
ADMIN_USERS_ENV = os.environ.get("ADMIN_USERS")
if ADMIN_USERS_ENV:
    ADMIN_USERS = dict(pair.split(":", 1) for pair in ADMIN_USERS_ENV.split(","))
else:
    ADMIN_USERS = {"vanta": "beastmode", "jasur": "jasur2025"}

def is_logged_in():
    return bool(session.get("logged_in"))

# Admin allowlist
ADMIN_ADMINS_ENV = os.environ.get("ADMIN_ADMINS")
if ADMIN_ADMINS_ENV:
    ADMIN_ADMINS = {u.strip() for u in ADMIN_ADMINS_ENV.split(",") if u.strip()}
else:
    ADMIN_ADMINS = set(ADMIN_USERS.keys())

def is_admin_user():
    return session.get("user") in ADMIN_ADMINS


# =========================
# Data access
# =========================
def get_inventory():
    # Ensure profit never NULL at source
    rows = db.db_all("""
        SELECT id,
               name,
               buying_price,
               selling_price,
               quantity,
               COALESCE(profit, (selling_price - buying_price) * quantity, 0) AS profit,
               COALESCE(currency, 'UZS') AS currency
        FROM inventory
        ORDER BY id
    """)
    return [tuple(r) for r in rows]


# =========================
# Routes
# =========================
@app.route("/")
def index():
    if not is_logged_in():
        return redirect(url_for("login"))

    # ---------- params ----------
    search_query    = (request.values.get("search", "") or "").strip().lower()
    selected_filter = request.values.get("filter", "")
    sort_by         = request.args.get("sort_by", "id")
    direction       = request.args.get("direction", "asc")

    # Map ?sort=name_asc|name_desc|qty_asc|qty_desc|price_asc|price_desc → in-memory sorter
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

    # ---------- data ----------
    inventory = get_inventory()  # (id, name, buy, sell, qty, profit, currency)
    using_sqlite = db.DATABASE_URL.startswith("sqlite")

    # ---------- today revenue/profit ----------
    if using_sqlite:
        # IMPORTANT: convert stored UTC timestamp to localtime for day matching
        row = db.db_one("""
            SELECT COALESCE(SUM(qty*sell_price),0), COALESCE(SUM(profit),0)
            FROM sales
            WHERE DATE(sold_at, 'localtime') = DATE('now','localtime')
        """)
    else:
        row = db.db_one("""
            SELECT COALESCE(SUM(qty*sell_price),0), COALESCE(SUM(profit),0)
            FROM sales s WHERE DATE(s.sold_at)=CURRENT_DATE
        """)
    today_revenue, today_profit = (row[0] if row else 0), (row[1] if row else 0)

    # ---------- filtering ----------
    if search_query:
        inventory = [it for it in inventory if search_query in (it[1] or "").lower()]
    if selected_filter == "low_stock":
        inventory = [it for it in inventory if (it[4] or 0) <= 5]
    elif selected_filter == "high_profit":
        inventory = [it for it in inventory if (it[5] or 0) >= 100]

    # ---------- sorting (None-safe) ----------
    sort_map = {"name": 1, "quantity": 4, "profit": 5, "price": 3}
    if sort_by in sort_map:
        idx = sort_map[sort_by]
        inventory = sorted(
            inventory,
            key=lambda x: (x[idx] is None, x[idx]),
            reverse=(direction == "desc"),
        )

    # ---------- totals (None-safe) ----------
    def nz_dec(x): return x if x is not None else Decimal(0)
    def nz_int(x): return x if x is not None else 0

    total_quantity = sum(nz_int(it[4]) for it in inventory)
    total_profit   = sum(nz_dec(it[5]) for it in inventory)

    # ---------- top/low lists ----------
    top_profit_items = sorted(inventory, key=lambda x: (x[5] is None, x[5]), reverse=True)[:5]
    low_stock_items  = sorted(inventory, key=lambda x: (x[4] is None, x[4]))[:5]

    # ---------- last 7 days revenue ----------
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
                   COALESCE((SELECT SUM(qty*sell_price)
                             FROM sales s
                             WHERE DATE(s.sold_at, 'localtime') = d),0) AS revenue
            FROM days
        """)
    else:
        rows = db.db_all("""
            WITH days AS (
              SELECT generate_series(current_date - interval '6 day', current_date, interval '1 day')::date AS d
            )
            SELECT d AS day,
                   COALESCE((SELECT SUM(qty*sell_price) FROM sales s WHERE DATE(s.sold_at)=d),0) AS revenue
            FROM days
            ORDER BY d
        """)

    sales_labels = [str(r[0]) for r in rows]
    sales_values = [float(r[1] or 0) for r in rows]

    # ---------- stock tracker ----------
    stock_labels = [it[1] for it in inventory]
    stock_values = [nz_int(it[4]) for it in inventory]

    # ---------- Sold Items — Today (JOIN for item name; alias qty→quantity) ----------
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
            WHERE DATE(s.sold_at, 'localtime') = DATE('now','localtime')
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

    # ---------- FX for footer ----------
    _base, _rates = _derive_rates_from_usd("USD")
    usd_to_aed = _rates.get("AED", 0)
    usd_to_uzs = _rates.get("UZS", 0)

    return render_template(
        "index.html",
        inventory=inventory,
        # filters/sort state
        search_query=search_query,
        sort_by=sort_by,
        direction=direction,
        selected_filter=selected_filter,
        # totals
        total_quantity=total_quantity,
        total_profit=total_profit,
        # top/low lists
        top_profit_labels=[it[1] for it in top_profit_items],
        top_profit_values=[float(nz_dec(it[5])) for it in top_profit_items],
        low_stock_labels=[it[1] for it in low_stock_items],
        low_stock_values=[nz_int(it[4]) for it in low_stock_items],
        # charts
        sales_labels=sales_labels,
        sales_values=sales_values,
        stock_labels=stock_labels,
        stock_values=stock_values,
        # today sales block
        sales_today=sales_today,
        # today totals
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


# 🛒 Sell Item  (FINAL)
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

    # price comes from UI currency → convert to DB currency (UZS)
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

    # profit uses *unit* sell_price as stored in DB; revenue is qty*sell_price in queries
    profit = (sell_price - buy_price) * qty

    # 1) record sale WITH TIMESTAMP
    db.db_exec("""
        INSERT INTO sales (item_id, qty, sell_price, profit, sold_at)
        VALUES (:id, :q, :sp, :pf, CURRENT_TIMESTAMP)
    """, {"id": item_id, "q": qty, "sp": sell_price, "pf": profit})

    # 2) reduce stock
    db.db_exec("UPDATE inventory SET quantity = quantity - :q WHERE id = :id",
               {"q": qty, "id": item_id})

    flash(f"Sold {qty} unit(s). Profit: {fmt_money(profit)}", "success")
    return redirect(url_for("index"))


# ↩️ Return a sale: restock inventory + remove sale
@app.post("/sales/<int:sale_id>/return")
def return_sale(sale_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    try:
        sale = db.db_one("SELECT id, item_id, qty FROM sales WHERE id=:id", {"id": sale_id})
        if not sale:
            flash("Sale not found.", "error")
            return redirect(url_for("index"))

        qty = int(sale[2] or 0)
        if qty <= 0:
            db.db_exec("DELETE FROM sales WHERE id=:id", {"id": sale_id})
            flash("Sale record removed (no quantity to return).", "warning")
            return redirect(url_for("index"))

        inv = db.db_one("SELECT id FROM inventory WHERE id=:id", {"id": sale[1]})
        if not inv:
            flash("Linked inventory item not found — sale not returned.", "error")
            return redirect(url_for("index"))

        db.db_exec("UPDATE inventory SET quantity = quantity + :q WHERE id = :id",
                   {"q": qty, "id": sale[1]})
        db.db_exec("DELETE FROM sales WHERE id=:id", {"id": sale_id})

        flash("Item returned to inventory and removed from today's sales.", "success")
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


# 📊 Export to Excel (dual currency: UZS + UI currency)
@app.get("/export")
def export_excel():
    if not is_logged_in():
        return redirect(url_for("login"))

    import openpyxl

    ui_curr = get_curr()
    base_ccy = BASE_CCY
    inventory = get_inventory()  # (id, name, buy, sell, qty, profit, currency)

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
    sh.append([""] * len(headers))
    for c, h in enumerate(headers, start=1):
        sh.cell(row=start_row, column=c, value=h)

    rowi = start_row + 1
    total_qty = 0
    total_profit_uzs = 0.0
    total_profit_ui = 0.0

    for it in inventory:
        _id, name, buy_uzs, sell_uzs, qty, profit_uzs, _curr = it

        buy_ui  = convert_amount(buy_uzs,  from_curr=base_ccy, to_curr=ui_curr)
        sell_ui = convert_amount(sell_uzs, from_curr=base_ccy, to_curr=ui_curr)
        prof_ui = convert_amount(profit_uzs, from_curr=base_ccy, to_curr=ui_curr)

        sh.cell(row=rowi, column=1, value=_id)
        sh.cell(row=rowi, column=2, value=name)
        sh.cell(row=rowi, column=3, value=float(buy_uzs or 0))
        sh.cell(row=rowi, column=4, value=float(sell_uzs or 0))
        sh.cell(row=rowi, column=5, value=int(qty or 0))
        sh.cell(row=rowi, column=6, value=float(profit_uzs or 0))
        sh.cell(row=rowi, column=7, value=float(buy_ui or 0))
        sh.cell(row=rowi, column=8, value=float(sell_ui or 0))
        sh.cell(row=rowi, column=9, value=float(prof_ui or 0))

        total_qty += int(qty or 0)
        total_profit_uzs += float(profit_uzs or 0)
        total_profit_ui  += float(prof_ui or 0)
        rowi += 1

    # Totals row
    sh.cell(row=rowi, column=2, value="TOTALS")
    sh.cell(row=rowi, column=5, value=total_qty)
    sh.cell(row=rowi, column=6, value=total_profit_uzs)
    sh.cell(row=rowi, column=9, value=total_profit_ui)

    # Basic formatting
    from openpyxl.styles import Font
    header_row = start_row
    for col in range(1, len(headers) + 1):
        sh.cell(row=header_row, column=col).font = Font(bold=True)
    for col in [2, 5, 6, 9]:
        sh.cell(row=rowi, column=col).font = Font(bold=True)

    # Autosize columns
    from openpyxl.utils import get_column_letter
    for col in range(1, len(headers) + 1):
        letter = get_column_letter(col)
        maxlen = 0
        for r in range(1, rowi + 1):
            v = sh.cell(row=r, column=col).value
            vlen = len(str(v)) if v is not None else 0
            maxlen = max(maxlen, vlen)
        sh.column_dimensions[letter].width = min(max(10, maxlen + 2), 40)

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    fname = f"inventory_export_{ui_curr}_and_{base_ccy}.xlsx"
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# 📦 Data backup (ZIP of CSVs)
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
        for t in tables:
            with conn.cursor() as c2:
                s = io.StringIO()
                c2.copy_expert(f'COPY (SELECT * FROM "{t}") TO STDOUT WITH CSV HEADER', s)
                zf.writestr(f"{t}.csv", s.getvalue())

    conn.close()
    buf.seek(0)
    fname = f"vanta_inventory_backup_{ts}.zip"
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=fname)


# =========================
# Prefs / small APIs
# =========================
@app.get("/api/rates")
def api_rates():
    base = (request.args.get("base") or get_curr()).upper()
    base, rates = _derive_rates_from_usd(base)
    return jsonify({"base": base, "rates": rates})

@app.get("/api/geo")
def api_geo():
    try:
        r = requests.get("https://ipapi.co/json", timeout=6)
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 502

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
# Auth routes
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if ADMIN_USERS.get(username) == password:
            session["logged_in"] = True
            session["user"] = username
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.get("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("user", None)
    return redirect(url_for("login"))


# =========================
# Local dev entry
# =========================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=True)
