"""Ilk yonetici hesabini olusturur. Kullanim:
python -m scripts.seed_admin <kullanici_adi> <sifre>"""

import sys

from app.database import Base, SessionLocal, engine
from app.models import User, UserRole
from app.security import hash_password


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Kullanim: python -m scripts.seed_admin <kullanici_adi> <sifre>")

    username, password = sys.argv[1], sys.argv[2]
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first():
            raise SystemExit(f"'{username}' kullanicisi zaten mevcut")
        admin = User(username=username, hashed_password=hash_password(password), role=UserRole.ADMIN)
        db.add(admin)
        db.commit()
        print(f"Yonetici hesabi olusturuldu: {username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
