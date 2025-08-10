from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import os
import sqlite3
import io
import openpyxl

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secret key for session management

# ---- Admin accounts (supports multiple) ----
# Format: "user1:pass1,user2:pass2"
ADMIN_USERS_ENV = os.environ.get("ADMIN_USERS")
if ADMIN_USERS_ENV:
    ADMIN_USERS = dict(pair.split(":", 1) for pair in ADMIN_USERS_ENV.split(","))
else:
    ADMIN_USERS = {
        "vanta": "beastmode",
        "jasur": "jasur2025",
    }

# ===== DB Connection =====
DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.getcwd(), "inventory.db")  # default for local dev
)

# =========================
# DB helpers + init
# =========================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn

def init_db():
    """Ensure inventory table exists and has a 'currency' column."""
    conn = get_db()
    c = conn.cursor()

    # Create table if missing (without currency column first)
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            buying_price REAL,
            selling_price REAL,
            quantity INTEGER,
            profit REAL
            -- 'currency' will be added if missing
        )
    """)

    # Add 'currency' column if missing
    c.execute("PRAGMA table_info(inventory)")
    cols = [row[1] for row in c.fetchall()]
    if "currency" not in cols:
        c.execute("ALTER TABLE inventory ADD COLUMN currency TEXT NOT NULL DEFAULT 'UZS'")

    # Backfill
    c.execute("UPDATE inventory SET currency='UZS' WHERE currency IS NULL OR TRIM(currency)=''")

    conn.commit()
    conn.close()

def init_sales_table():
    """Ensure sales table exists."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            sell_price REAL NOT NULL,
            profit REAL NOT NULL,
            sold_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES inventory(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

# Run table initializations at import time (works on Render + local)
with app.app_context():
    init_db()
    init_sales_table()



# 🔎 Fetch inventory
def get_inventory():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory")
    items = cursor.fetchall()
    conn.close()
    return items

# 🏠 Home Route
@app.route('/', methods=['GET', 'POST'])
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    search_query = request.form.get('search', '').strip().lower()
    selected_filter = request.form.get('filter', '')
    sort_by = request.args.get('sort_by', 'id')
    direction = request.args.get('direction', 'asc')

    inventory = get_inventory()

    # 📈 Today's revenue & profit
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT 
            COALESCE(SUM(qty * sell_price), 0) AS revenue,
            COALESCE(SUM(profit), 0) AS profit
        FROM sales
        WHERE DATE(sold_at) = DATE('now', 'localtime')
    """)
    today_revenue, today_profit = c.fetchone()
    conn.close()

    # 🔍 Filter by search
    if search_query:
        inventory = [item for item in inventory if search_query in item[1].lower()]

    # 🧠 Extra filters
    if selected_filter == 'low_stock':
        inventory = [item for item in inventory if item[4] <= 5]
    elif selected_filter == 'high_profit':
        inventory = [item for item in inventory if item[5] >= 100]

    # 🔄 Sorting
    sort_map = {'name': 1, 'quantity': 4, 'profit': 5}
    if sort_by in sort_map:
        index_key = sort_map[sort_by]
        inventory = sorted(inventory, key=lambda x: x[index_key], reverse=(direction == 'desc'))

    total_quantity = sum(item[4] for item in inventory)
    total_profit = sum(item[5] for item in inventory)

    # 📊 Top 5 Profit & Lowest 5 Stock
    top_profit_items = sorted(inventory, key=lambda x: x[5], reverse=True)[:5]
    low_stock_items = sorted(inventory, key=lambda x: x[4])[:5]

    # 📊 Last 7 days revenue
    conn = get_db()
    c = conn.cursor()
    c.execute("""
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
                 SELECT SUM(qty * sell_price)
                 FROM sales s
                 WHERE DATE(s.sold_at)=d
               ), 0) AS revenue
        FROM days;
    """)
    rows = c.fetchall()
    conn.close()
    
    sales_labels = [r[0] for r in rows]
    sales_values = [r[1] for r in rows]

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
        sales_values=sales_values
    )

# ➕ Add Item
@app.route('/add', methods=['POST'])
def add_item():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    name = request.form['name'].strip().lower()
    quantity = int(request.form['quantity'])
    buying_price = float(request.form['buying_price'])
    selling_price = float(request.form['selling_price'])
    profit = (selling_price - buying_price) * quantity

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO inventory (name, buying_price, selling_price, quantity, profit)
        VALUES (?, ?, ?, ?, ?)
    ''', (name.capitalize(), buying_price, selling_price, quantity, profit))
    conn.commit()
    conn.close()

    flash(f"Item '{name.capitalize()}' added successfully!", "success")
    return redirect(url_for('index'))

# 💵 Sell Item
@app.route('/sell', methods=['POST'])
def sell_item():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    item_id = int(request.form['item_id'])
    qty = int(request.form['qty'])
    sell_price = float(request.form['sell_price'])

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT quantity, buying_price FROM inventory WHERE id = ?", (item_id,))
    item = c.fetchone()
    if not item:
        flash("Item not found!", "error")
        conn.close()
        return redirect(url_for('index'))

    stock_qty, buy_price = item
    if qty > stock_qty:
        flash("Not enough stock!", "error")
        conn.close()
        return redirect(url_for('index'))

    profit = (sell_price - buy_price) * qty

    c.execute("""
        INSERT INTO sales (item_id, qty, sell_price, profit)
        VALUES (?, ?, ?, ?)
    """, (item_id, qty, sell_price, profit))

    c.execute("UPDATE inventory SET quantity = quantity - ? WHERE id = ?", (qty, item_id))
    conn.commit()
    conn.close()

    flash(f"Sold {qty} unit(s). Profit: {profit:.2f}", "success")
    return redirect(url_for('index'))

# ❌ Delete Item
@app.route('/delete/<int:item_id>')
def delete_item(item_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inventory WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

    flash("Item deleted successfully!", "warning")
    return redirect(url_for('index'))

# 🔐 Login
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

# 🚪 Logout
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# ✏️ Edit Item
@app.route('/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        name = request.form['name'].strip().lower()
        quantity = int(request.form['quantity'])
        buying_price = float(request.form['buying_price'])
        selling_price = float(request.form['selling_price'])
        profit = (selling_price - buying_price) * quantity

        cursor.execute('''
            UPDATE inventory
            SET name = ?, buying_price = ?, selling_price = ?, quantity = ?, profit = ?
            WHERE id = ?
        ''', (name.capitalize(), buying_price, selling_price, quantity, profit, item_id))
        conn.commit()
        conn.close()

        flash(f"Item '{name.capitalize()}' updated successfully!", "info")
        return redirect(url_for('index'))

    cursor.execute('SELECT * FROM inventory WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    conn.close()
    return render_template('edit.html', item=item)

# 📤 Export to Excel
@app.route('/export')
def export_excel():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    inventory = get_inventory()

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Inventory"
    headers = ["ID", "Name", "Buying Price", "Selling Price", "Quantity", "Profit", "Currency"]
    sheet.append(headers)
    for item in inventory:
        sheet.append(item)

    file_stream = io.BytesIO()
    workbook.save(file_stream)
    file_stream.seek(0)

    return send_file(
        file_stream,
        as_attachment=True,
        download_name="inventory_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 🚀 Run App
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
