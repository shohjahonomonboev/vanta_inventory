from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import os, io, openpyxl
import database_sqlalchemy as db

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-secret-change-me")

# --- Version helpers ---
def get_version():
    try:
        return open("VERSION", encoding="utf-8").read().strip()
    except Exception:
        return "dev"

@app.context_processor
def inject_version():
    return {"APP_VERSION": get_version()}

# --- Health route ---
@app.get("/__health")
def __health():
    return jsonify(status="ok", version=get_version()), 200

# --- Env config ---
ENV = os.getenv("ENV", "dev").lower()
if ENV == "dev":
    app.config.update(DEBUG=True, TEMPLATES_AUTO_RELOAD=True, SERVER_NAME=None, SESSION_COOKIE_SECURE=False, SESSION_COOKIE_SAMESITE="Lax")
else:
    app.config.update(TEMPLATES_AUTO_RELOAD=False, SEND_FILE_MAX_AGE_DEFAULT=31536000, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax")

# --- Admin users ---
ADMIN_USERS_ENV = os.environ.get("ADMIN_USERS")
if ADMIN_USERS_ENV:
    ADMIN_USERS = dict(pair.split(":", 1) for pair in ADMIN_USERS_ENV.split(","))
else:
    ADMIN_USERS = {"vanta": "beastmode", "jasur": "jasur2025"}

# Ensure schema (works for both SQLite & Postgres)
_initialized = False  # Flag so it runs only once

@app.before_request
def _init_db_once():
    global _initialized
    if not _initialized:
        try:
            db.ensure_schema()  # Create tables if missing
        finally:
            _initialized = True


# ===== Helpers =====

def get_inventory():
    rows = db.db_all(
        """
        SELECT id, name, buying_price, selling_price, quantity, profit,
               COALESCE(currency, 'UZS') AS currency
        FROM inventory
        ORDER BY id
        """
    )
    return [tuple(r) for r in rows]

# 🏠 Home
@app.route('/', methods=['GET', 'POST'])
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    search_query = request.form.get('search', '').strip().lower()
    selected_filter = request.form.get('filter', '')
    sort_by = request.args.get('sort_by', 'id')
    direction = request.args.get('direction', 'asc')

    inventory = get_inventory()
    CURRENCY = (inventory[0][6] if inventory and len(inventory[0]) > 6 else 'UZS')

    # Today's revenue/profit (portable SQL)
    if db.is_sqlite():
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

    # Filter
    if search_query:
        inventory = [item for item in inventory if search_query in item[1].lower()]
    if selected_filter == 'low_stock':
        inventory = [item for item in inventory if item[4] <= 5]
    elif selected_filter == 'high_profit':
        inventory = [item for item in inventory if item[5] >= 100]

    # Sort
    sort_map = {'name': 1, 'quantity': 4, 'profit': 5}
    if sort_by in sort_map:
        idx = sort_map[sort_by]
        inventory = sorted(inventory, key=lambda x: x[idx], reverse=(direction == 'desc'))

    total_quantity = sum(item[4] for item in inventory)
    total_profit = sum(item[5] for item in inventory)

    # Top 5 / Low 5
    top_profit_items = sorted(inventory, key=lambda x: x[5], reverse=True)[:5]
    low_stock_items = sorted(inventory, key=lambda x: x[4])[:5]

    # Last 7 days revenue (portable)
    if db.is_sqlite():
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
    stock_labels = [item[1] for item in inventory]
    stock_values = [item[4] for item in inventory]

    return render_template(
        'index.html',
        inventory=inventory,
        total_quantity=total_quantity,
        total_profit=total_profit,
        search_query=search_query,
        sort_by=sort_by,
        direction=direction,
        selected_filter=selected_filter,
        top_profit_labels=[item[1] for item in top_profit_items],
        top_profit_values=[item[5] for item in top_profit_items],
        low_stock_labels=[item[1] for item in low_stock_items],
        low_stock_values=[item[4] for item in low_stock_items],
        today_revenue=today_revenue,
        today_profit=today_profit,
        sales_labels=sales_labels,
        sales_values=sales_values,
        stock_labels=stock_labels,
        stock_values=stock_values,
        CURRENCY=CURRENCY,
    )

# ➕ Add Item
@app.post('/add')
def add_item():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    name = request.form['name'].strip().lower()
    quantity = int(request.form['quantity'])
    buying_price = float(request.form['buying_price'])
    selling_price = float(request.form['selling_price'])
    profit = (selling_price - buying_price) * quantity

    db.db_exec(
        '''
        INSERT INTO inventory (name, buying_price, selling_price, quantity, profit)
        VALUES (:n, :bp, :sp, :q, :pf)
        ''', {"n": name.capitalize(), "bp": buying_price, "sp": selling_price, "q": quantity, "pf": profit}
    )

    flash(f"Item '{name.capitalize()}' added successfully!", "success")
    return redirect(url_for('index'))

# 💵 Sell Item
@app.post('/sell')
def sell_item():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    item_id = int(request.form['item_id'])
    qty = int(request.form['qty'])
    sell_price = float(request.form['sell_price'])

    row = db.db_one("SELECT quantity, buying_price FROM inventory WHERE id=:id", {"id": item_id})
    if not row:
        flash("Item not found!", "error")
        return redirect(url_for('index'))

    stock_qty, buy_price = int(row[0]), float(row[1])
    if qty > stock_qty:
        flash("Not enough stock!", "error")
        return redirect(url_for('index'))

    profit = (sell_price - buy_price) * qty

    db.db_exec(
        """
        INSERT INTO sales (item_id, qty, sell_price, profit)
        VALUES (:id, :q, :sp, :pf)
        """,
        {"id": item_id, "q": qty, "sp": sell_price, "pf": profit}
    )
    db.db_exec("UPDATE inventory SET quantity = quantity - :q WHERE id = :id", {"q": qty, "id": item_id})

    flash(f"Sold {qty} unit(s). Profit: {profit:.2f}", "success")
    return redirect(url_for('index'))

# ❌ Delete Item
@app.get('/delete/<int:item_id>')
def delete_item(item_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    db.db_exec('DELETE FROM inventory WHERE id = :id', {"id": item_id})
    flash("Item deleted successfully!", "warning")
    return redirect(url_for('index'))

# 🔐 Login/Logout
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if ADMIN_USERS.get(username) == password:
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.get('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# ✏️ Edit Item
@app.route('/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name'].strip().lower()
        quantity = int(request.form['quantity'])
        buying_price = float(request.form['buying_price'])
        selling_price = float(request.form['selling_price'])
        profit = (selling_price - buying_price) * quantity

        db.db_exec(
            '''
            UPDATE inventory
            SET name=:n, buying_price=:bp, selling_price=:sp, quantity=:q, profit=:pf
            WHERE id=:id
            ''', {"n": name.capitalize(), "bp": buying_price, "sp": selling_price, "q": quantity, "pf": profit, "id": item_id}
        )
        flash(f"Item '{name.capitalize()}' updated successfully!", "info")
        return redirect(url_for('index'))

    row = db.db_one('SELECT * FROM inventory WHERE id = :id', {"id": item_id})
    item = tuple(row) if row else None
    return render_template('edit.html', item=item)

# 📤 Export to Excel
@app.get('/export')
def export_excel():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

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

# Local dev entry (prefer Flask CLI)
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=True)