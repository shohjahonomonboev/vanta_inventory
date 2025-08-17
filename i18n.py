I18N = {
    "en": {
        # UI & Preferences
        "app_name": "Jasurbek Inventory",
        "toggle_theme": "Toggle theme",
        "logout": "Logout",
        "made_with": "Made with ⚡ by Vanta",
        "version": "Version",

        "lang_curr": "Language & Currency",
        "language": "Language",
        "currency": "Currency",
        "save": "Save",
        "auto_detect": "Auto-detect",
        "rates_unavailable": "Rates unavailable.",
        "live_rates_loading": "Live rates loading…",
        "preferences_saved": "Preferences saved.",
        "welcome_back": "Welcome back, Commander.",

        # Inventory
        "inventory": "Inventory",
        "item": "Item",
        "quantity": "Quantity",
        "buy": "Buy",
        "sell": "Sell",
        "profit": "Profit",
        "action": "Action",
        "sell_item": "Sell Item",
        "add_item": "Add Item",
        "stock": "Stock",
        "qty": "Qty",
        "sell_price": "Sell Price",
        "add": "Add",
        "search_item": "Search item",
        "filter": "Filter",
        "apply": "Apply",

        # Filters
        "filters": "Filters",
        "low_stock_hint": "Low Stock shows items with ≤ 5 units.",
        "high_profit_hint": "High Profit surfaces the most profitable items.",

        # Insights / Charts
        "todays_revenue": "Today's Revenue",
        "todays_profit": "Today's Profit",
        "low_stock": "Low Stock",
        "high_profit": "High Profit",
        "insights": "Insights",
        "backup_now": "Backup Now",
        "download_excel": "Download Excel",

        # Export & Backup
        "export_backup": "Export & Backup",
        "export_excel": "Export Excel",
        "backup_db": "Backup DB",

        # Chart titles/labels
        "top_profit_title": "Top 5 Profitable Items",
        "top_profit_label": "Top 5 Profitable Items",
        "low_stock_title": "Lowest Stock (5)",
        "low_stock_label": "Lowest Stock (5)",
        "stock_tracker_title": "Stock Tracker",
        "stock_tracker_label": "Stock Tracker",
        "revenue_7d_title": "Revenue — Last 7 Days",
        "daily_revenue_label": "Daily Revenue",
    },

    "uz": {
        # UI & Preferences
        "app_name": "Jasurbek do'koni",
        "toggle_theme": "Oq va Qora tema",
        "logout": "Chiqish",
        "made_with": "Shohjahon tomonidan ⚡ bajarilgan",
        "version": "Versiya",

        "lang_curr": "Til & Valyuta",
        "language": "Til",
        "currency": "Valyuta",
        "save": "Saqlash",
        "auto_detect": "Avto-aniqlash",
        "rates_unavailable": "Kurslar mavjud emas.",
        "live_rates_loading": "Jonli kurslar yuklanmoqda…",
        "preferences_saved": "Sozlamalar saqlandi.",
        "welcome_back": "Xush kelibsiz, Komandir.",

        # Inventory
        "inventory": "Umumiy jadval",
        "item": "Mahsulot",
        "quantity": "Miqdor",
        "buy": "Sotib olish",
        "sell": "Sotish",
        "profit": "Foyda",
        "action": "Amal",
        "sell_item": "Mahsulotni sotish",
        "add_item": "Mahsulot qoʻshish",
        "stock": "Zaxira",
        "qty": "Soni",
        "sell_price": "Sotish narxi",
        "add": "Qoʻshish",
        "search_item": "Mahsulot qidirish",
        "filter": "Filtr",
        "apply": "Qoʻllash",

        # Filters
        "filters": "Filtrlar",
        "low_stock_hint": "Kam zaxira — ≤ 5 dona mahsulotlar.",
        "high_profit_hint": "Yuqori foyda eng foydali mahsulotlarni ko‘rsatadi.",

        # Insights / Charts
        "todays_revenue": "Bugungi daromad",
        "todays_profit": "Bugungi foyda",
        "low_stock": "Kam zaxira",
        "high_profit": "Yuqori foyda",
        "insights": "Tahlil grafikasi",
        "backup_now": "Zaxira nusxa olish",
        "download_excel": "Excel yuklab olish",

        # Export & Backup
        "export_backup": "Eksport va Zaxira",
        "export_excel": "Excel eksport",
        "backup_db": "Bazani zaxiralash",

        # Chart titles/labels
        "top_profit_title": "Eng foydali 5 ta mahsulot",
        "top_profit_label": "Eng foydali 5 ta mahsulot",
        "low_stock_title": "Eng kam zaxira (5)",
        "low_stock_label": "Eng kam zaxira (5)",
        "stock_tracker_title": "Zaxira dinamikasi",
        "stock_tracker_label": "Zaxira dinamikasi",
        "revenue_7d_title": "Oxirgi 7 kun — Daromad",
        "daily_revenue_label": "Kundalik daromad",
    }
}

def t(key, lang="en"):
    return I18N.get(lang, I18N["en"]).get(key, key)
