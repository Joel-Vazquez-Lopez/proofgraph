import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Text, Boolean, Integer, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine
from app.config import settings

Base = declarative_base()


class DisputeCaseDB(Base):
    __tablename__ = "dispute_cases"

    dispute_id = Column(String(100), primary_key=True, index=True)
    category = Column(String(50), nullable=False)
    state = Column(String(50), nullable=False, default="CREATED")
    data_source = Column(String(50), nullable=False, default="SYNTHETIC_FIXTURE")
    amount = Column(Float, nullable=False, default=0.0)
    currency = Column(String(10), nullable=False, default="USD")
    buyer_id = Column(String(100), nullable=False)
    seller_id = Column(String(100), nullable=False)
    transaction_id = Column(String(100), nullable=False)
    buyer_claim = Column(Text, nullable=False)
    seller_response = Column(Text, nullable=True)
    
    # Serialized graph and readiness cache
    graph_json = Column(Text, nullable=True, default="{}")
    readiness_json = Column(Text, nullable=True, default="{}")
    policy_decision_json = Column(Text, nullable=True, default="{}")
    timeline_json = Column(Text, nullable=True, default="[]")
    integrity_findings_json = Column(Text, nullable=True, default="[]")
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GraphNodeDB(Base):
    __tablename__ = "graph_nodes"

    id = Column(String(120), primary_key=True)
    dispute_id = Column(String(100), index=True, nullable=False)
    node_type = Column(String(50), nullable=False)
    label = Column(String(200), nullable=False)
    content_json = Column(Text, nullable=False, default="{}")
    source = Column(String(100), nullable=False)
    origin = Column(String(50), nullable=False, default="UNVERIFIED")
    verification_status = Column(String(50), nullable=False, default="UNVERIFIED")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    verified_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")


class GraphEdgeDB(Base):
    __tablename__ = "graph_edges"

    id = Column(String(120), primary_key=True)
    dispute_id = Column(String(100), index=True, nullable=False)
    source_id = Column(String(120), nullable=False, index=True)
    target_id = Column(String(120), nullable=False, index=True)
    edge_type = Column(String(50), nullable=False)
    provenance = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0)
    metadata_json = Column(Text, nullable=False, default="{}")


class EvidenceItemDB(Base):
    __tablename__ = "evidence_items"

    id = Column(String(120), primary_key=True)
    dispute_id = Column(String(100), index=True, nullable=False)
    action_id = Column(String(100), nullable=True)
    submitter_role = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)
    carrier_name = Column(String(100), nullable=True)
    tracking_number = Column(String(120), nullable=True)
    file_path = Column(String(300), nullable=True)
    sha256_hash = Column(String(64), nullable=True)
    mime_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# Database engine and session factory
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
