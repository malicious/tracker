import json
from datetime import datetime
from typing import Optional, List

from sqlalchemy.exc import IntegrityError, StatementError

from tasks_v1.models import Task as Task_v1, TaskTimeScope
from tasks_v1.time_scope import TimeScope
from tasks_v2.models import Task as Task_v2, TaskLinkage

MIGRATION_BATCH_SIZE = 50


def _force_day_scope(scope_str):
    maybe_scope = TimeScope(scope_str)
    if maybe_scope.type == TimeScope.Type.quarter:
        # Convert "quarter" scopes into their first day
        scope = maybe_scope.start.strftime("%G-ww%V.%u")
        return scope
    elif maybe_scope.type == TimeScope.Type.week:
        # Convert "week" scopes into their first day
        scope = maybe_scope.start.strftime("%G-ww%V.%u")
        return scope

    return scope_str


def _get_scopes(t: Task_v1):
    tts_query = TaskTimeScope.query \
        .filter_by(task_id=t.task_id) \
        .order_by(TaskTimeScope.time_scope_id)

    return [_force_day_scope(tts.time_scope_id) for tts in tts_query.all()]


def _migrate_simple(session, t1: Task_v1) -> Task_v2:
    """
    Migrate an orphan task

    Task_v1 only has a few fields that will turn into linkages:

    - for first_scope, we can add the `created_at` field,
      and possibly an `as_json()` dump
    - for the last scope, we set `resolution` + `time_elapsed`
    - every other linkage has no info, a `roll => wwXX.Y` resolution at most

    Note that first_scope isn't guaranteed to be the _earliest_ scope,
    it's intended to be the one where the task was created.
    """
    t2 = Task_v2(desc=t1.desc, category=t1.category, time_estimate=t1.time_estimate)
    session.add(t2)
    session.flush()
    print(f"DEBUG: {t2} <= _migrate_simple({t1})")

    created_at_linkage = None
    prior_linkage = None
    for scope_id in _get_scopes(t1):
        linkage = TaskLinkage(task_id=t2.task_id, time_scope_id=scope_id)
        linkage.created_at = datetime.now()
        session.add(linkage)

        # Touch up created_at_linkage
        if scope_id == _force_day_scope(t1.first_scope):
            created_at_linkage = linkage
            created_at_linkage.created_at = t1.created_at if t1.created_at else datetime.now()
            created_at_linkage.detailed_resolution = json.dumps(t1.as_json(), indent=4)

        # For "ordinary" linkages, append `roll => wwXX.Y` resolution
        if prior_linkage:
            min_scope_id = TimeScope(t1.first_scope).minimize(scope_id)
            prior_linkage.resolution = f"roll => {min_scope_id}"

        prior_linkage = linkage

    # For the final linkage, inherit any/all Task_v1 fields
    final_linkage = prior_linkage if prior_linkage else created_at_linkage
    final_linkage.resolution = t1.resolution
    final_linkage.time_elapsed = t1.time_actual

    return t2


