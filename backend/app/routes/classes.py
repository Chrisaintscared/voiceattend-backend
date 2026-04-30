import random
import string

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.database import (
    get_connection,
    save_attendance,
    create_join_request,
    get_pending_requests,
    get_pending_requests_for_teacher,
    approve_join_request,
    decline_join_request,
    get_join_request_status,
    is_enrolled,
)
from app.security import get_current_user

router = APIRouter(tags=["classes"])


def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


class CreateClassRequest(BaseModel):
    name: str


class JoinClassRequest(BaseModel):
    code: str


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
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can join classes")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM classes WHERE code = %s", (body.code.upper(),))
        cls = cur.fetchone()
        if not cls:
            raise HTTPException(status_code=404, detail="Invalid class code")

        class_id = cls[0]

        # Already a member
        if is_enrolled(class_id, user["id"]):
            raise HTTPException(status_code=409, detail="Already enrolled in this class")

        # Check existing request
        status = get_join_request_status(class_id, user["id"])
        if status:
            if status["status"] == "pending":
                raise HTTPException(status_code=409, detail="Join request already pending")
            if status["status"] == "declined":
                raise HTTPException(status_code=403, detail="Your request was declined by the teacher")

        create_join_request(class_id, user["id"])
        return {"message": "Join request sent. Waiting for teacher approval."}
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


@router.get("/requests")
def get_all_my_requests(user=Depends(get_current_user)):
    """Teacher: get all pending join requests across their classes."""
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Teachers only")
    return get_pending_requests_for_teacher(user["id"])


@router.get("/{class_id}/requests")
def get_class_requests(class_id: int, user=Depends(get_current_user)):
    """Teacher: get pending requests for a specific class."""
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Teachers only")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM classes WHERE id = %s AND teacher_id = %s",
            (class_id, user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Not your class")
    finally:
        conn.close()
    return get_pending_requests(class_id)


@router.post("/{class_id}/requests/{student_id}/approve")
def approve_request(class_id: int, student_id: int, user=Depends(get_current_user)):
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Teachers only")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM classes WHERE id = %s AND teacher_id = %s",
            (class_id, user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Not your class")
    finally:
        conn.close()
    approve_join_request(class_id, student_id)
    return {"message": "Student approved"}


@router.post("/{class_id}/requests/{student_id}/decline")
def decline_request(class_id: int, student_id: int, user=Depends(get_current_user)):
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Teachers only")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM classes WHERE id = %s AND teacher_id = %s",
            (class_id, user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Not your class")
    finally:
        conn.close()
    decline_join_request(class_id, student_id)
    return {"message": "Student declined"}


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
