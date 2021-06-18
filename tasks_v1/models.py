from typing import Dict

from sqlalchemy import String, Column, Integer, ForeignKey, UniqueConstraint, DateTime, Float
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Task(Base):
    __tablename__ = 'Tasks-v1'

    task_id = Column(Integer, primary_key=True, nullable=False, unique=True)
    desc = Column(String, nullable=False)
    first_scope = Column(String(20), nullable=False)
    category = Column(String)
    created_at = Column(DateTime)
    resolution = Column(String)
    parent_id = Column(Integer, ForeignKey('Tasks-v1.task_id'))
    time_estimate = Column(Float)
    time_actual = Column(Float)
    __table_args__ = (
        UniqueConstraint('desc', 'created_at'),
    )

    def get_children(self):
        return Task.query \
            .filter_by(parent_id=self.task_id) \
            .all()

    def get_parent(self):
        return Task.query \
            .filter_by(task_id=self.parent_id) \
            .one_or_none()

    children = property(get_children)
    parent = property(get_parent)

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

    def as_json(self,
                 include_scopes: bool = True,
                 include_parents: bool = False,
                 include_children: bool = True) -> Dict:
        def get_parentiest_task(t: Task) -> Dict:
            """Look for the highest-level parent"""
            while t.parent_id:
                t = t.get_parent()
            return t

        if include_parents:
            parentiest_task = get_parentiest_task(self)
            include_children = True
            return parentiest_task.as_json(include_scopes, False, True)

        response_dict = self.to_json_dict()
        if include_children:
            child_json = [
                child.as_json(include_scopes, False, True)
                    for child in self.get_children()
            ]
            if child_json:
                response_dict['children'] = child_json

        if include_scopes:
            tsses = TaskTimeScope.query \
                .filter(TaskTimeScope.task_id == self.task_id) \
                .order_by(TaskTimeScope.time_scope_id) \
                .all()
            scopes = [tts.time_scope_id for tts in tsses]
            if scopes:
                response_dict['time_scopes'] = scopes

        return response_dict


class TaskTimeScope(Base):
    __tablename__ = 'TaskTimeScopes-v1'

    task_id = Column(Integer, ForeignKey("Tasks-v1.task_id"), primary_key=True, nullable=False)
    time_scope_id = Column(String, primary_key=True, nullable=False)
    __table_args__ = (
        UniqueConstraint('task_id', 'time_scope_id'),
    )