def _tack_on_peer(session, baseline_t2: Task_v2, t1: Task_v1):
    """
    Tacks on the info from the new peer Task_v1 (identical description).

    Mini version of how to handle child Task_v1's.
    See _tack_on_child() for the reference implementation.
    """
    print(f"DEBUG: {baseline_t2} <= _tack_on_peer({t1})")
    if t1.category and t1.category != baseline_t2.category:
        print(f"WARN: new category will be lost: \"{t1.category}\"")
        print(f"      baseline category is     : \"{baseline_t2.category}\"")

    created_at_linkage = None
    prior_linkage = None
    for scope_id in _get_scopes(t1):
        linkage = TaskLinkage(task_id=baseline_t2.task_id, time_scope_id=scope_id)
        linkage.created_at = datetime.now()
        session.add(linkage)

        if scope_id == _force_day_scope(t1.first_scope):
            created_at_linkage = linkage

        if prior_linkage:
            prior_linkage.resolution = f"roll => {scope_id} (for peer {t1})"

        prior_linkage = linkage

    if t1.created_at:
        created_at_linkage.created_at = min(created_at_linkage.created_at, t1.created_at)

    final_linkage = prior_linkage if prior_linkage else created_at_linkage
    if final_linkage.resolution and final_linkage.resolution != t1.resolution:
        print(f"WARN: peer resolution will be lost: \"{t1.resolution[:40]}\"")
        print(f"      existing resolution is      : \"{final_linkage.resolution[:40]}\"" )
        print(f"      copied from legacy {t1}/{created_at_linkage.time_scope_id}")
    else:
        final_linkage.resolution = t1.resolution
    if final_linkage.time_elapsed is not None and t1.time_actual:
        final_linkage.time_elapsed += t1.time_actual
    else:
        final_linkage.time_elapsed = t1.time_actual

    return baseline_t2


def _tack_on_child(session, parent_t2: Task_v2, child_t1: Task_v1):
    """
    Merge a Task, its scopes, and its child Tasks

    Key thing is to treat linkages as the data object, and then dedupe them
    when it's closer to DB commit time. We're merging them via markdown
    formatting anyway, it's not like there's a ton of special data.

    A few interacting cases, documented in pytest:

    - parent task can have multiple scopes; this is the same as _migrate_simple
    - child tasks can have multiple scopes, which can overlap and interleave in time
      with the parent linkages, and even resolution.

    Thinking backwards, from what could go into a TaskLinkage:

    - set of TaskTimeScopes, potentially several
    - each of Task/Scope linkages, though:
        - Task_v1.first_scope, which means JSON data and created_at field
        - Task_v1's final "resolution" scope
        - other, arbitrary Task_v1 scopes

    This gets complicated if you merge together several of these from (sub-) tasks.
    Three-by-three means 9 cases, and potentially more if you think of the general case?
    (Probably not though. Maybe. I think it's just 6x6, where each of the three "new"
    cases have to do with repeating X potentially infinite times. Er. That's wrong.)

    Hopefully this is just... a way to stack new Task_v1 info onto an existing Task_v2.
    This would make it easy to support way more arbitrary stacks...

    Things that need to be migrated:

    | source field        | cadence | new purpose |
    | ---                 | ---     | ---
    | Task_v1.desc        | once    | top-level Task_v2
    | Task_v1.first_scope | once    |
    | Task_v1.category    | once    |
    | Task_v1.created_at
    | Task_v1.resolution
    | Task_v1.time_estimate
    | TaskTimeScope.time_scope_id
    """
    print(f"DEBUG: {parent_t2} <=  _tack_on_child({child_t1})")
    if child_t1.category != parent_t2.category:
        print(f"WARN: categories don't match (parent {parent_t2} is \"{parent_t2.category}\", child {child_t1} is \"{child_t1.category}\")")

    created_at_linkage = None
    prior_linkage = None
    for scope_id in _get_scopes(child_t1):
        linkage = parent_t2.linkage_at(scope_id)
        session.add(linkage)

        # Touch up created_at_linkage
        if scope_id == _force_day_scope(child_t1.first_scope):
            created_at_linkage = linkage

        # For "ordinary" linkages, append `roll => wwXX.Y (for child Task#ZZZ)`
        if prior_linkage and not prior_linkage.resolution:
            prior_linkage.resolution = f"roll => {scope_id} (for child {child_t1})"

        prior_linkage = linkage

    # Touch up created_at_linkage
    if child_t1.created_at:
        created_at_linkage.created_at = min(created_at_linkage.created_at, child_t1.created_at)
    if created_at_linkage.detailed_resolution:
        print(f"WARN: child desc will be lost : {repr(child_t1.desc[:40])}")
        print(f"      existing desc/resolution: {repr(created_at_linkage.detailed_resolution[:40])}" )
        print(f"      copied from legacy {child_t1}/{created_at_linkage.time_scope_id}")
    else:
        created_at_linkage.detailed_resolution = child_t1.desc

    # Touch up final linkage
    final_linkage = prior_linkage if prior_linkage else created_at_linkage
    if final_linkage.resolution and final_linkage.resolution != child_t1.resolution:
        print(f"WARN: child resolution will be lost: \"{child_t1.resolution[:40]}\"")
        print(f"      existing resolution is       : \"{final_linkage.resolution[:40]}\"" )
    else:
        final_linkage.resolution = f"{child_t1.resolution} (for child {child_t1})"
    if final_linkage.time_elapsed is not None and child_t1.time_actual:
        final_linkage.time_elapsed += child_t1.time_actual
    else:
        final_linkage.time_elapsed = child_t1.time_actual


