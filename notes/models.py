from typing import Dict

from sqlalchemy import String, Column, Integer, ForeignKey, UniqueConstraint, DateTime, Index, CheckConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Note(Base):
    __tablename__ = 'Notes'

    note_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    time_scope_id = Column(String(20), nullable=False, index=True)

    # source info (mostly URL, sometimes manually labeled)
    source = Column(String)
    # note type, used for last-mile CSS styling
    type = Column(String)

    # short description, used for quick scanning (usually manually written)
    short_desc = Column(String)
    # long-form note content
    # summary notes will have _only_ this string
    desc = Column(String)

    # usually machine-generated
    created_at = Column(DateTime)
    # usually machine-generated, used for sorting within a TimeScope
    # NB this should really be within the given TimeScope
    sort_time = Column(DateTime)

    __table_args__ = (
        UniqueConstraint('source', 'type', 'sort_time', 'time_scope_id', 'short_desc'),
        CheckConstraint('NOT(short_desc IS NULL AND desc IS NULL)'),
        Index("import-notes-index-1", 'time_scope_id', 'short_desc'),
        Index("import-notes-index-2", 'source', 'type', 'sort_time', 'time_scope_id', 'short_desc', 'desc'),
    )

    domains = relationship('NoteDomain', backref='Note')

    def to_json(self, include_domains: bool = False) -> Dict:
        response_dict = {
            'note_id': self.note_id,
            'time_scope_id': self.time_scope_id,
        }

        for field in ['source', 'type', 'short_desc', 'desc', 'created_at', 'sort_time']:
            value = getattr(self, field)
            if value:
                response_dict[field] = value

        if include_domains:
            if self.domains:
                response_dict['domains'] = [nd.domain_id for nd in self.domains]

        return response_dict


class NoteDomain(Base):
    __tablename__ = 'NoteDomains'
    __bind_key__ = 'notes'
    note_id = Column(Integer, ForeignKey('Notes.note_id'), primary_key=True, nullable=False, index=True)
    domain_id = Column(String, primary_key=True, nullable=False, index=True)
    __table_args__ = (
        UniqueConstraint('note_id', 'domain_id'),
        Index("note-domain-index", 'note_id', 'domain_id'),
        Index("domain-note-index", 'domain_id', 'note_id'),
    )
