import os, io, time, json, zipfile, datetime
from urllib.parse import urlparse

import requests
import openpyxl
import psycopg2
from sqlalchemy.exc import IntegrityError  # keep if you actually use it

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify, g

# Babel (optional)
try:
    from babel.numbers import format_currency as _format_currency
except Exception:
    def _format_currency(value, currency, locale=None):
        try:
            return f"{float(value or 0):,.2f} {currency}"
        except Exception:
            return f"{value} {currency}"

import database_sqlalchemy as db
from database_sqlalchemy import ensure_schema
from i18n import t


# =========================
# Currency / i18n
# =========================
BASE_CCY = "UZS"   # set to "UZS" if DB rows are UZS
DEFAULT_LANG = "en"
DEFAULT_CURR = "USD"

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

# Robust USD-based FX
_SUPPORTED = {"USD", "AED", "UZS"}
_FX_CACHE = {"rates": None, "ts": 0}  # 1 USD = R[currency]

def _fetch_usd_rates():
    """
    Return a dict like {'USD':1.0,'AED':3.67,'UZS':12600} for 1 USD = X.
    Tries multiple providers, caches ~1h, and never returns missing keys.
    """
    now = time.time()
    if _FX_CACHE["rates"] and (now - _FX_CACHE["ts"]) < 3600:
        return _FX_CACHE["rates"]

    providers = []
    providers.append((
        "exchangerate.host",
        lambda: requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": "USD,AED,UZS"},
            headers={"User-Agent": "VantaInventory/1.0"},
            timeout=8,
        ).json().get("rates", {})
    ))
    providers.append((
        "open.er-api.com",
        lambda: requests.get(
            "https://open.er-api.com/v6/latest/USD",
            headers={"User-Agent": "VantaInventory/1.0"},
            timeout=8,
        ).json().get("rates", {})
    ))
    providers.append((
        "frankfurter.app",
        lambda: requests.get(
            "https://api.frankfurter.dev/v1/latest",
            params={"from": "USD", "to": "AED,USD,UZS"},
            headers={"User-Agent": "VantaInventory/1.0"},
            timeout=8,
        ).json().get("rates", {})
    ))

    rates = None
    for name, fn in providers:
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
    """amount[from_curr] -> USD -> to_curr"""
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

# =========================
# App setup
# =========================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")

# ✅ Ensure DB schema once at startup
with app.app_context():
    try:
        ensure_schema()
        print("✅ Database schema ensured at startup.")
    except Exception as e:
        print(f"⚠️ Failed to ensure schema: {e}")

@app.before_request
def _inject_currency():
    g.CURRENCY = get_curr()

@app.template_filter("ccy")
def ccy(amount):
    """Convert from DB currency -> current UI currency."""
    return convert_amount(amount, from_curr=BASE_CCY, to_curr=get_curr())

@app.template_filter("fmtmoney")
def fmtmoney(amount):
    return fmt_money(amount, curr=get_curr(), lang=get_lang())

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
        "t": lambda key: t(key, lang),
    }

# APIs used by the prefs panel
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

# Prefs (language + currency)
@app.post("/prefs")
def set_prefs():
    lang = (request.form.get("lang") or DEFAULT_LANG).strip()
    curr = (request.form.get("curr") or DEFAULT_CURR).strip().upper()
    session["LANG"] = "uz" if lang == "uz" else "en"
    session["CURR"] = curr if curr in _SUPPORTED else DEFAULT_CURR
    flash(t("preferences_saved", session["LANG"]), "success")
    return redirect(url_for("login"))

# Legacy currency setter (kept; writes CURR)
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
# Money helpers (legacy)
# =========================
def money(v, decimals=0):
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

app.jinja_env.filters["money"] = money


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
# Env config
# =========================
ENV = os.getenv("ENV", "dev").lower()
if ENV == "dev":
    app.config.update(
        DEBUG=True,
        TEMPLATES_AUTO_RELOAD=True,
        SERVER_NAME=None,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE="Lax",
    )
