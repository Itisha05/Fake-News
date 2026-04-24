"""Add @csrf.exempt decorator to JSON API routes in app.py"""
import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# These are the JSON API route patterns that need CSRF exemption
# Format: the @app.route line text (unique enough to match)
routes_to_exempt = [
    '@app.route("/analyze", methods=["POST"])',
    '@app.route("/analyze_url", methods=["POST"])',
    '@app.route("/save_history", methods=["POST"])',
    '@app.route("/delete_history/<int:index>", methods=["DELETE"])',
    '@app.route("/clear_history", methods=["POST"])',
    '@app.route("/get_history")',
    '@app.route("/get_stats")',
    '@app.route("/get_analytics")',
    '@app.route("/save_preferences", methods=["POST"])',
    '@app.route("/save_profile", methods=["POST"])',
    '@app.route("/change_password", methods=["POST"])',
    '@app.route("/export_user_data")',
    '@app.route("/delete_account", methods=["POST"])',
]

count = 0
for route in routes_to_exempt:
    if route in content and f"@csrf.exempt\n{route}" not in content:
        content = content.replace(route, f"@csrf.exempt\n{route}")
        count += 1

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print(f"Added @csrf.exempt to {count} routes.")

routes_to_exempt = [
    if routes in content and f""
]
