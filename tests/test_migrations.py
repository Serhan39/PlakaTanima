import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.migrations import run_light_migrations
from app.models import User, UserRole


def test_migration_adds_missing_column_to_existing_table():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    # Eski surumdeki gibi, can_manage_equipment SUTUNU OLMADAN "users"
    # tablosunu elle olusturup icine bir satir ekliyoruz.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER NOT NULL PRIMARY KEY,
                    username VARCHAR(64) NOT NULL UNIQUE,
                    hashed_password VARCHAR(255) NOT NULL,
                    role VARCHAR(16) NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (id, username, hashed_password, role, is_active, created_at) "
                # SQLAlchemy Enum(UserRole) varsayilan olarak uye ADINI
                # ("ADMIN") saklar, degerini ("admin") degil.
                "VALUES (1, 'eski_kullanici', 'x', 'ADMIN', 1, '2026-01-01 00:00:00')"
            )
        )

    inspector = inspect(engine)
    assert "can_manage_equipment" not in {c["name"] for c in inspector.get_columns("users")}

    Base.metadata.create_all(bind=engine)  # zaten var olan "users" tablosunu degistirmez
    run_light_migrations(engine, Base)

    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("users")}
    assert "can_manage_equipment" in columns

    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=engine)()
    user = session.query(User).filter(User.username == "eski_kullanici").first()
    assert user is not None
    assert user.role == UserRole.ADMIN
    assert user.can_manage_equipment is False  # geriye donuk dolduruldu (DEFAULT 0)


def test_migration_is_idempotent_when_schema_already_up_to_date():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    # Iki kez calistirmak hata vermemeli (eklenecek eksik sutun kalmadi)
    run_light_migrations(engine, Base)
    run_light_migrations(engine, Base)

    inspector = inspect(engine)
    assert "can_manage_equipment" in {c["name"] for c in inspector.get_columns("users")}
