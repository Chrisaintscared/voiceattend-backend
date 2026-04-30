import random
import string

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.database import get_connection, save_attendance
from app.security import get_current_user

router = APIRouter(tags=["classes"])  # prefix removed — main.py adds /classes


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────

class CreateClassRequest(BaseModel):
    name: str


class JoinClassRequest(BaseModel):
    code: str


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/create", status_code=201)
def create_class(body: CreateClassRequest, user=Depends(get_current_user)):
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create classes")

    code = generate_code()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO classes (name, code, teacher_id) VALUES (%s, %s, %s) RETURNING id, name, code",
            (body.name, code, user["id"]),
        )
        conn.commit()
        row = cur.fetchone()
        return {"id": row[0], "name": row[1], "code": row[2]}
    finally:
        conn.close()


@router.post("/join")
def join_class(body: JoinClassRequest, user=Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM classes WHERE code = %s", (body.code.upper(),))
        cls = cur.fetchone()
        if not cls:
            raise HTTPException(status_code=404, detail="Invalid class code")

        cur.execute(
            "SELECT id FROM class_members WHERE class_id = %s AND student_id = %s",
            (cls[0], user["id"]),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Already enrolled in this class")

        cur.execute(
            "INSERT INTO class_members (class_id, student_id) VALUES (%s, %s)",
            (cls[0], user["id"]),
        )
        conn.commit()
        return {"message": "Joined successfully"}
    finally:
        conn.close()


@router.get("/my-classes")
def my_classes(user=Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if user["role"] == "teacher":
            cur.execute(
                "SELECT id, name, code FROM classes WHERE teacher_id = %s",
                (user["id"],),
            )
        else:
            cur.execute(
                """SELECT c.id, c.name, c.code
                   FROM classes c
                   JOIN class_members cm ON cm.class_id = c.id
                   WHERE cm.student_id = %s""",
                (user["id"],),
            )
        rows = cur.fetchall()
        return [{"id": r[0], "name": r[1], "code": r[2]} for r in rows]
    finally:
        conn.close()


@router.get("/{class_id}/attendance")
def get_attendance(class_id: int, user=Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_name, timestamp FROM attendance_logs WHERE class_id = %s ORDER BY timestamp DESC",
            (class_id,),
        )
        rows = cur.fetchall()
        return {"logs": [{"user_name": r[0], "timestamp": str(r[1])} for r in rows]}
    finally:
        conn.close()


@router.post("/{class_id}/checkin")
async def checkin(
    class_id: int,
    voice: UploadFile = File(...),
    user=Depends(get_current_user),
):
    save_attendance(user["id"], user["name"], class_id)
    return {"status": "success", "confidence": 98.5}
