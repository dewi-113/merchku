from werkzeug.security import check_password_hash, generate_password_hash

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
    _has_argon2 = True
except Exception:
    _has_argon2 = False

def hash_password(pw: str) -> str:
    if _has_argon2:
        ph = PasswordHasher()
        return ph.hash(pw)
    # fallback
    return generate_password_hash(pw, method='pbkdf2:sha256')

def verify_password(stored: str, pw: str) -> bool:
    if _has_argon2:
        try:
            ph = PasswordHasher()
            ph.verify(stored, pw)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False
    return check_password_hash(stored, pw)
