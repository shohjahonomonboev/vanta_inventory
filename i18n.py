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

        # Insights
        "todays_revenue": "Today's Revenue",
        "todays_profit": "Today's Profit",
        "low_stock": "Low Stock",
        "high_profit": "High Profit",
        "insights": "Insights",
        "backup_now": "Backup Now",
        "download_excel": "Download Excel",
        "preferences_saved": "Preferences saved."
    },

    "uz": {
        # UI & Preferences
        "app_name": "Jasurbek Skladi",
        "toggle_theme": "Oq va Qora tema",
        "logout": "Chiqish",
        "made_with": "Vanta tomonidan ⚡ bilan yaratilgan",
        "version": "Versiya",

        "lang_curr": "Til va Valyuta",
        "language": "Til",
        "currency": "Valyuta",
        "save": "Saqlash",
        "auto_detect": "Avto-aniqlash",
        "rates_unavailable": "Kurslar mavjud emas.",
        "live_rates_loading": "Jonli kurslar yuklanmoqda…",

        # Inventory
        "inventory": "Skladi",
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

        # Insights
        "todays_revenue": "Bugungi daromad",
        "todays_profit": "Bugungi foyda",
        "low_stock": "Kam zaxira",
        "high_profit": "Yuqori foyda",
        "insights": "Tahlillar",
        "backup_now": "Zaxira nusxa olish",
        "download_excel": "Excel yuklab olish",
        "preferences_saved": "Sozlamalar saqlandi."
    }
}


def t(key, lang="en"):
    return I18N.get(lang, I18N["en"]).get(key, key)
