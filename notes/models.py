from typing import Dict

from tracker.content import content_db as db


class Note(db.Model):
    __tablename__ = 'Notes'
    note_id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    time_scope_id = db.Column(db.String(20), nullable=False)
    desc = db.Column(db.String)
    title = db.Column(db.String)
    created_at = db.Column(db.DateTime)
    is_summary = db.Column(db.Boolean)
    source = db.Column(db.String)
    __table_args__ = (
        db.UniqueConstraint('time_scope_id', 'desc', 'title'),
        db.CheckConstraint('NOT(desc IS NULL AND title IS NULL)'),
    )

    def to_json(self) -> Dict:
        response_dict = {
            'note_id': self.note_id,
            'time_scope_id': self.time_scope_id,
        }

        if self.created_at is not None:
            response_dict['created_at'] = str(self.created_at)
        if self.is_summary is not None:
            response_dict['is_summary'] = str(self.is_summary)
        for field in ["desc", "title", "source"]:
            if getattr(self, field):
                response_dict[field] = getattr(self, field)

        return response_dict


class Domain(db.Model):
    __tablename__ = 'Domains'
    domain_id = db.Column(db.String, primary_key=True, nullable=False, unique=True)
    is_person = db.Column(db.Boolean)


class NoteDomain(db.Model):
    __tablename__ = 'NoteDomains'
    note_id = db.Column(db.Integer, db.ForeignKey('Notes.note_id'), primary_key=True, nullable=False)
    domain_id = db.Column(db.String, db.ForeignKey('Domains.domain_id'), primary_key=True, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('note_id', 'domain_id'),
    )
