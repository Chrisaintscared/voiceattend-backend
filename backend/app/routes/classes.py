import random
import string
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from app.database import get_connection
from app.security import get_current_user

router = APIRouter()

def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ─── MODELS ───────────────────────────────────────

class CreateClassRequest(BaseModel):
    name: str

class JoinClassRequest(BaseModel):
    code: str


# ─── TEACHER: CREATE CLASS ────────────────────────

@router.post("/create", status_code=201)
def create_class(body: CreateClassRequest, user=Depends(get_current_user)):
    if user['role'] != 'teacher':
        raise HTTPException(status_code=403, detail="Only teachers can create classes")

    code = generate_code()
    conn = get_connection()
    try:
        cur = conn.cursor()
        for _ in range(5):
            cur.execute("SELECT id FROM classes WHERE code = %s", (code,))
            if not cur.fetchone():
                break
            code = generate_code()

        cur.execute("""
            INSERT INTO classes (name, code, teacher_id)
            VALUES (%s, %s, %s)
            RETURNING id, name, code, teacher_id, created_at;
        """, (body.name, code, user['id']))
        conn.commit()
        row = cur.fetchone()
        return {
            "id": row[0],
            "name": row[1],
            "code": row[2],
            "teacher_id": row[3],
            "created_at": str(row[4]),
        }
    finally:
        conn.close()


# ─── STUDENT: JOIN CLASS ──────────────────────────

@router.post("/join")
def join_class(body: JoinClassRequest, user=Depends(get_current_user)):
    if user['role'] != 'student':
        raise HTTPException(status_code=403, detail="Only students can join classes")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM classes WHERE code = %s", (body.code.upper(),))
        cls = cur.fetchone()
        if not cls:
            raise HTTPException(status_code=404, detail="Invalid class code")

        class_id, class_name = cls

        cur.execute("""
            SELECT id FROM class_members
            WHERE class_id = %s AND student_id = %s
        """, (class_id, user['id']))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Already joined this class")

        cur.execute("""
            INSERT INTO class_members (class_id, student_id)
            VALUES (%s, %s)
        """, (class_id, user['id']))
        conn.commit()
        return {
            "message": f"Joined '{class_name}' successfully",
            "class_id": class_id,
            "class_name": class_name
        }
    finally:
        conn.close()


# ─── GET MY CLASSES ───────────────────────────────

@router.get("/my-classes")
def my_classes(user=Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if user['role'] == 'teacher':
            cur.execute("""
                SELECT c.id, c.name, c.code, c.created_at,
                       COUNT(cm.student_id) as member_count
                FROM classes c
                LEFT JOIN class_members cm ON cm.class_id = c.id
                WHERE c.teacher_id = %s
                GROUP BY c.id
                ORDER BY c.created_at DESC
            """, (user['id'],))
        else:
            cur.execute("""
                SELECT c.id, c.name, c.code, c.created_at,
                       u.name as teacher_name
                FROM classes c
                JOIN class_members cm ON cm.class_id = c.id
                JOIN users u ON u.id = c.teacher_id
                WHERE cm.student_id = %s
                ORDER BY c.created_at DESC
            """, (user['id'],))

        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


# ─── TEACHER: GET CLASS MEMBERS ───────────────────

@router.get("/{class_id}/members")
def get_members(class_id: int, user=Depends(get_current_user)):
    if user['role'] != 'teacher':
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.name, u.email, cm.joined_at
            FROM class_members cm
            JOIN users u ON u.id = cm.student_id
            WHERE cm.class_id = %s
            ORDER BY cm.joined_at DESC
        """, (class_id,))
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


# ─── GET CLASS ATTENDANCE ─────────────────────────

@router.get("/{class_id}/attendance")
def get_class_attendance(class_id: int, user=Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if user['role'] == 'teacher':
            cur.execute("""
                SELECT al.id, al.user_name, al.timestamp, al.class_id
                FROM attendance_logs al
                WHERE al.class_id = %s
                ORDER BY al.timestamp DESC
            """, (class_id,))
        else:
            cur.execute("""
                SELECT al.id, al.user_name, al.timestamp, al.class_id
                FROM attendance_logs al
                WHERE al.class_id = %s AND al.user_name = %s
                ORDER BY al.timestamp DESC
            """, (class_id, user['name']))

        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return {"logs": [dict(zip(cols, row)) for row in rows]}
    finally:
        conn.close()


# ─── MARK ATTENDANCE FOR A CLASS ─────────────────

@router.post("/{class_id}/checkin")
async def checkin(class_id: int, voice: UploadFile = File(...), user=Depends(get_current_user)):
    from app.services.voice_service import extract_voice_embedding, find_best_match
    from app.database import get_all_voice_profiles, get_user_by_id

    audio_bytes = await voice.read()

    try:
        query_emb = extract_voice_embedding(audio_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Voice processing failed: {e}")

    profiles = get_all_voice_profiles()
    if not profiles:
        raise HTTPException(status_code=404, detail="No voice profiles enrolled")

    match, score = find_best_match(query_emb, profiles)
    if not match:
        raise HTTPException(
            status_code=401,
            detail=f"Voice not recognised (score: {score:.3f})"
        )

    matched_user = get_user_by_id(match["user_id"])
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Verify matched user is in this class
        cur.execute("""
            SELECT id FROM class_members
            WHERE class_id = %s AND student_id = %s
        """, (class_id, matched_user["id"]))
        if not cur.fetchone():
            raise HTTPException(
                status_code=403,
                detail=f"{matched_user['name']} is not enrolled in this class"
            )

        # Prevent duplicate check-in same day
        cur.execute("""
            SELECT id FROM attendance_logs
            WHERE class_id = %s AND user_name = %s
            AND timestamp::date = CURRENT_DATE
        """, (class_id, matched_user["name"]))
        if cur.fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"{matched_user['name']} already checked in today"
            )

        cur.execute("""
            INSERT INTO attendance_logs (user_name, class_id)
            VALUES (%s, %s)
            RETURNING id, user_name, timestamp, class_id;
        """, (matched_user["name"], class_id))
        conn.commit()
        row = cur.fetchone()
        return {
            "id": row[0],
            "user_name": row[1],
            "matched_name": matched_user["name"],
            "confidence": round(score * 100, 1),
            "timestamp": str(row[2]),
            "class_id": row[3],
        }
    finally:
        conn.close()
