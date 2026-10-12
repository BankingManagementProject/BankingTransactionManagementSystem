from __future__ import annotations
import os, jwt, time
from fastapi import Header, HTTPException
from typing import Optional

SECRET = os.getenv('BANK_JWT_SECRET', 'dev-only-change-this-secret-at-least-32-chars')

def issue(uid, email, role, name, branch=None):
    now = int(time.time())
    return jwt.encode({
        'sub': str(uid),
        'email': email,
        'role': role,
        'name': name,
        'branch': branch,
        'iat': now,
        'exp': now + 900
    }, SECRET, algorithm='HS256')

def current(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Sign in required.')
    try:
        p = jwt.decode(authorization[7:], SECRET, algorithms=['HS256'])
        return {
            'id': int(p['sub']),
            'email': p['email'],
            'role': p['role'],
            'name': p['name'],
            'branch': p.get('branch')
        }
    except Exception:
        raise HTTPException(401, 'Invalid or expired access token.')

def require(user, *roles):
    """Enforces role-based authorization.
    Accepts both STAFF and EMPLOYEE interchangeably for backward compatibility.
    """
    user_role = user.get('role', '')
    allowed = set(roles)
    if 'STAFF' in allowed:
        allowed.add('EMPLOYEE')
    if 'EMPLOYEE' in allowed:
        allowed.add('STAFF')
    if user_role not in allowed:
        raise HTTPException(403, f"Your role ({user_role}) is not allowed to perform this action. Required: {', '.join(roles)}")

def is_staff(user):
    """Returns True if the user has Staff, Manager, or Admin privileges."""
    return user.get('role') in ('EMPLOYEE', 'STAFF', 'MANAGER', 'ADMIN')

def is_manager(user):
    """Returns True if user has Manager or Admin privileges."""
    return user.get('role') in ('MANAGER', 'ADMIN')
