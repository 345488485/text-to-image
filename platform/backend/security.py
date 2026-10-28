import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def validate_password(password):
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise ValueError('密码长度须为10至128个字符')


def hash_password(password):
    validate_password(password)
    return _encode_password(password)


def _encode_password(password):
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return 'scrypt$' + salt + '$' + key.hex()


def bootstrap_admin(db):
    # Explicit local first-run credential; business APIs remain locked until changed.
    encoded = _encode_password('123456')
    with db.transaction() as c:
        if c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            return False
        c.execute('INSERT INTO users(id,username,password_hash,role,created_at,must_change_password) VALUES(?,?,?,?,?,1)',
                  (secrets.token_hex(16),'admin',encoded,'admin',now()))
    return True


def check_password(password, encoded):
    try:
        method, salt, expected = encoded.split('$')
        if method != 'scrypt' or not isinstance(password, str) or len(password) > 128:
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(db, username, password, role='user'):
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{3,32}', username):
        raise ValueError('账号须为3至32位字母、数字、下划线、点或短横线')
    if role not in ('admin', 'user'):
        raise ValueError('角色无效')
    uid = secrets.token_hex(16)
    db.execute('INSERT INTO users(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
               (uid, username, hash_password(password), role, now()))
    return uid
