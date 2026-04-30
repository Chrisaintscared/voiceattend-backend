from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.database import (
    list_all_users,
    delete_user,
    get_all_logs,
    get_connection
)
from app.security import require_admin

router = APIRouter() # tags are handled in main.py

class RoleUpdate(BaseModel):
    role: str

@router.get("/users")
def list_users(admin=Depends(require_admin)):
    return list_all_users()

@router.delete("/users/{user_id}", status_code=204)
def remove_user(user_id: int, admin=Depends(require_admin)):
    success = delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

@router.put("/users/{user_id}/role")
def update_role(user_id: int, body: RoleUpdate, admin=Depends(require_admin)):
    if body.role not in ("admin", "student", "teacher"):
        raise HTTPException(status_code=400, detail="Invalid role")

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET role=%s WHERE id=%s",
                    (body.role, user_id)
                )
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="User not found")
    finally:
        conn.close()
    return {"user_id": user_id, "role": body.role}

@router.get("/attendance")
def get_attendance(limit: int = 100, admin=Depends(require_admin)):
    logs = get_all_logs()
    return logs[:limit]
