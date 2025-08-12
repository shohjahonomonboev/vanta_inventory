# start-dev.ps1 — run local dev server with auto-reload
$env:FLASK_APP = "app.py"
$env:FLASK_ENV = "development"
$env:ENV       = "dev"            # our app.py reads this to set dev config
$env:PYTHONUNBUFFERED = "1"       # cleaner live logs
flask run --debug --port 5000
