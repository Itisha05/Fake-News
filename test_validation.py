"""Quick test of the validation module."""
from security.validation import validate_text, validate_url, sanitize_input, detect_malicious_patterns
from pprint import pprint

print("\n--- Testing Sanitization ---")
dirty = "<script>alert('xss')</script><b>Hello</b>"
print(f"Dirty: {dirty}")
print(f"Clean: {sanitize_input(dirty)}") # Should be "alert('xss')Hello" but safe

print("\n--- Testing Malicious Patterns ---")
bad_str = "javascript:alert(1)"
print(f"Is '{bad_str}' malicious? {detect_malicious_patterns(bad_str)}")

normal_str = "This is a normal tweet."
print(f"Is '{normal_str}' malicious? {detect_malicious_patterns(normal_str)}")

print("\n--- Testing Text Validation ---")
val_text_good = validate_text(normal_str)
print("Good text:", val_text_good)

val_text_bad = validate_text("<script>onload=function(){}</script>")
print("Bad text:", val_text_bad)

print("\n--- Testing URL Validation (No Google Key) ---")
val_url_good = validate_url("https://www.google.com")
print("Good URL:", val_url_good)

val_url_bad_scheme = validate_url("javascript:alert(1)")
print("Bad Scheme URL:", val_url_bad_scheme)

val_url_ip = validate_url("http://192.168.1.1/admin")
print("Bad IP URL:", val_url_ip)
