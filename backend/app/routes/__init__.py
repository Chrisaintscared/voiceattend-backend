from fastapi import APIRouter
from . import auth, admin, attendance, classes, enroll

router = APIRouter()
router.include_router(auth.router, prefix="/auth")
router.include_router(admin.router, prefix="/admin")
router.include_router(attendance.router, prefix="/attendance")
router.include_router(classes.router, prefix="/classes")
router.include_router(enroll.router, prefix="/enroll")
