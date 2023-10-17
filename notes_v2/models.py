import operator
from typing import Dict, List

from dateutil import parser
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

    def get_domain_ids(self):
        return map(operator.attrgetter('domain_id'), self.domains)

    def as_json(self, include_domains: bool = False) -> Dict:
        """
        Converts the Note into a dict object, usable for JSON-y functions

        This is also the serialization format; this dict gets converted into CSV.
        """
        response_dict = {
            'note_id': self.note_id,
            'time_scope_id': self.time_scope_id,
            'desc': self.desc,
        }

        for datetime_field in ['sort_time', 'created_at']:
            if getattr(self, datetime_field) is not None:
                response_dict[datetime_field] = str(getattr(self, datetime_field))

        for field in ['source', 'detailed_desc']:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        if include_domains:
            if self.domains:
                response_dict['domains'] = list(self.get_domain_ids())

        return response_dict

    @classmethod
    def from_dict(cls, serialized: Dict):
        # Remove entries that have an empty string value, because that's how the CSV package works
        for field in list(serialized.keys()):
            if not serialized[field]:
                del serialized[field]

        # If there's nothing _left_ for that dict, just, stop
        if not serialized:
            return None

        # Convert datetime objects into... datetimes
        for datetime_field in ['sort_time', 'created_at']:
            if datetime_field in serialized:
                serialized[datetime_field] = parser.parse(serialized[datetime_field])

        return cls(**serialized)


class NoteDomain(Base):
    __tablename__ = 'NoteDomains-v2'

    note_id = Column(Integer, ForeignKey('Notes-v2.note_id'), primary_key=True, nullable=False, index=True)
    domain_id = Column(String, primary_key=True, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint('note_id', 'domain_id'),
        Index("note-domain-index", 'note_id', 'domain_id'),
        Index("domain-note-index", 'domain_id', 'note_id'),
    )
