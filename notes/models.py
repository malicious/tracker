from typing import Dict

from sqlalchemy.orm import relationship

from tracker.db import content_db as db


class Note(db.Model):
    __tablename__ = 'Notes'
    __bind_key__ = 'notes'
    note_id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    time_scope_id = db.Column(db.String(20), nullable=False, index=True)

    # source info (mostly URL, sometimes manually labeled)
    source = db.Column(db.String)
    # note type, used for last-mile CSS styling
    type = db.Column(db.String)

    # short description, used for quick scanning (usually manually written)
    short_desc = db.Column(db.String)
    # long-form note content
    # summary notes will have _only_ this string
    desc = db.Column(db.String)

    # usually machine-generated
    created_at = db.Column(db.DateTime)
    # usually machine-generated, used for sorting within a TimeScope
    # NB this should really be within the given TimeScope
    sort_time = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint('source', 'type', 'sort_time', 'time_scope_id', 'short_desc'),
        db.CheckConstraint('NOT(short_desc IS NULL AND desc IS NULL)'),
        db.Index("import-notes-index-1", 'time_scope_id', 'short_desc'),
        db.Index("import-notes-index-2", 'source', 'type', 'sort_time', 'time_scope_id', 'short_desc', 'desc'),
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


class NoteDomain(db.Model):
    __tablename__ = 'NoteDomains'
    __bind_key__ = 'notes'
    note_id = db.Column(db.Integer, db.ForeignKey('Notes.note_id'), primary_key=True, nullable=False, index=True)
    domain_id = db.Column(db.String, primary_key=True, nullable=False, index=True)
    __table_args__ = (
        db.UniqueConstraint('note_id', 'domain_id'),
        db.Index("note-domain-index", 'note_id', 'domain_id'),
        db.Index("domain-note-index", 'domain_id', 'note_id'),
    )
