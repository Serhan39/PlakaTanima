from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import UserCreate, UserRead
from app.security import hash_password, require_roles

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserRead], dependencies=[Depends(require_roles(UserRole.ADMIN))])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserRead, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu kullanici adi zaten kayitli")
    user = User(username=payload.username, hashed_password=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
