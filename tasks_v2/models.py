from sqlalchemy.orm import relationship

from tracker.db import content_db as db


class Task(db.Model):
    __tablename__ = 'Tasks_v2'
    __bind_key__ = 'tasks_v2'
    task_id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    desc = db.Column(db.String, nullable=False)
    category = db.Column(db.String)
    created_at = db.Column(db.DateTime)
    time_estimate = db.Column(db.Float)
    __table_args__ = (
        db.UniqueConstraint('desc', 'created_at'),
    )

    linkages = relationship('TaskLinkage', backref='Task')


class TaskLinkage(db.Model):
    __tablename__ = 'TaskLinkages'
    __bind_key__ = 'tasks_v2'
    task_id = db.Column(db.Integer, db.ForeignKey("Tasks_v2.task_id"), primary_key=True, nullable=False)
    time_scope_id = db.Column(db.String, primary_key=True, nullable=False)
    created_at = db.Column(db.DateTime)
    resolution = db.Column(db.String)
    detailed_resolution = db.Column(db.String)
    time_elapsed = db.Column(db.Float)
    __table_args__ = (
        db.UniqueConstraint('task_id', 'time_scope_id'),
    )
