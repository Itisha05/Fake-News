import os
import re

app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add recaptcha helper natively
if "def verify_recaptcha" not in content:
    helper = """
import requests

def verify_recaptcha(recaptcha_response):
    secret = os.getenv("RECAPTCHA_SECRET_KEY", "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe")
    if not recaptcha_response:
        return False
    try:
        r = requests.post("https://www.google.com/recaptcha/api/siteverify", data={
            "secret": secret,
            "response": recaptcha_response
        }, timeout=5)
        return r.json().get("success", False)
    except:
        return False

"""
    # Insert helper after app instantiation
    content = content.replace('app = Flask(__name__)\n', 'app = Flask(__name__)\n' + helper)

# pass SITE KEY to context
if "@app.context_processor" not in content:
    context_processor = """
@app.context_processor
def inject_recaptcha():
    return dict(RECAPTCHA_SITE_KEY=os.getenv("RECAPTCHA_SITE_KEY", "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"))
"""
    content = content.replace("app.secret_key", context_processor.strip() + "\n\napp.secret_key")

# 2. Patch /login logic
if "verify_recaptcha(recaptcha_response)" not in content:
    login_validation = """
        recaptcha_response = request.form.get("g-recaptcha-response")
        if not verify_recaptcha(recaptcha_response):
            flash("Invalid CAPTCHA. Please try again.", "error")
            return redirect(url_for("login"))
            
        if users_col is None:"""
    content = content.replace('if users_col is None:', login_validation.strip(), 1)

# 3. Patch /signup logic
    signup_validation = """
        recaptcha_response = request.form.get("g-recaptcha-response")
        if not verify_recaptcha(recaptcha_response):
            flash("Invalid CAPTCHA. Please try again.", "error")
            return redirect(url_for("signup"))
            
        email = request.form["email"]"""
    content = content.replace('email = request.form["email"]', signup_validation.strip(), 1)

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)

# 4. Patch templates
templates_to_patch = ["login.html", "signup.html"]
for t_name in templates_to_patch:
    t_path = os.path.join("templates", t_name)
    if not os.path.exists(t_path): continue
    
    with open(t_path, "r", encoding="utf-8") as f:
        t_content = f.read()
        
    # Inject script tags into head
    if "recaptcha/api.js" not in t_content:
        t_content = t_content.replace('</head>', '    <script src="https://www.google.com/recaptcha/api.js" async defer></script>\n</head>')
        
    # Inject box
    recaptcha_html = '<div class="g-recaptcha" data-sitekey="{{ RECAPTCHA_SITE_KEY }}" style="margin-bottom:15px;"></div>'
    
    if t_name == "login.html" and 'class="g-recaptcha"' not in t_content:
        # replace the placeholder
        t_content = re.sub(r'<div class="form-group captcha-group".*?</div>\s*</div>', recaptcha_html, t_content, flags=re.DOTALL)
    
    elif t_name == "signup.html" and 'class="g-recaptcha"' not in t_content:
        # insert before the button
        t_content = t_content.replace('<button type="submit"', recaptcha_html + '\n                <button type="submit"')

    with open(t_path, "w", encoding="utf-8") as f:
        f.write(t_content)

print("reCAPTCHA integration complete.")
