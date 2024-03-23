import json
from datetime import datetime
from typing import Dict, Iterable

from markupsafe import escape
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, UniqueConstraint, Date, text
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Task(Base):
    __tablename__ = 'Tasks'

    task_id = Column(Integer, primary_key=True, nullable=False,
                     default=text("IFNULL((SELECT MAX(task_id) FROM Tasks) + 1, 1)"))
    import_source = Column(String, primary_key=True, nullable=False, default='')

    desc = Column(String, nullable=False)
    desc_for_llm = Column(String)

    category = Column(String)
    time_estimate = Column(Float)

    linkages = relationship(
        'TaskLinkage',
        primaryjoin=(
            "and_(Task.task_id == TaskLinkage.task_id, "
            "Task.import_source == TaskLinkage.import_source)"
        ),
        backref='task',
    )

    def __repr__(self):
        maybe_import_source = f"{self.import_source}/"
        if not self.import_source:
            maybe_import_source = ""
        return f"<Task {maybe_import_source}t#{self.task_id}>"

    def as_json_dict(self, include_linkages: bool = True) -> Dict:
        response_dict = {
            'task_id': self.task_id,
            'import_source': self.import_source,
            'desc': self.desc,
        }

        for field in ['desc_for_llm', 'category', 'time_estimate']:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        if include_linkages:
            linkages_for_dict = [linkage.as_json_dict() for linkage in self.linkages]
            if linkages_for_dict:
                response_dict['linkages'] = linkages_for_dict

        return response_dict

    def as_json(self, do_escape: bool = True) -> str:
        json_str = json.dumps(self.as_json_dict(), indent=2, ensure_ascii=False)
        return escape(json_str)

    def linkage_at(self, requested_scope_id: str, create_if_none: bool = True):
        requested_scope = datetime.strptime(requested_scope_id, '%G-ww%V.%u').date()

        linkage = (
            TaskLinkage.query
            .filter_by(
                task_id=self.task_id,
                import_source=self.import_source,
                time_scope=requested_scope)
            .one_or_none()
        )
        if linkage:
            return linkage

        if create_if_none:
            linkage = TaskLinkage(
                task_id=self.task_id,
                import_source=self.import_source,
                time_scope=requested_scope)
            linkage.created_at = datetime.now()
            return linkage

        return None

    def get_time_elapsed(self):
        return sum([tl.time_elapsed for tl in self.linkages if tl.time_elapsed])

    def split_categories(self, default: str | None = None) -> Iterable[str]:
        if self.category is None:
            if default is not None:
                yield default
            return

        # NB: No double-ampersands supported, because…
        #     too lazy to figure out how to share code with `notes_v2.add.tokenize_domain_ids()`
        for domain in self.category.split('&'):
            # Depends on the caller to remove "blank" categories
            yield domain.strip()


class TaskLinkage(Base):
    __tablename__ = 'TaskLinkages'

    task_id = Column(Integer, ForeignKey(Task.task_id), primary_key=True, nullable=False)
    import_source = Column(String, ForeignKey(Task.import_source), primary_key=True, nullable=False)
    time_scope = Column(Date, primary_key=True, nullable=False)

    # Note that timestamps are always promoted to microsecond precision, for storage consistency.
    # See `sqlalchemy.dialects.sqlite.DATETIME`.
    created_at = Column(DateTime, nullable=False)

    time_elapsed = Column(Float)
    resolution = Column(String)
    detailed_resolution = Column(String)

    __table_args__ = (
        UniqueConstraint('task_id', 'import_source', 'time_scope'),
    )

    @property
    def time_scope_id(self):
        if not self.time_scope:
            return self.time_scope

        return self.time_scope.strftime("%G-ww%V.%u")

    @time_scope_id.setter
    def time_scope_id(self, value: str):
        self.time_scope = datetime.strptime(value, '%G-ww%V.%u').date()

    def __repr__(self):
        maybe_import_source = f"{self.import_source}/"
        if not self.import_source:
            maybe_import_source = ""
        return f"<TaskLinkage {maybe_import_source}t#{self.task_id}/{self.time_scope_id}>"

    def as_json_dict(self) -> Dict:
        """
        Turn into a dict object, for easy JSON printing

        Skips task_id and import_source, cause we assume we're getting called by a Task
        """
        response_dict = {
            'time_scope_id': self.time_scope_id,
            'created_at': str(self.created_at),
        }

        # Check optional fields separately
        for field in ['time_elapsed', 'resolution', 'detailed_resolution']:
            if getattr(self, field) is not None:
                response_dict[field] = getattr(self, field)

        return response_dict
