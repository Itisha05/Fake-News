import os
import re

app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. IMPORTS
imports = """from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
import bleach
import time
from datetime import datetime, timedelta
from email_validator import validate_email, EmailNotValidError"""
content = re.sub(
    r"from flask import Flask.*?flash, jsonify\n",
    imports + "\n",
    content,
    count=1
)

# 2. APP CONFIGURATION
app_config = """app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Security Configurations
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.permanent_session_lifetime = timedelta(minutes=30)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

csrf = CSRFProtect(app)

csp = {
    'default-src': ["\\'self\\'", 'cdnjs.cloudflare.com', 'cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'],
    'script-src': ["\\'self\\'", "\\'unsafe-inline\\'", 'cdnjs.cloudflare.com', 'cdn.jsdelivr.net', 'cdn.jsdelivr.net/npm/chart.js@4.4.0/'],
    'style-src': ["\\'self\\'", "\\'unsafe-inline\\'", 'cdnjs.cloudflare.com', 'fonts.googleapis.com'],
    'img-src': ["\\'self\\'", 'data:', 'https:']
}
Talisman(app, content_security_policy=csp)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per hour"]
)"""

content = re.sub(
    r"app = Flask\(__name__\)\s+app\.secret_key = os\.getenv\(\"SECRET_KEY\", \"supersecretkey\"\)",
    app_config.replace('\\', ''), # Fix escaping in Python string block
    content,
    count=1
)

# 3. /login route logic
login_original = """@app.route("/login", methods=["GET", "POST"])
def login():"""

login_new = """@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        if users_col is None:
            return _db_unavailable()

        email = request.form["email"]
        password = request.form["password"]

        user_record = users_col.find_one({"email": email})
        if user_record and user_record.get('locked_until'):
            if datetime.now() < user_record['locked_until']:
                flash("Account locked due to too many failed attempts. Try again later.", "error")
                return redirect(url_for("login"))
            else:
                users_col.update_one({"email": email}, {"$set": {"failed_attempts": 0}, "$unset": {"locked_until": ""}})

        user = users_col.find_one({"email": email, "password": password})

        if user:
            users_col.update_one({"email": email}, {"$set": {"failed_attempts": 0}})
            session.permanent = True
            token = serializer.dumps(email, salt='magic-link')
            link = url_for('magic_login', token=token, _external=True)
            send_magic_link(email, link)
            return redirect(url_for("check_email"))
        else:
            if user_record:
                failed = user_record.get('failed_attempts', 0) + 1
                update_data = {"$set": {"failed_attempts": failed}}
                if failed >= 5:
                    update_data["$set"]["locked_until"] = datetime.now() + timedelta(minutes=15)
                users_col.update_one({"email": email}, update_data)
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))

    return render_template("login.html")"""

content = re.sub(
    r"@app\.route\(\"/login\", methods=\[\"GET\", \"POST\"\]\)\ndef login\(\):.*?(?=return render_template\(\"login\.html\"\)\n).*?return render_template\(\"login\.html\"\)",
    login_new,
    content,
    flags=re.DOTALL,
    count=1
)


# 4. /magic-login
content = re.sub(
    r"@app\.route\(\"/magic-login/<token>\"\)\ndef magic_login\(token\):",
    r"@app.route(\"/magic-login/<token>\")\n@limiter.limit(\"3 per minute\")\ndef magic_login(token):\n    session.permanent = True",
    content,
    count=1
)

# 5. /verify_otp
verify_new = """@app.route("/verify_otp", methods=["GET", "POST"])
@limiter.limit("3 per minute")
def verify_otp():
    if "pending_email" not in session:
        return redirect(url_for("login"))

    otp_time = session.get("otp_time", 0)
    if time.time() > otp_time + 300:
        session.pop("otp", None)
        flash("OTP has expired. Please login again.", "error")
        return redirect(url_for("login"))
        
    retries = session.get("otp_retries", 0)
    if retries >= 3:
        session.pop("otp", None)
        flash("Too many failed OTP attempts. Please login again.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        user_otp = request.form["otp"]
        if user_otp == session.get("otp"):
            session.pop("otp", None)
            session.pop("pending_email", None)
            session["user_email"] = session.get("pending_email")
            session.permanent = True
            return redirect(url_for("dashboard"))
        else:
            session["otp_retries"] = retries + 1
            return "Invalid OTP. Please try again."

    return render_template("otp.html")"""

content = re.sub(
    r"@app\.route\(\"/verify_otp\", methods=\[\"GET\", \"POST\"\]\)\ndef verify_otp\(\):.*?(?=return render_template\(\"otp\.html\"\)\n).*?return render_template\(\"otp\.html\"\)",
    verify_new,
    content,
    flags=re.DOTALL,
    count=1
)

# 6. /signup route logic limits + email validation
content = content.replace('@app.route("/signup", methods=["GET", "POST"])\ndef signup():',
'''@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def signup():''')

content = content.replace('_re.match(r\'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$\', email)',
'''_re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            # Email Validation using email-validator
            try:
                validate_email(email)
            except EmailNotValidError:
                flash("Invalid email format (Email Validator rejected).", "error")
                return redirect(url_for("signup"))
            # End hook''')

# 7. /analyze 
content = content.replace('@app.route("/analyze", methods=["POST"])\ndef analyze_news():',
'''@app.route("/analyze", methods=["POST"])
@limiter.limit("10 per minute")
def analyze_news():''')

# 8. /analyze_url
content = content.replace('@app.route("/analyze_url", methods=["POST"])\ndef analyze_url():',
'''@app.route("/analyze_url", methods=["POST"])
@limiter.limit("5 per minute")
def analyze_url():''')

# 9. Error Handlers
error_handlers = """

# ---------- Error Handlers ----------
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    if request.is_json:
        return jsonify({"error": "CSRF token missing or incorrect", "status": "Error"}), 400
    return "CSRF Error", 400

@app.errorhandler(400)
def bad_request(e):
    if request.is_json: return jsonify({"error": "Bad Request"}), 400
    return "Bad Request", 400

@app.errorhandler(401)
def unauthorized(e):
    if request.is_json: return jsonify({"error": "Unauthorized"}), 401
    return "Unauthorized", 401

@app.errorhandler(403)
def forbidden(e):
    if request.is_json: return jsonify({"error": "Forbidden"}), 403
    return "Forbidden", 403

@app.errorhandler(429)
def ratelimit_handler(e):
    if request.is_json: return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
    return "Rate Limit Exceeded", 429

@app.errorhandler(500)
def internal_error(e):
    if request.is_json: return jsonify({"error": "Internal Server Error"}), 500
    return "Internal Server Error", 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))
"""

content = content + error_handlers

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patch applied.")
