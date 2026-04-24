import re
app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix app.run and move error handlers
error_handlers_block = re.search(r'# ---------- Error Handlers ----------.*', content, re.DOTALL)
if error_handlers_block:
    error_handlers = error_handlers_block.group(0)
    # Remove from bottom
    content = content.replace(error_handlers, "")
    
    # Replace app.run and put error handlers right above it
    content = content.replace('if __name__ == "__main__":\n    # Disable reloader on Windows to prevent socket errors\n    app.run(debug=True, use_reloader=False)',
    error_handlers + '\n\nif __name__ == "__main__":\n    app.run(debug=False, use_reloader=False)')

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content.strip() + "\\n")
print("Fixed app.run and error handlers mapping.")
