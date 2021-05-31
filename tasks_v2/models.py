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

    linkages = relationship('TaskLinkage', backref='Task')

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


class TaskLinkage(Base):
    __tablename__ = 'TaskLinkages'

    task_id = Column(Integer, ForeignKey("Tasks.task_id"), primary_key=True, nullable=False)
    time_scope_id = Column(Date, primary_key=True, nullable=False) # TODO: make _id a derived property
    created_at = Column(DateTime)
    resolution = Column(String)
    detailed_resolution = Column(String)
    time_elapsed = Column(Float)
    __table_args__ = (
        UniqueConstraint('task_id', 'time_scope_id'),
    )

    def __repr__(self):
        return f"<TaskLinkage-#{self.task_id}-{self.time_scope_id}>"

    def as_json(self) -> Dict:
        """
        Turn into a dict object, for easy JSON printing

        Skips task_id, cause we assume we're getting called by a Task
        """
        response_dict = {
            'time_scope_id': self.time_scope_id.strftime("%G-ww%V.%u"),
        }

        if self.created_at is not None:
            response_dict['created_at'] = str(self.created_at)

        for field in ['resolution', 'detailed_resolution', 'time_elapsed']:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        return response_dict
