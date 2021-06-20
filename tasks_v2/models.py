from datetime import datetime
from typing import Dict

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, UniqueConstraint, Date
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Task(Base):
    __tablename__ = 'Tasks'

    task_id = Column(Integer, primary_key=True, nullable=False)
    desc = Column(String, nullable=False)
    category = Column(String)
    time_estimate = Column(Float)

    linkages = relationship('TaskLinkage', backref='task')

    def __repr__(self):
        return f"<Task#{self.task_id}>"

    def as_json(self, include_linkages: bool = True) -> Dict:
        response_dict = {
            'task_id': self.task_id,
            'desc': self.desc,
        }

        for field in ['category', 'time_estimate']:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        if include_linkages:
            linkages_for_dict = [linkage.as_json() for linkage in self.linkages]
            if linkages_for_dict:
                response_dict['linkages'] = linkages_for_dict

        return response_dict

    def linkage_at(self, requested_scope_id: str, create_if_none: bool = True):
        requested_scope = datetime.strptime(requested_scope_id, '%G-ww%V.%u').date()
        linkage = TaskLinkage.query \
            .filter_by(task_id=self.task_id, time_scope=requested_scope) \
            .one_or_none()
        if linkage:
            return linkage

        if create_if_none:
            linkage = TaskLinkage(task_id=self.task_id, time_scope=requested_scope)
            linkage.created_at = datetime.now()
            return linkage

        raise ValueError(f"Couldn't find TaskLinkage for #{self.task_id}/{requested_scope}")


class TaskLinkage(Base):
    __tablename__ = 'TaskLinkages'

    task_id = Column(Integer, ForeignKey("Tasks.task_id"), primary_key=True, nullable=False)
    time_scope = Column(Date, primary_key=True, nullable=False)
    created_at = Column(DateTime)
    resolution = Column(String)
    detailed_resolution = Column(String)
    time_elapsed = Column(Float)
    __table_args__ = (
        UniqueConstraint('task_id', 'time_scope'),
    )

    @property
    def time_scope_id(self):
        if not self.time_scope:
            return self.time_scope

        return self.time_scope.strftime("%G-ww%V.%u")

    @time_scope_id.setter
    def time_scope_id(self, value: str):
        self.time_scope = datetime.strptime(value, '%G-ww%V.%u').date()

    def as_json(self) -> Dict:
        """
        Turn into a dict object, for easy JSON printing

        Skips task_id, cause we assume we're getting called by a Task
        """
        response_dict = {
        }

        if self.created_at is not None:
            response_dict['created_at'] = str(self.created_at)

        for field in ['time_scope_id', 'resolution', 'detailed_resolution', 'time_elapsed']:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        return response_dict
