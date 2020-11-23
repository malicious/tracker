from typing import Dict

from tracker.db import content_db as db


class Note(db.Model):
    __tablename__ = 'Notes'
    __bind_key__ = 'notes'
    note_id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    time_scope_id = db.Column(db.String(20), nullable=False)

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
    sort_time = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint('source', 'type', 'sort_time', 'time_scope_id', 'short_desc'),
        db.CheckConstraint('NOT(short_desc IS NULL AND desc IS NULL)'),
    )

    def to_json(self) -> Dict:
        response_dict = {
            'note_id': self.note_id,
            'time_scope_id': self.time_scope_id,
        }

        for field in ['source', 'type', 'short_desc', 'desc']:
            value = getattr(self, field)
            if value:
                response_dict[field] = repr(value)

        for field in ['created_at', 'sort_time']:
            value = getattr(self, field)
            if value:
                response_dict[field] = str(value)

        return response_dict


class NoteDomain(db.Model):
    __tablename__ = 'NoteDomains'
    __bind_key__ = 'notes'
    note_id = db.Column(db.Integer, db.ForeignKey('Notes.note_id'), primary_key=True, nullable=False)
    domain_id = db.Column(db.String, primary_key=True, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('note_id', 'domain_id'),
    )