def _migrate_tree(session, t1: Task_v1) -> Task_v2:
    """
    Migrate the fully general case of N depth Task trees
    """
    parent_t2 = _migrate_simple(session, t1)
    session.flush()

    children_to_tack_on: List[Task_v1] = t1.children
    while children_to_tack_on:
        current_child: Task_v1 = children_to_tack_on.pop()
        children_to_tack_on.extend(current_child.children)

        _tack_on_child(session, parent_t2, current_child)
        session.flush()

    return parent_t2


def _do_one(tasks_v2_session, t1: Task_v1) -> Task_v2:
    """
    Merge a Task, its scopes, and its child Tasks
    """
    def _task_depth(t: Task_v1) -> int:
        """
        Returns number of layers in task tree, where childless node = 0

        - task with children = depth 1
        - task with children with children = depth 2
        """
        t_depth = 0
        for child in t.children:
            t_depth = max(t_depth, _task_depth(child) + 1)

        return t_depth

    baseline_t2 = Task_v2.query \
        .filter_by(desc=t1.desc) \
        .one_or_none()
    if baseline_t2:
        _tack_on_peer(tasks_v2_session, baseline_t2, t1)
        return baseline_t2

    if not t1.parent and not t1.children:
        return _migrate_simple(tasks_v2_session, t1)

    if not t1.parent and t1.children:
        if _task_depth(t1) > 1:
            return _migrate_tree(tasks_v2_session, t1)
        else:
            parent_t2 = _migrate_simple(tasks_v2_session, t1)
            tasks_v2_session.flush()

            for child in t1.children:
                _tack_on_child(tasks_v2_session, parent_t2, child)
                tasks_v2_session.flush()

            return parent_t2


def do_one(tasks_v2_session, t1: Task_v1) -> Optional[Task_v2]:
    if t1.parent:
        return None

    try:
        t2 = _do_one(tasks_v2_session, t1)
    except ValueError as e:
        print(e)
        print(json.dumps(t1.as_json(), indent=2))
        raise

    try:
        tasks_v2_session.commit()
    except StatementError as e:
        tasks_v2_session.rollback()
        print(f"ERROR: Hit exception while parsing {t1}, skipping")
        print()
        print(e)
        print()
        print(json.dumps(t1.as_json(), indent=2))
        raise
    except IntegrityError as e:
        session.rollback()
        print(f"ERROR: Hit exception while parsing {t1}, skipping")
        print()
        print(e)
        print()
        print(json.dumps(t1.as_json(), indent=2))
        raise

    return t2


def do_multiple(tasks_v1_session,
                tasks_v2_session,
                force_delete_current: bool = False):
    if force_delete_current:
        tasks_v2_session.query(TaskLinkage).delete()
        tasks_v2_session.query(Task_v2).delete()
        tasks_v2_session.commit()

    v1_tasks = Task_v1.query \
        .order_by(Task_v1.task_id) \
        .all()
    for t1 in v1_tasks:
        do_one(tasks_v2_session, t1)

    print("Done migrating tasks")
