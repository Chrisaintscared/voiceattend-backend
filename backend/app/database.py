def get_user_by_id_internal(user_id: int):
    """Same as get_user_by_id but returns password_hash too (for auth checks)."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()

def get_all_voice_profiles():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT user_id, embedding FROM voice_profiles")
        return cur.fetchall()
    finally:
        conn.close()

def get_voice_profile(user_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM voice_profiles WHERE user_id = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()

def save_attendance(user_id: int, user_name: str, class_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO attendance_logs (user_id, user_name, class_id) VALUES (%s, %s, %s)",
            (user_id, user_name, class_id),
        )
        conn.commit()
    finally:
        conn.close()

def has_attendance_today(class_id: int, user_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM attendance_logs
            WHERE user_id = %s AND class_id = %s
              AND timestamp::date = CURRENT_DATE
            """,
            (user_id, class_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()

def is_enrolled(class_id: int, user_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM class_members WHERE class_id = %s AND student_id = %s",
            (class_id, user_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()

def get_attendance_logs(user_id: int, class_id: int | None = None):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if class_id:
            cur.execute(
                """
                SELECT l.id, l.user_name, l.timestamp, c.name AS class_name
                FROM attendance_logs l
                JOIN classes c ON l.class_id = c.id
                WHERE l.user_id = %s AND l.class_id = %s
                ORDER BY l.timestamp DESC
                """,
                (user_id, class_id),
            )
        else:
            cur.execute(
                """
                SELECT l.id, l.user_name, l.timestamp, c.name AS class_name
                FROM attendance_logs l
                JOIN classes c ON l.class_id = c.id
                WHERE l.user_id = %s
                ORDER BY l.timestamp DESC
                """,
                (user_id,),
            )
        return cur.fetchall()
    finally:
        conn.close()

def update_user_password(user_id: int, password_hash: str):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (password_hash, user_id),
        )
        conn.commit()
    finally:
        conn.close()
