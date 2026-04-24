import os
import re

# PATCH HTML
templates = ["index.html", "dashboard.html", "login.html", "signup.html", "otp.html", "check_email.html"]
for t in templates:
    path = os.path.join("templates", t)
    if not os.path.exists(path): continue
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Inject meta tag in head
    if "<head>" in content and "csrf-token" not in content:
        content = content.replace("<head>", "<head>\n    <meta name=\"csrf-token\" content=\"{{ csrf_token() }}\">")
        
    # Inject hidden input in forms
    # We will use regex to find <form ...>
    if "csrf_token" not in content:
        content = re.sub(
            r'(<form[^>]*>)', 
            r'\1\n        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>', 
            content
        )
        
    # specific CAPTCHA placeholder for login
    if t == "login.html" and "CAPTCHA" not in content:
        captcha_html = '''
            <div class="form-group captcha-group" style="margin-top:15px; margin-bottom:15px;">
                <div style="border:1px solid #ccc; background:#f9f9f9; padding:10px; text-align:center; border-radius:4px; color:#666;">
                    <i class="fas fa-shield-alt"></i> CAPTCHA Placeholder
                </div>
            </div>
            <button type="submit"'''
        content = content.replace('<button type="submit"', captcha_html)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# PATCH JS
js_path = "static/js/dashboard.js"
if os.path.exists(js_path):
    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()
        
    # replace headers manually
    if "X-CSRFToken" not in js_content:
        # replace `headers: { 'Content-Type': 'application/json' }` or similar
        js_content = re.sub(
            r"headers:\s*\{\s*'Content-Type'\s*:\s*'application/json'\s*\}",
            "headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name=\"csrf-token\"]')?.getAttribute('content') || '' }",
            js_content
        )
        
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(js_content)

print("Frontend patched.")
