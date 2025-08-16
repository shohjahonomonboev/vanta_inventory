from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import os, io, time, json, zipfile, datetime
import requests
from urllib.parse import urlparse
import psycopg2  # Postgres (used for backup route)
import openpyxl  # Excel export

# Babel is optional; if missing, use a safe fallback
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

# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")

# -----------------------------------------------------------------------------
# Language / Currency (Phase 2 core)
# -----------------------------------------------------------------------------
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

# ---- Robust FX (USD base) ---------------------------------------------------
# We always fetch 1 USD = X {USD,AED,UZS} and derive any other base from that.
_SUPPORTED = {"USD", "AED", "UZS"}
_FX_CACHE = {"rates": None, "ts": 0}  # USD-based table only

def _fetch_usd_rates():
    """Get 1 USD = R[currency] with caching + safe fallbacks."""
    now = time.time()
    if _FX_CACHE["rates"] and (now - _FX_CACHE["ts"]) < 3600:
        return _FX_CACHE["rates"]

    try:
        r = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": ",".join(sorted(_SUPPORTED))},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json() or {}
        rates = data.get("rates") or {}
        rates["USD"] = 1.0
        _FX_CACHE.update({"rates": rates, "ts": now})
    except Exception:
        # last-resort defaults if first-ever call fails
        if not _FX_CACHE["rates"]:
            _FX_CACHE["rates"] = {"USD": 1.0, "AED": 3.6725, "UZS": 12600.0}
            _FX_CACHE["ts"] = now
    return _FX_CACHE["rates"]

def _derive_rates_from_usd(base):
    """
    Build BASE->currency rates using only the USD table:
      BASE->X = (USD->X) / (USD->BASE)
    """
    R = _fetch_usd_rates()
    base = (base or "USD").upper()
    if base not in R:
        base = "USD"

    derived = {}
    for x in _SUPPORTED:
        if x == base:
            derived[x] = 1.0
        else:
            try:
                derived[x] = float(R[x]) / float(R[base])
            except Exception:
                derived[x] = 0.0
    return base, derived

def convert_amount(value, from_curr=None, to_curr=None):
    """Convert using USD-base table: from -> USD -> to."""
    try:
        v = float(value or 0)
    except Exception:
        return 0.0
    from_curr = (from_curr or "UZS").upper()
    to_curr   = (to_curr or get_curr()).upper()
    if from_curr == to_curr:
        return v

    R = _fetch_usd_rates()  # 1 USD = R[currency]
    if from_curr not in R or to_curr not in R:
        return v

    amount_usd = v / float(R[from_curr])
    return amount_usd * float(R[to_curr])

def fmt_money_auto(value, from_curr=None):
    """Convert from 'from_curr' to the user's currency, then format."""
    return fmt_money(convert_amount(value, from_curr=from_curr, to_curr=get_curr()))

@app.template_filter('convert_js')
def convert_js(value, from_curr):
    return round(convert_amount(value, from_curr=from_curr, to_curr=get_curr()), 2)

@app.context_processor
def inject_helpers():
    lang = get_lang()
    return {
        "fmt_money": fmt_money,
        "fmt_money_auto": fmt_money_auto,  # for values stored in UZS (or another base)
        "convert": convert_amount,         # raw converter (e.g., JS prefill)
        "USER_LANG": lang,
        "USER_CURR": get_curr(),
        "t": lambda key: t(key, lang),
    }

@app.get("/api/rates")
def api_rates():
    # Always return a correct BASE->(USD,AED,UZS) map derived from USD table
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
    curr = (request.form.get("curr") or DEFAULT_CURR).strip()
    session["LANG"] = "uz" if lang == "uz" else "en"
    session["CURR"] = curr if curr in {"USD", "AED", "UZS"} else DEFAULT_CURR
    flash(t("preferences_saved", session["LANG"]), "success")
    return redirect(url_for("login"))


# -----------------------------------------------------------------------------
# Money helpers (legacy filter kept for inputs/old spots)
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Startup: ensure DB schema
# -----------------------------------------------------------------------------
with app.app_context():
    try:
        ensure_schema()
        print("✅ Database schema ensured at startup.")
    except Exception as e:
        print(f"⚠️ Failed to ensure schema: {e}")

# -----------------------------------------------------------------------------
# Version / Health
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Env config
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------
ADMIN_USERS_ENV = os.environ.get("ADMIN_USERS")
if ADMIN_USERS_ENV:
    ADMIN_USERS = dict(pair.split(":", 1) for pair in ADMIN_USERS_ENV.split(","))
else:
    ADMIN_USERS = {"vanta": "beastmode", "jasur": "jasur2025"}

def is_logged_in():
    return bool(session.get("logged_in"))

