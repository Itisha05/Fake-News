import re
app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# Bleach and input length logic for analyze
analyze_repl = """    data = request.get_json()
    content = data.get("content", "")
    
    if not content:
        return {"error": "No content provided"}, 400
        
    if len(content) > 50000:
        return {"error": "Content too long (max 50000 characters)"}, 400
        
    content = bleach.clean(content)"""

content = re.sub(
    r'\s*data = request\.get_json\(\)\s*content = data\.get\("content", ""\)\s*if not content:\s*return \{"error": "No content provided"\}, 400',
    analyze_repl,
    content,
    count=1
)

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Bleach and length limits applied.")
