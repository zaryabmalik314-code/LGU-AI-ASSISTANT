from sqlalchemy import (
    Column, Integer, String, Float, Date, Text, JSON, ForeignKey, Boolean, ARRAY
)
from sqlalchemy.orm import relationship
from app.db.session import Base


class Program(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    department = Column(String)
    duration_years = Column(Float)
    is_active = Column(Boolean, default=True)
    preferred_stream = Column(String, nullable=True)  # e.g. "ICS" — best-fit stream, distinct from *eligible* streams in AdmissionRule

    rules = relationship("AdmissionRule", back_populates="program")
    content = relationship("ProgramContent", back_populates="program", uselist=False)


class AdmissionRule(Base):
    """Versioned. Never overwrite — old row gets effective_to set, new row added."""
    __tablename__ = "admission_rules"

    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=False)
    allowed_streams = Column(ARRAY(String), nullable=False)   # e.g. ["Pre-Engineering","ICS"]
    min_matric_pct = Column(Float, nullable=False)
    min_inter_pct = Column(Float, nullable=False)
    required_subjects = Column(ARRAY(String), default=[])
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)  # null = currently active
    source_url = Column(String)
    verified_by = Column(String)

    program = relationship("Program", back_populates="rules")


class ProgramContent(Base):
    __tablename__ = "program_content"

    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=False, unique=True)
    description = Column(Text)
    curriculum = Column(Text)
    career_opportunities = Column(Text)
    required_skills = Column(ARRAY(String), default=[])
    interest_tags = Column(ARRAY(String), default=[])   # for scoring step later
    career_keywords = Column(ARRAY(String), default=[])

    program = relationship("Program", back_populates="content")


class RecommendationLog(Base):
    __tablename__ = "recommendation_log"

    id = Column(Integer, primary_key=True)
    profile_hash = Column(String, index=True)
    input_profile = Column(JSON)
    eligible_program_ids = Column(ARRAY(Integer))
    ranked_program_ids = Column(ARRAY(Integer))
    rule_version_ids = Column(ARRAY(Integer))
    model_version = Column(String)
    llm_output = Column(JSON, nullable=True)
    created_at = Column(String)
