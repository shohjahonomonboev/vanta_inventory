import sqlite3

# Connect to (or create) the database
conn = sqlite3.connect('inventory.db')
cursor = conn.cursor()

# Create inventory table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        buying_price REAL,
        selling_price REAL,
        quantity INTEGER,
        profit REAL
    )
''')

conn.commit()
conn.close()

print("✅ Database and table created successfully.")
@app.route('/add', methods=['POST'])
def add_item():
    name = request.form['name'].strip().lower()
    buying_price = float(request.form['buying_price'])
    selling_price = float(request.form['selling_price'])
    quantity = int(request.form['quantity'])
    profit = (selling_price - buying_price) * quantity

    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO inventory (name, buying_price, selling_price, quantity, profit)
        VALUES (?, ?, ?, ?, ?)
    ''', (name.capitalize(), buying_price, selling_price, quantity, profit))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))
