# i18n.py — consolidated keys (no duplicates) + keys used by templates added

I18N = {
    "en": {
        # App / Header / Footer
        "app_name": "Jasurbek Inventory",
        "toggle_theme": "Toggle theme",
        "logout": "Logout",
        "made_with": "Made with ⚡ by Vanta",
        "version": "Version",
        "welcome_back": "Welcome back, Commander.",

        # Preferences panel
        "lang_curr": "Language & Currency",
        "language": "Language",
        "currency": "Currency",
        "save": "Save",
        "auto_detect": "Auto-detect",
        "rates_unavailable": "Rates unavailable.",
        "live_rates_loading": "Live rates loading…",
        "preferences_saved": "Preferences saved.",
        "prices_in_ui_currency": "Prices you enter are in UI currency",

        # Inventory / Forms
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

        # Filters / Sorting
        "filters": "Filters",
        "filter": "Filter",
        "apply": "Apply",
        "filter_sort": "Filter / Sort",
        "low_stock": "Low Stock",
        "high_profit": "High Profit",
        "low_stock_hint": "Low Stock shows items with ≤ 5 units.",
        "high_profit_hint": "High Profit surfaces the most profitable items.",
        "sort_name_asc": "A → Z (Name)",
        "sort_name_desc": "Z → A (Name)",
        "sort_qty_desc": "Quantity: High → Low",
        "sort_qty_asc": "Quantity: Low → High",
        "sort_price_desc": "Price: High → Low",
        "sort_price_asc": "Price: Low → High",
        "reset_sort": "Reset sort",

        # KPIs / Insights / Charts
        "todays_revenue": "Today's Revenue",
        "todays_profit": "Today's Profit",
        "insights": "Insights",
        "top_profit_title": "Top 5 Profitable Items",
        "top_profit_label": "Top 5 Profitable Items",
        "low_stock_title": "Lowest Stock (5)",
        "low_stock_label": "Lowest Stock (5)",
        "stock_tracker_title": "Stock Tracker",
        "stock_tracker_label": "Stock Tracker",
        "revenue_7d_title": "Revenue — Last 7 Days",
        "daily_revenue_label": "Daily Revenue",

        # Stock overview (chart block)
        "stock_overview_title": "Stock On Hand — Overview",
        "stock_overview_hint": "Bars show quantity per item; the line shows total stock value. Use search, sort, and Top N to focus. Scroll to zoom, drag to pan. Double-click to reset.",
        "search_items": "Search items…",
        "sort_label": "Sort",
        "top_n": "Top N",
        "hide_zero_qty": "Hide zero qty",
        "reset_view": "Reset view",
        "stock_value": "Stock Value",

        # (Chart control labels used in your template)
        "sort": "Sort",
        "qty_high_low": "Qty (high→low)",
        "value_high_low": "Value (high→low)",
        "profit_unit_high_low": "Profit/unit (high→low)",
        "name_az": "Name (A→Z)",

        # Sold Items
        "sold_items": "Sold Items",
        "sold_items_sub": "Return puts the quantity back into Inventory and removes this sale from today.",
        "sold_items_hint": "Return puts the quantity back into Inventory and removes this sale from today.",
        "no_sales_today": "No sales yet today.",
        "no_sales": "No sales yet.",
        "return": "Return",
        "delete": "Delete",

        # Export & Backup
        "export_backup": "Export & Backup",
        "export_excel": "Export Excel",
        "backup_db": "Backup DB",
        "download_excel": "Download Excel",
        "backup_now": "Backup Now",

        # Edit Item page
        "edit_item": "Edit Item",
        "update": "Update",
        "cancel": "Cancel",
        "quantity_placeholder": "Quantity",

        # Admin Login
        "admin_login": "Admin Login",
        "username": "Username",
        "password": "Password",
        "login": "Login",
        "forgot_password": "Forgot Password?",
        "admins_only_hint": "Admins only. Unauthorized access prohibited.",
        "enter_admin_username": "Enter your administrator username.",
        "only_admins_allowed": "Only authorized administrators are allowed to log in.",
        "invalid_credentials": "Invalid username or password.",

        # Generic confirmations / messages
        "confirm_delete_item": "Delete item?",
        "confirm_delete_sale": "Delete sale record?",
        "success": "Success",
        "error": "Error",
        "info": "Info",
        "warning": "Warning",
    },

    "uz": {
        # App / Header / Footer
        "app_name": "Jasurbek do'koni",
        "toggle_theme": "Oq / Qora tema",
        "logout": "Chiqish",
        "made_with": "Shohjahon tomonidan ⚡ bajarilgan",
        "version": "Versiya",
        "welcome_back": "Xush kelibsiz, Komandir.",

        # Preferences panel
        "lang_curr": "Til va Valyuta",
        "language": "Til",
        "currency": "Valyuta",
        "save": "Saqlash",
        "auto_detect": "Avto-aniqlash",
        "rates_unavailable": "Kurslar mavjud emas.",
        "live_rates_loading": "Jonli kurslar yuklanmoqda…",
        "preferences_saved": "Sozlamalar saqlandi.",
        "prices_in_ui_currency": "Kiritilgan narxlar UI valyutasida",

        # Inventory / Forms
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

        # Filters / Sorting
        "filters": "Filtrlar",
        "filter": "Filtr",
        "apply": "Qoʻllash",
        "filter_sort": "Filtr / Saralash",
        "low_stock": "Kam zaxira",
        "high_profit": "Yuqori foyda",
        "low_stock_hint": "Kam zaxira — ≤ 5 dona mahsulotlar.",
        "high_profit_hint": "Yuqori foyda eng foydali mahsulotlarni ko‘rsatadi.",
        "sort_name_asc": "A → Z (Nomi bo‘yicha)",
        "sort_name_desc": "Z → A (Nomi bo‘yicha)",
        "sort_qty_desc": "Miqdor: Ko‘p → Kam",
        "sort_qty_asc": "Miqdor: Kam → Ko‘p",
        "sort_price_desc": "Narx: Yuqori → Past",
        "sort_price_asc": "Narx: Past → Yuqori",
        "reset_sort": "Saralashni tiklash",

        # KPIs / Insights / Charts
        "todays_revenue": "Bugungi daromad",
        "todays_profit": "Bugungi foyda",
        "insights": "Tahlil grafikasi",
        "top_profit_title": "Eng foydali 5 ta mahsulot",
        "top_profit_label": "Eng foydali 5 ta mahsulot",
        "low_stock_title": "Eng kam zaxira (5)",
        "low_stock_label": "Eng kam zaxira (5)",
        "stock_tracker_title": "Zaxira dinamikasi",
        "stock_tracker_label": "Zaxira dinamikasi",
        "revenue_7d_title": "Oxirgi 7 kun — Daromad",
        "daily_revenue_label": "Kundalik daromad",

        # Stock overview (chart block)
        "stock_overview_title": "Ombordagi zaxira — Umumiy ko‘rinish",
        "stock_overview_hint": "Ustunlar — miqdor; chiziq — umumiy zaxira qiymati. Zoom uchun aylantiring, surish uchun torting, tiklash uchun ikki marta bosing.",
        "search_items": "Mahsulot qidirish…",
        "sort_label": "Saralash",
        "top_n": "Top N",
        "hide_zero_qty": "Nol miqdorni yashirish",
        "reset_view": "Ko‘rinishni tiklash",
        "stock_value": "Zaxira qiymati",

        # (Chart control labels used in your template)
        "sort": "Saralash",
        "qty_high_low": "Miqdor (ko‘p→kam)",
        "value_high_low": "Qiymat (yuqori→past)",
        "profit_unit_high_low": "Foyda/birlik (yuqori→past)",
        "name_az": "Nomi (A→Z)",

        # Sold Items
        "sold_items": "Sotilgan maxsulot",
        "sold_items_sub": "Qaytarish zaxiraga qo‘shadi va bugungi savdodan o‘chiradi.",
        "sold_items_hint": "Qaytarish zaxiraga qo‘shadi va bugungi savdodan o‘chiradi.",
        "no_sales_today": "Buguncha savdo yo‘q.",
        "no_sales": "Savdo yo‘q.",
        "return": "Qaytarish",
        "delete": "O‘chirish",

        # Export & Backup
        "export_backup": "Eksport va Zaxira",
        "export_excel": "Excel eksport",
        "backup_db": "Bazani zaxiralash",
        "download_excel": "Excel yuklab olish",
        "backup_now": "Zaxira nusxa olish",

        # Edit Item page
        "edit_item": "Mahsulotni tahrirlash",
        "update": "Yangilash",
        "cancel": "Bekor qilish",
        "quantity_placeholder": "Miqdor",

        # Admin Login
        "admin_login": "Admin kirish",
        "username": "Foydalanuvchi nomi",
        "password": "Parol",
        "login": "Kirish",
        "forgot_password": "Parolni unutdingizmi?",
        "admins_only_hint": "Faqat adminlar. Ruxsatsiz kirish taqiqlanadi.",
        "enter_admin_username": "Administrator foydalanuvchi nomini kiriting.",
        "only_admins_allowed": "Faqat ruxsat etilgan administratorlar kirishi mumkin.",
        "invalid_credentials": "Foydalanuvchi yoki parol noto‘g‘ri.",

        # Generic confirmations / messages
        "confirm_delete_item": "Mahsulot o‘chirilsinmi?",
        "confirm_delete_sale": "Savdo yozuvi o‘chirilsinmi?",
        "success": "Muvaffaqiyat",
        "error": "Xatolik",
        "info": "Ma’lumot",
        "warning": "Ogohlantirish",
    }
}

def t(key: str, lang: str = "en") -> str:
    return I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))
