def save_attendance(user_id: int, user_name: str, class_id: int | None = None) -> dict:
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            INSERT INTO attendance_logs (user_name, class_id)
            VALUES (%s, %s)
            RETURNING *;
            """,
            (user_name, class_id),
        )
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()
