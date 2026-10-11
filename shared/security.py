import os, jwt, time
from fastapi import Header, HTTPException
SECRET=os.getenv('BANK_JWT_SECRET','dev-only-change-this-secret-at-least-32-chars')
def issue(uid,email,role,name,branch=None):
    now=int(time.time()); return jwt.encode({'sub':str(uid),'email':email,'role':role,'name':name,'branch':branch,'iat':now,'exp':now+900},SECRET,algorithm='HS256')
def current(authorization: str|None=Header(default=None)):
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Sign in required.')
    try: p=jwt.decode(authorization[7:],SECRET,algorithms=['HS256']); return {'id':int(p['sub']),'email':p['email'],'role':p['role'],'name':p['name'],'branch':p.get('branch')}
    except Exception: raise HTTPException(401,'Invalid or expired access token.')
def require(user, *roles):
    if user['role'] not in roles: raise HTTPException(403,'Your role is not allowed to perform this action.')
def is_staff(user): return user['role'] in ('EMPLOYEE','MANAGER','ADMIN')
