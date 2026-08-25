import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

EMBEDDING_DIM = 1024  # BAAI/bge-m3

# Source and Document.type are free-form strings (not DB enums) on purpose: adding a
# new source or document type should not require a migration.
Source = str  # "official" | "finki_hub"
DocumentType = str  # "announcement" | "course" | "professor" | "thesis" | "schedule" | "material" | "page"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("url", name="uq_documents_url"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    document: Mapped[Document] = relationship(back_populates="chunks")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)  # {"keywords": [...], "course_codes": [...]}
    confirmed: Mapped[bool] = mapped_column(default=False)
    confirm_token: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SentNotification(Base):
    __tablename__ = "sent_notifications"
    __table_args__ = (
        UniqueConstraint("subscription_id", "document_id", name="uq_sent_notification_sub_doc"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    # Admin-triggered password reset (see core/users.py) — same shape as
    # Subscription.confirm_token, plus an expiry since this one grants account access.
    reset_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SiteSetting(Base):
    """Admin-editable operational settings (scraper limits, scheduler intervals, per-
    scraper enable/disable) — see core/site_settings.py. Deliberately excludes secrets
    (API keys, DB/SMTP credentials, the JWT signing key), which stay .env-only. Keyed
    by name rather than a surrogate id since this is addressed by key everywhere."""

    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