else:
    app.config.update(
        TEMPLATES_AUTO_RELOAD=False,
        SEND_FILE_MAX_AGE_DEFAULT=31536000,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
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

# =========================
# Data access
# =========================
def get_inventory():
    rows = db.db_all("""
        SELECT id, name, buying_price, selling_price, quantity, profit,
               COALESCE(currency, 'UZS') AS currency
        FROM inventory
        ORDER BY id
    """)
    return [tuple(r) for r in rows]

# =========================
# Routes
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Filters
    search_query    = (request.values.get("search", "") or "").strip().lower()
    selected_filter = request.values.get("filter", "")
    sort_by         = request.args.get("sort_by", "id")
    direction       = request.args.get("direction", "asc")

    inventory = get_inventory()  # tuples: (id, name, buy, sell, qty, profit, currency)
    using_sqlite = db.DATABASE_URL.startswith("sqlite")

    # Today revenue/profit
    if using_sqlite:
        row = db.db_one("""
            SELECT COALESCE(SUM(qty*sell_price),0), COALESCE(SUM(profit),0)
            FROM sales WHERE DATE(sold_at)=DATE('now','localtime')
        """)
    else:
        row = db.db_one("""
            SELECT COALESCE(SUM(qty*sell_price),0), COALESCE(SUM(profit),0)
            FROM sales s WHERE DATE(s.sold_at)=CURRENT_DATE
        """)
    today_revenue, today_profit = (row[0] if row else 0), (row[1] if row else 0)

    # Filter
    if search_query:
        inventory = [it for it in inventory if search_query in (it[1] or "").lower()]
    if selected_filter == "low_stock":
        inventory = [it for it in inventory if it[4] <= 5]
    elif selected_filter == "high_profit":
        inventory = [it for it in inventory if it[5] >= 100]

    # Sort
    sort_map = {"name": 1, "quantity": 4, "profit": 5}
    if sort_by in sort_map:
        idx = sort_map[sort_by]
        inventory = sorted(inventory, key=lambda x: x[idx], reverse=(direction == "desc"))

    total_quantity = sum(it[4] for it in inventory)
    total_profit   = sum(it[5] for it in inventory)

    # Top 5 / Low 5
    top_profit_items = sorted(inventory, key=lambda x: x[5], reverse=True)[:5]
    low_stock_items  = sorted(inventory, key=lambda x: x[4])[:5]

    # Last 7 days revenue
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
                   COALESCE((SELECT SUM(qty*sell_price) FROM sales s WHERE DATE(s.sold_at)=d),0) AS revenue
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

    # Stock tracker
    stock_labels = [it[1] for it in inventory]
    stock_values = [it[4] for it in inventory]

    # Footer live rates (server-rendered)
    _base, _rates = _derive_rates_from_usd("USD")
    usd_to_aed = _rates.get("AED", 0)
    usd_to_uzs = _rates.get("UZS", 0)

    return render_template(
        "index.html",
        inventory=inventory,
        total_quantity=total_quantity,
        total_profit=total_profit,
        search_query=search_query,
        sort_by=sort_by,
        direction=direction,
        selected_filter=selected_filter,
        top_profit_labels=[it[1] for it in top_profit_items],
        top_profit_values=[it[5] for it in top_profit_items],
        low_stock_labels=[it[1] for it in low_stock_items],
        low_stock_values=[it[4] for it in low_stock_items],
        today_revenue=today_revenue,
        today_profit=today_profit,
        sales_labels=sales_labels,
        sales_values=sales_values,
        stock_labels=stock_labels,
        stock_values=stock_values,
        usd_to_aed=usd_to_aed,
        usd_to_uzs=usd_to_uzs,
    )

# ➕ Add Item (UPSERT by name) — portable for SQLite & Postgres
@app.post("/add")
def add_item():
    if not is_logged_in():
        return redirect(url_for("login"))

    # ---- Name ----
    name_raw = (request.form.get("name") or "").strip()
    if not name_raw:
        flash("Name is required.", "error")
        return redirect(url_for("index"))
    name = name_raw.capitalize()

    # ---- Quantity ----
    quantity_raw = (request.form.get("quantity") or "").strip()
    try:
        quantity = int(quantity_raw)
    except Exception:
        flash("Quantity must be a number.", "error")
        return redirect(url_for("index"))
    if quantity <= 0:
        flash("Quantity must be greater than 0.", "error")
        return redirect(url_for("index"))

    # ---- Prices from UI → numbers ----
    try:
        buying_price_ui  = parse_money(request.form.get("buying_price"))
        selling_price_ui = parse_money(request.form.get("selling_price"))
    except Exception as e:
        flash(f"Could not read prices: {e}", "error")
        return redirect(url_for("index"))

    if buying_price_ui is None or selling_price_ui is None:
        flash("Buying and selling prices are required.", "error")
        return redirect(url_for("index"))

    try:
        bp_ui = float(buying_price_ui)
        sp_ui = float(selling_price_ui)
    except Exception:
        flash("Prices must be numeric.", "error")
        return redirect(url_for("index"))

    if bp_ui < 0 or sp_ui < 0:
        flash("Prices must be non-negative.", "error")
        return redirect(url_for("index"))

    # ---- Currency conversion (UI → BASE_CCY) ----
    try:
        buying_price  = convert_amount(bp_ui, from_curr=get_curr(), to_curr=BASE_CCY)
        selling_price = convert_amount(sp_ui, from_curr=get_curr(), to_curr=BASE_CCY)
    except Exception as e:
        flash(f"Currency conversion failed: {e}", "error")
        return redirect(url_for("index"))

    # ---- UPSERT via db layer (let DB defaults handle timestamps) ----
    try:
        existing = db.db_one("SELECT id, quantity FROM inventory WHERE name=:n", {"n": name})
        if existing:
            item_id, existing_qty = existing[0], (existing[1] or 0)
            new_qty = existing_qty + quantity
            db.db_exec(
                """
                UPDATE inventory
                   SET buying_price=:bp,
                       selling_price=:sp,
                       quantity=:q,
                       updated_at=CURRENT_TIMESTAMP
                 WHERE id=:id
                """,
                {"bp": buying_price, "sp": selling_price, "q": new_qty, "id": item_id},
            )
            flash(f"Updated '{name}': quantity +{quantity} → {new_qty}.", "success")
        else:
            db.db_exec(
                """
                INSERT INTO inventory (name, buying_price, selling_price, quantity)
                VALUES (:n, :bp, :sp, :q)
                """,
                {"n": name, "bp": buying_price, "sp": selling_price, "q": quantity},
            )
            flash(f"Added '{name}' (qty {quantity}).", "success")
    except Exception as e:
        flash(f"Failed to save item: {e}", "error")

    return redirect(url_for("index"))



@app.post("/sell")
def sell_item():
    if not is_logged_in():
        return redirect(url_for("login"))

    item_id = int(request.form["item_id"])
    qty     = int(request.form["qty"])

    # get the UI price from any of these field names
    raw = request.form.get("sell_price") or request.form.get("price") or request.form.get("sell")
    sell_price_ui = parse_money(raw)
    sell_price    = convert_amount(sell_price_ui, from_curr=get_curr(), to_curr=BASE_CCY)  # store in UZS

    row = db.db_one("SELECT quantity, buying_price FROM inventory WHERE id=:id", {"id": item_id})
    if not row:
        flash("Item not found!", "error")
        return redirect(url_for("index"))

    stock_qty, buy_price = int(row[0]), float(row[1])
    if qty > stock_qty:
        flash("Not enough stock!", "error")
        return redirect(url_for("index"))

    profit = (sell_price - buy_price) * qty
    db.db_exec(
        "INSERT INTO sales (item_id, qty, sell_price, profit) VALUES (:id, :q, :sp, :pf)",
        {"id": item_id, "q": qty, "sp": sell_price, "pf": profit},
    )
    db.db_exec("UPDATE inventory SET quantity = quantity - :q WHERE id = :id", {"q": qty, "id": item_id})

    flash(f"Sold {qty} unit(s). Profit: {fmt_money(profit)}", "success")
    return redirect(url_for("index"))


# ❌ Delete Item
@app.get("/delete/<int:item_id>")
def delete_item(item_id):
    if not is_logged_in():
        return redirect(url_for("login"))
    db.db_exec("DELETE FROM inventory WHERE id = :id", {"id": item_id})
    flash("Item deleted successfully!", "warning")
    return redirect(url_for("index"))

# 🔐 Login/Logout
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

# ✏️ Edit Item
@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
def edit_item(item_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        # ---- Name ----
        name_raw = (request.form.get("name") or "").strip()
        if not name_raw:
            flash("Name is required.", "error")
            return redirect(url_for("edit_item", item_id=item_id))
        name = name_raw.capitalize()

        # ---- Quantity ----
        quantity_raw = (request.form.get("quantity") or "").strip()
        try:
            quantity = int(quantity_raw)
        except Exception:
            flash("Quantity must be a number.", "error")
            return redirect(url_for("edit_item", item_id=item_id))
        if quantity < 0:
            flash("Quantity must be ≥ 0.", "error")
            return redirect(url_for("edit_item", item_id=item_id))

        # ---- Prices (UI currency → numbers) ----
        try:
            buying_price_ui  = parse_money(request.form.get("buying_price"))
            selling_price_ui = parse_money(request.form.get("selling_price"))
        except Exception as e:
            flash(f"Could not read prices: {e}", "error")
            return redirect(url_for("edit_item", item_id=item_id))

        if buying_price_ui is None or selling_price_ui is None:
            flash("Buying and selling prices are required.", "error")
            return redirect(url_for("edit_item", item_id=item_id))

        try:
            bp_ui = float(buying_price_ui)
            sp_ui = float(selling_price_ui)
        except Exception:
            flash("Prices must be numeric.", "error")
            return redirect(url_for("edit_item", item_id=item_id))

        if bp_ui < 0 or sp_ui < 0:
            flash("Prices must be non-negative.", "error")
            return redirect(url_for("edit_item", item_id=item_id))

        # Optional sanity check (warning only)
        # if sp_ui < bp_ui:
        #     flash("Selling price is below buying price.", "warning")

        # ---- Currency conversion (UI → BASE_CCY) ----
        try:
            from_curr = get_curr()
            to_curr   = BASE_CCY
            buying_price  = convert_amount(bp_ui, from_curr=from_curr, to_curr=to_curr)
            selling_price = convert_amount(sp_ui, from_curr=from_curr, to_curr=to_curr)
        except Exception as e:
            flash(f"Currency conversion failed: {e}", "error")
            return redirect(url_for("edit_item", item_id=item_id))

        # ---- Persist ----
        try:
            db.db_exec(
                """
                UPDATE inventory
                   SET name=:n,
                       buying_price=:bp,
                       selling_price=:sp,
                       quantity=:q
                 WHERE id=:id
                """,
                {"n": name, "bp": buying_price, "sp": selling_price, "q": quantity, "id": item_id},
            )
            flash(f"Item '{name}' updated.", "success")
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Failed to update item: {e}", "error")
            return redirect(url_for("edit_item", item_id=item_id))

    # ---- GET ----
    item = db.db_one("SELECT * FROM inventory WHERE id=:id", {"id": item_id})
    if not item:
        flash("Item not found!", "error")
        return redirect(url_for("index"))

    return render_template("edit.html", item=item)



# 📤 Export to Excel (dual currency: UZS + current UI currency)
@app.get("/export")
def export_excel():
    if not is_logged_in():
        return redirect(url_for("login"))

    ui_curr = get_curr()          # e.g. USD/AED/UZS
    base_ccy = BASE_CCY           # "UZS"
    inventory = get_inventory()   # (id, name, buy, sell, qty, profit, currency)

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.title = "Inventory"

    # Meta block
    sh["A1"] = "Vanta Inventory Export"
    sh["A2"] = f"Generated at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    sh["A3"] = f"Stored currency (DB): {base_ccy}"
    sh["A4"] = f"UI currency: {ui_curr}"
    start_row = 6

    # Headers
    headers = [
        "ID",
        "Name",
        f"Buying ({base_ccy})",
        f"Selling ({base_ccy})",
        "Quantity",
        f"Profit ({base_ccy})",
        f"Buying ({ui_curr})",
        f"Selling ({ui_curr})",
        f"Profit ({ui_curr})",
    ]
    sh.append([""] * len(headers))  # row 5 spacer
    sh.cell(row=start_row, column=1, value=headers[0])
    for c, h in enumerate(headers, start=1):
        sh.cell(row=start_row, column=c, value=h)

    # Data rows
    rowi = start_row + 1
    total_qty = 0
    total_profit_uzs = 0.0
    total_profit_ui = 0.0

    for it in inventory:
        _id, name, buy_uzs, sell_uzs, qty, profit_uzs, _curr = it

        # Convert DB (UZS) → UI currency
        buy_ui   = convert_amount(buy_uzs,  from_curr=base_ccy, to_curr=ui_curr)
        sell_ui  = convert_amount(sell_uzs, from_curr=base_ccy, to_curr=ui_curr)
        prof_ui  = convert_amount(profit_uzs, from_curr=base_ccy, to_curr=ui_curr)

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

    # Basic formatting: bold headers & totals, autosize columns
    header_row = start_row
    for col in range(1, len(headers) + 1):
        sh.cell(row=header_row, column=col).font = openpyxl.styles.Font(bold=True)
    for col in [2, 5, 6, 9]:
        sh.cell(row=rowi, column=col).font = openpyxl.styles.Font(bold=True)

    # Autosize columns
    for col in range(1, len(headers) + 1):
        letter = openpyxl.utils.get_column_letter(col)
        maxlen = 0
        for r in range(1, rowi + 1):
            v = sh.cell(row=r, column=col).value
            vlen = len(str(v)) if v is not None else 0
            maxlen = max(maxlen, vlen)
        sh.column_dimensions[letter].width = min(max(10, maxlen + 2), 40)

    # Save to buffer
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"inventory_export_{ui_curr}_and_{base_ccy}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# 📦 One-click data backup (ZIP of CSVs)
@app.get("/admin/backup")
def admin_backup():
    if not is_logged_in():
        return redirect(url_for("login"))

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return "DATABASE_URL not set", 500

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

    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
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
# Local dev entry
# =========================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=True)