# -----------------------------------------------------------------------------
# Data access
# -----------------------------------------------------------------------------
def get_inventory():
    rows = db.db_all("""
        SELECT id, name, buying_price, selling_price, quantity, profit,
               COALESCE(currency, 'UZS') AS currency
        FROM inventory
        ORDER BY id
    """)
    return [tuple(r) for r in rows]

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
# 🏠 Home
@app.route("/", methods=["GET", "POST"])
def index():
    if not is_logged_in():
        return redirect(url_for("login"))

    # ---- BLOCK 3: search/filter/sort (from GET or POST) ----
    search_query    = (request.values.get("search", "") or "").strip().lower()
    selected_filter = request.values.get("filter", "")
    sort_by         = request.args.get("sort_by", "id")
    direction       = request.args.get("direction", "asc")
    # --------------------------------------------------------

    inventory = get_inventory()  # tuples: (id, name, buying_price, selling_price, quantity, profit, currency)

    # DB type
    using_sqlite = db.DATABASE_URL.startswith("sqlite")

    # Today's revenue/profit
    if using_sqlite:
        row = db.db_one(
            """
            SELECT COALESCE(SUM(qty*sell_price),0), COALESCE(SUM(profit),0)
            FROM sales WHERE DATE(sold_at)=DATE('now','localtime')
            """
        )
    else:
        row = db.db_one(
            """
            SELECT COALESCE(SUM(qty*sell_price),0), COALESCE(SUM(profit),0)
            FROM sales WHERE DATE(sold_at)=CURRENT_DATE
            """
        )
    today_revenue, today_profit = (row[0] if row else 0), (row[1] if row else 0)

    # Filter (string search + quick filters)
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

    # Top 5 / Low 5 (by profit/quantity)
    top_profit_items = sorted(inventory, key=lambda x: x[5], reverse=True)[:5]
    low_stock_items  = sorted(inventory, key=lambda x: x[4])[:5]

    # Last 7 days revenue
    if using_sqlite:
        rows = db.db_all(
            """
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
            """
        )
    else:
        rows = db.db_all(
            """
            WITH days AS (
              SELECT generate_series(current_date - interval '6 day', current_date, interval '1 day')::date AS d
            )
            SELECT d AS day,
                   COALESCE((SELECT SUM(qty*sell_price) FROM sales s WHERE DATE(s.sold_at)=d),0) AS revenue
            FROM days
            ORDER BY d
            """
        )
    sales_labels = [str(r[0]) for r in rows]
    sales_values = [float(r[1] or 0) for r in rows]

    # Stock tracker
    stock_labels = [it[1] for it in inventory]
    stock_values = [it[4] for it in inventory]

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
    )

# ➕ Add Item
@app.post("/add")
def add_item():
    if not is_logged_in():
        return redirect(url_for("login"))

    name = request.form["name"].strip().lower()
    quantity = int(request.form["quantity"])
    buying_price = parse_money(request.form["buying_price"])
    selling_price = parse_money(request.form["selling_price"])
    profit = (selling_price - buying_price) * quantity

    db.db_exec(
        """
        INSERT INTO inventory (name, buying_price, selling_price, quantity, profit)
        VALUES (:n, :bp, :sp, :q, :pf)
        """,
        {"n": name.capitalize(), "bp": buying_price, "sp": selling_price, "q": quantity, "pf": profit},
    )

    flash(f"Item '{name.capitalize()}' added successfully!", "success")
    return redirect(url_for("index"))

# 💵 Sell Item
@app.post("/sell")
def sell_item():
    if not is_logged_in():
        return redirect(url_for("login"))

    item_id = int(request.form["item_id"])
    qty = int(request.form["qty"])
    sell_price = parse_money(request.form["sell_price"])

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
        """
        INSERT INTO sales (item_id, qty, sell_price, profit)
        VALUES (:id, :q, :sp, :pf)
        """,
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
        name = request.form["name"].strip().lower()
        quantity = int(request.form["quantity"])
        buying_price = parse_money(request.form["buying_price"])
        selling_price = parse_money(request.form["selling_price"])
        profit = (selling_price - buying_price) * quantity

        db.db_exec(
            """
            UPDATE inventory
            SET name=:n, buying_price=:bp, selling_price=:sp, quantity=:q, profit=:pf
            WHERE id=:id
            """,
            {"n": name.capitalize(), "bp": buying_price, "sp": selling_price, "q": quantity, "pf": profit, "id": item_id},
        )
        flash(f"Item '{name.capitalize()}' updated successfully!", "info")
        return redirect(url_for("index"))

    row = db.db_one("SELECT * FROM inventory WHERE id = :id", {"id": item_id})
    item = tuple(row) if row else None
    return render_template("edit.html", item=item)

# 📤 Export to Excel
@app.get("/export")
def export_excel():
    if not is_logged_in():
        return redirect(url_for("login"))

    inventory = get_inventory()

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.title = "Inventory"
    headers = ["ID", "Name", "Buying Price", "Selling Price", "Quantity", "Profit", "Currency"]
    sh.append(headers)
    for row in inventory:
        sh.append(list(row))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name="inventory_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# 📦 One-click data backup (ZIP of CSVs for every public table)
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
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE'
            ORDER BY table_name;
            """
        )
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

# -----------------------------------------------------------------------------
# Local dev entry
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=True)
