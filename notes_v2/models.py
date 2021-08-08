from typing import Dict

from sqlalchemy import String, Column, Integer, ForeignKey, UniqueConstraint, DateTime, Index
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Note(Base):
    """
    Notes represent variable data, in a NoSQL-kinda way

    Three main kinds of notes, so far:

    1. event notes, for manual reference when you need to find specific data
        - marking e.g. X email account was created on Y date with Z credentials
    2. summary notes, for manual _review_ when you want to look over the past
        - e.g. notes from say, a phone conversation with X online service
    3. notes with data for later automated processing
        - like "ate 1500 calories today" or "weighed 150 lbs"

    There's very little reason to represent these in the database schema, so at
    best we have some of the domains tagged something like "email: summary",
    and use CSS to format Notes appropriately.
    """
    __tablename__ = 'Notes-v2'

    note_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    time_scope_id = Column(String(20), nullable=False, index=True)
    sort_time = Column(DateTime)

    source = Column(String)

    desc = Column(String, nullable=False)
    detailed_desc = Column(String)
    created_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint('time_scope_id', 'sort_time', 'source', 'desc', 'detailed_desc', 'created_at'),
        Index("import-notes-index-1", 'time_scope_id', 'desc'),
        Index("import-notes-index-2", 'time_scope_id', 'sort_time', 'source', 'desc', 'detailed_desc'),
    )

    domains = relationship('NoteDomain', backref='Note')


class NoteDomain(Base):
    __tablename__ = 'NoteDomains-v2'

    note_id = Column(Integer, ForeignKey('Notes-v2.note_id'), primary_key=True, nullable=False, index=True)
    domain_id = Column(String, primary_key=True, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint('note_id', 'domain_id'),
        Index("note-domain-index", 'note_id', 'domain_id'),
        Index("domain-note-index", 'domain_id', 'note_id'),
    )
