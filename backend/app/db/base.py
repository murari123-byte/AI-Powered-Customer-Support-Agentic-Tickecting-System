from enum import StrEnum

from sqlalchemy import CheckConstraint, Enum, MetaData
from sqlalchemy.orm import DeclarativeBase

# Predictable constraint names (e.g. "fk_tickets_customer_id_users"), so later migrations can
# refer to them by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Parent class of every table model. Alembic reads Base.metadata to detect changes."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_column(enum_class: type[StrEnum]) -> Enum:
    """Store a Python enum as plain text (VARCHAR). Pair it with one_of() in __table_args__."""
    return Enum(
        enum_class,
        native_enum=False,
        create_constraint=False,  # we add our own named CHECK with one_of()
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


def one_of(column: str, enum_class: type[StrEnum]) -> CheckConstraint:
    """CHECK (<column> IN (...)): the database itself rejects unknown values."""
    values = ", ".join(f"'{member.value}'" for member in enum_class)
    return CheckConstraint(f"{column} IN ({values})", name=column)
