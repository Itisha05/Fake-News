import os
import re

templates = ["login.html", "signup.html", "otp.html", "dashboard.html", "index.html"]
for t in templates:
    path = os.path.join("templates", t)
    if not os.path.exists(path): continue
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # If the form doesn't actually have the hidden input yet, add it
    if 'name="csrf_token"' not in content:
        content = re.sub(
            r'(<form[^>]*>)', 
            r'\1\n        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>', 
            content
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
print("Forms patched successfully.")
