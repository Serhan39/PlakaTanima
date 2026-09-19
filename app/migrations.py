"""Alembic gibi tam bir migrasyon araci kullanmiyoruz (kucuk/tek sunuculu
bir kurulum icin gereksiz agirlik); bunun yerine her baslangicta, modelde
tanimli olup veritabaninda henuz olmayan sutunlari basitce ALTER TABLE ile
ekleyen hafif bir mekanizma kullaniyoruz. Boylece musteri veritabanindaki
mevcut veriler (kullanicilar, izleme listesi, tespit kayitlari...) yeni bir
surume gecerken kaybolmaz - sadece eksik sutunlar tamamlanir.

`Base.metadata.create_all()` SADECE hic olmayan tablolari olusturur, var
olan bir tabloya sonradan eklenen sutunlari eklemez; bu modul o boslugu
doldurur."""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("sertek_alpr.migrations")


def _default_sql_literal(column) -> str:
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return ""
    value = default.arg
    if isinstance(value, bool):
        return f" DEFAULT {1 if value else 0}"
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    return ""


def run_light_migrations(engine: Engine, base) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all zaten olusturdu, eksik sutun soz konusu degil

            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue

                col_type = column.type.compile(dialect=engine.dialect)
                default_clause = _default_sql_literal(column)
                logger.warning("Eksik sutun ekleniyor: %s.%s (%s)", table.name, column.name, col_type)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_clause}'))
