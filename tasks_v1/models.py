from typing import Dict

from tracker.db import content_db as db


class Task(db.Model):
    __tablename__ = 'Tasks'
    __bind_key__ = 'tasks'
    task_id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    desc = db.Column(db.String, nullable=False)
    first_scope = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String)
    created_at = db.Column(db.DateTime)
    resolution = db.Column(db.String)
    parent_id = db.Column(db.Integer, db.ForeignKey('Tasks.task_id'))
    time_estimate = db.Column(db.Float)
    time_actual = db.Column(db.Float)
    __table_args__ = (
        db.UniqueConstraint('desc', 'created_at'),
    )

    def get_children(self):
        return Task.query \
            .filter(Task.parent_id == self.task_id) \
            .all()

    def get_parent(self):
        return Task.query \
            .filter(Task.task_id == self.parent_id) \
            .one_or_none()

    def to_json_dict(self) -> Dict:
        response_dict = {
            'task_id': self.task_id,
            'desc': self.desc,
            'first_scope': self.first_scope,
        }

        # Skip null fields, per Google JSON style guide:
        # https://google.github.io/styleguide/jsoncstyleguide.xml#Empty/Null_Property_Values
        if self.created_at is not None:
            response_dict['created_at'] = str(self.created_at)

        for field in ["category", "resolution", "parent_id", "time_estimate", "time_actual"]:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        return response_dict


class TaskTimeScope(db.Model):
    __tablename__ = 'TaskTimeScopes'
    __bind_key__ = 'tasks'
    task_id = db.Column(db.Integer, db.ForeignKey("Tasks.task_id"), primary_key=True, nullable=False)
    time_scope_id = db.Column(db.String, primary_key=True, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('task_id', 'time_scope_id'),
    )
