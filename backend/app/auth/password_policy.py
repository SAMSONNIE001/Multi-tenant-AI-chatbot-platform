def validate_password_input(value: str) -> str:
    text = str(value or "")
    if len(text.encode("utf-8")) > 72:
        raise ValueError("Password too long (max 72 bytes).")
    if any((ord(ch) < 32 or ord(ch) == 127) for ch in text):
        raise ValueError("Password contains unsupported control characters.")
    return text

