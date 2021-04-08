from typing import Dict

from sqlalchemy.orm import relationship

from tracker.db import content_db as db


class Task(db.Model):
    __tablename__ = 'Tasks_v2'
    __bind_key__ = 'tasks_v2'
    task_id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    desc = db.Column(db.String, nullable=False)
    category = db.Column(db.String)
    time_estimate = db.Column(db.Float)

    linkages = relationship('TaskLinkage', backref='Task')

    def to_json_dict(self, include_linkages: bool = True) -> Dict:
        response_dict = {
            'task_id': self.task_id,
            'desc': self.desc,
        }

        for field in ['category', 'time_estimate']:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        if include_linkages:
            linkages_for_json = [linkage.to_json_dict() for linkage in self.linkages]
            if linkages_for_json:
                response_dict['linkages'] = linkages_for_json

        return response_dict


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

    def to_json_dict(self) -> Dict:
        """
        Turn into a dict object, for easy JSON printing

        Skips task_id, cause we assume we're getting called by a Task
        """
        response_dict = {
            'time_scope_id': self.time_scope_id,
        }

        if self.created_at is not None:
            response_dict['created_at'] = str(self.created_at)

        for field in ['resolution', 'detailed_resolution', 'time_elapsed']:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        return response_dict
