from sqlalchemy import (
    Column, Integer, String, ForeignKey, CheckConstraint, UniqueConstraint,
    PrimaryKeyConstraint, Index, DateTime, Boolean, func
)
from sqlalchemy.orm import relationship, declarative_base
from pydantic import BaseModel, ConfigDict
from datetime import datetime

Base = declarative_base()

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)

    users = relationship("User", back_populates="organization", cascade="all, delete")

class OrganizationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"))
    delegation_threshold = Column(Integer, default=0)
    available = Column(Boolean, default=True)

    organization = relationship("Organization", back_populates="users")
    document = relationship("Document", back_populates="users")

    def __repr__(self):
        return f"<User(id={self.id}, name={self.full_name})>"

class UserSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str
    delegation_threshold: int
    available: bool

class UserHierarchy(Base):
    __tablename__ = "user_hierarchy"

    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    ancestor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    descendant_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    depth = Column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "ancestor_id", "descendant_id"),
        CheckConstraint("depth >= 0"),
        Index("idx_hierarchy_org_ancestor", "organization_id", "ancestor_id", "depth"),
        Index("idx_hierarchy_org_descendant", "organization_id", "descendant_id"),
    )

class Delegation(Base):
    __tablename__ = "delegations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    expiration_date = Column(DateTime, nullable=True)
    user_id_owner = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_id_delegate = Column(Integer, ForeignKey("users.id"), nullable=False)
    bounded = Column(Boolean, default=False)

    owner = relationship("User", foreign_keys=[user_id_owner])
    delegate = relationship("User", foreign_keys=[user_id_delegate])

    __table_args__ = (
        CheckConstraint("user_id_owner != user_id_delegate", name="owner_not_delegate"),
        UniqueConstraint("user_id_owner", "user_id_delegate", name="unique_owner_delegate_pair"),
    )

class DelegationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    expiration_date: datetime | None
    user_id_owner: int
    user_id_delegate: int
    bounded: bool

class Document(Base):
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    status = Column(String(20), default='inert')

    __table_args__ = (
        CheckConstraint(
            "status IN ('inert', 'pending', 'signed', 'archived')",
            name='ck_documents_status'
        ),
    )

    users = relationship("User", back_populates="document")

class DocumentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    status: str

class DocumentUserLink(Base):
    __tablename__ = 'document_user_links'

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    permission_type = Column(String(20), nullable=False)
    has_signed = Column(Boolean, default=False, nullable=False)
    signed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "permission_type IN ('read', 'sign')",
            name='ck_doc_user_links_permission_type'
        ),
        UniqueConstraint('document_id', 'user_id', 'permission_type', name='uq_doc_user_perm'),

        Index('idx_doc_user_perm', 'document_id', 'permission_type'),
        Index('idx_doc_user_signed', 'document_id', 'has_signed'),
        Index('idx_user_doc', 'user_id', 'document_id'),
    )

    document = relationship("Document", backref="user_links")
    user = relationship("User", backref="document_links")