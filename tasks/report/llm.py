import json
import re
from datetime import datetime, timedelta
from textwrap import indent

from flask import make_response
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from tasks.database_models import TaskLinkage, Task
from util import TimeScope


def _construct_textual_timedelta(
        tasklinkage_dt: datetime,
        reference_dt: datetime,
) -> str | None:
    years_delta = reference_dt.year - tasklinkage_dt.year

    if years_delta >= 2:
        return f"{years_delta} years ago"
    elif years_delta <= -2:
        return f"in {-years_delta} years"

    # if years isn't granular enough, dump it into a months number
    months_delta = reference_dt.month - tasklinkage_dt.month
    months_delta += years_delta * 12

    if months_delta >= 3:
        return f"{months_delta} months ago"
    elif months_delta <= -3:
        return f"in {-months_delta} months"

    # remainders are weeks and days
    days_delta = reference_dt - tasklinkage_dt

    if days_delta.days >= 12:
        return f"{days_delta.days/7:.0f} weeks ago"
    elif days_delta.days <= -12:
        return f"in {-days_delta.days/7:.0f} weeks"

    elif days_delta.days > 1:
        return f"{days_delta.days} days ago"
    elif days_delta.days < -1:
        return f"in {-days_delta.days} days"

    elif days_delta.days == 1:
        return f"yesterday"
    elif days_delta.days == -1:
        return f"tomorrow"

    # otherwise it's due today; don't print anything because LLM's interpret
    # "today" to mean "this is very important"
    return None


def _category_for_llm(
        task: Task,
        formatter,
):
        # Assume the description already has categories embedded
        if task.desc_for_llm:
            return ""

        categories = set()
        for d in task.split_categories():
            if d:
                categories.add(d)

        if len(categories) > 1:
            return formatter(f"categories {', '.join(categories)}")
        elif len(categories) == 1:
            return formatter(categories.pop())

        return ""


def tasks_as_prompt(
        db_session: Session,
        hide_future: bool = False,
        hide_past: bool = False,
        include_detailed_resolutions: bool = False,
        output_as_json: bool = False,
):
    render_time_dt = datetime.utcnow()
    future_tasks_cutoff = render_time_dt + timedelta(days=91)
    past_tasks_cutoff = render_time_dt - timedelta(days=366)

    additional_filters = [
        TaskLinkage.resolution == None,
    ]
    if hide_past:
        additional_filters.append(TaskLinkage.time_scope > past_tasks_cutoff)
    if hide_future:
        additional_filters.append(TaskLinkage.time_scope < future_tasks_cutoff)

    tasks_by_usefulest_linkage = (
        select(Task.task_id, Task.import_source, func.min(TaskLinkage.time_scope).label('earliest_unresolved_linkage'))
        .where(and_(*additional_filters,
                    TaskLinkage.task_id == Task.task_id,
                    TaskLinkage.import_source == Task.import_source))
        .group_by(Task.task_id, Task.import_source)
        .subquery()
    )

    query = (
        select(Task,
               tasks_by_usefulest_linkage.c.earliest_unresolved_linkage)
        .join(tasks_by_usefulest_linkage,
              and_(Task.task_id == tasks_by_usefulest_linkage.c.task_id,
                   Task.import_source == tasks_by_usefulest_linkage.c.import_source))
        .order_by(func.random())
        .group_by(Task.task_id, Task.import_source)
    )
    task_rows = db_session.execute(query).all()

    final_markdown_descs = []

    task: Task
    usefulest_time_scope: TimeScope
    for (task, usefulest_time_scope) in task_rows:
        output_desc = task.desc
        # Use the override if it exists
        if task.desc_for_llm is not None:
            output_desc = task.desc_for_llm

            # Sometimes the override is an empty string,
            # which indicates we should skip it for LLM output.
            if not task.desc_for_llm.strip():
                continue

        # Filter out link info for any markdown links
        output_desc = re.sub(r'\[(.*?)\]\(.*\)', r'\1', output_desc)
        maybe_category = _category_for_llm(task, ", in {}".format)

        usefulest_ts_dt = datetime(
            year=usefulest_time_scope.year,
            month=usefulest_time_scope.month,
            day=usefulest_time_scope.day,
        )
        fancy_timedelta = _construct_textual_timedelta(usefulest_ts_dt, render_time_dt)
        maybe_overdue = f", due {fancy_timedelta}" if fancy_timedelta else ""

        s = f"- {output_desc}{maybe_category}{maybe_overdue}"
        if "\n" in output_desc:
            maybe_category = _category_for_llm(task, "in {}, ".format)
            maybe_overdue = f"due {fancy_timedelta}, " if fancy_timedelta else ""
            # indent the desc text, but need that initial markdown unordered list mark
            indented_output_desc = indent(output_desc, '  ')
            s = f"- {maybe_category}{maybe_overdue}{indented_output_desc[2:]}"

        final_markdown_descs.append(s)

        # And add detail from all sub-linkages, if any:
        if include_detailed_resolutions:
            for tl in task.linkages:
                if tl.detailed_resolution:
                    # Apparently web input gives newlines as `\r\n`, hopefully that's not browser-specific
                    short_res = re.sub(r'<!-- .* -->\r\n', '', tl.detailed_resolution)
                    short_res_lines = short_res.split('\r\n')

                    if short_res_lines and short_res_lines[0]:
                        final_markdown_descs.append("  - " + short_res_lines[0])
                        for line in short_res_lines[1:]:
                            if line.strip():
                                final_markdown_descs.append("    " + line)

    result_text = "\n".join(final_markdown_descs)
    if output_as_json:
        # Format the output specially so it can get parsed directly into llama.cpp
        response = make_response(json.dumps(result_text), 200)
        response.mimetype = "application/json"
        return response

    response = make_response(result_text, 200)
    response.mimetype = "text/plain"
    return response
