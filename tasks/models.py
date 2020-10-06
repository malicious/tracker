from typing import Dict

from dateutil import parser

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

    def _to_json(self) -> Dict:
        """
        Build a dict for JSON response
        """
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
            if getattr(self, field):
                response_dict[field] = getattr(self, field)

        return response_dict

    def to_json(self, recurse: bool = False) -> Dict:
        response_dict = self._to_json()

        if recurse:
            child_json = []
            child_tasks = Task.query \
                .filter(Task.parent_id == self.task_id) \
                .all()
            for c in child_tasks:
                child_json.append(c.to_json(recurse))

            if child_json:
                response_dict['child_tasks'] = child_json

        return response_dict

    def short_time(self) -> str:
        if self.time_estimate and self.time_actual:
            return f"`{self.time_estimate}h => {self.time_actual}h`"
        elif self.time_estimate:
            return f"`{self.time_estimate}h`"
        elif self.time_actual:
            return f"`=> {self.time_actual}`"
        else:
            return ""


class TaskTimeScope(db.Model):
    __tablename__ = 'TaskTimeScopes'
    __bind_key__ = 'tasks'
    task_id = db.Column(db.Integer, db.ForeignKey("Tasks.task_id"), primary_key=True, nullable=False)
    time_scope_id = db.Column(db.String, primary_key=True, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('task_id', 'time_scope_id'),
    )
