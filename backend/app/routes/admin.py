from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.database import list_all_users, delete_user, get_all_logs, get_connection
from app.security import require_admin

router = APIRouter()

class RoleUpdate(BaseModel):
    role: str

@router.get("/users")
def list_users(admin=Depends(require_admin)):
    return list_all_users()

@router.delete("/users/{user_id}", status_code=204)
def remove_user(user_id: int, admin=Depends(require_admin)):
    if not delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")

@router.get("/attendance")
def get_attendance(limit: int = 100, admin=Depends(require_admin)):
    return get_all_logs()[:limit]
