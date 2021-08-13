import hashlib
import json
from typing import Dict, List

from flask import render_template
from markupsafe import escape
from sqlalchemy import or_

from notes_v2.models import Note, NoteDomain
from notes_v2.time_scope import TimeScope


NOTES_KEY = "notes"

class NoteStapler:
    """
    Bundles up Note.as_json() results into a Jinja-renderable dict

    The only really hard part of this is the auto-promotion: if there
    aren't enough "day" tasks, they get bundled together into a "week"
    or "quarter" scope for ease of scanning.
    """

    def __init__(self, domains_filter: List[str]):
        self.filtered_query = Note.query
        if domains_filter:
            domains_filter_sql = [NoteDomain.domain_id.like(d + "%") for d in domains_filter]
            # TODO: Combining domain and scope filtering doesn't work
            self.filtered_query = self.filtered_query \
                .join(NoteDomain, Note.note_id == NoteDomain.note_id) \
                .filter(or_(*domains_filter_sql))

        self.scope_tree = {}
        self.week_promotion_threshold = 10
        self.quarter_promotion_threshold = 10

    def _construct_scope_tree(self, scope: TimeScope) -> Dict:
        # TODO: Could probably collapse these cases into something cute and recursive
        if scope.is_quarter():
            if scope not in self.scope_tree:
                self.scope_tree[scope] = {
                    NOTES_KEY: [],
                }

            return self.scope_tree[scope]

        elif scope.is_week():
            quarter_tree = self._construct_scope_tree(scope.parent)
            if scope not in quarter_tree:
                quarter_tree[scope] = {
                    NOTES_KEY: [],
                }

            return quarter_tree[scope]

        elif scope.is_day():
            week_tree = self._construct_scope_tree(scope.parent)
            if scope not in week_tree:
                week_tree[scope] = {
                    NOTES_KEY: [],
                }

            return week_tree[scope]

        raise ValueError(f"TimeScope has unknown type: {repr(scope)}")

    def _collapse_scope_tree(self, scope: TimeScope) -> None:
        scope_tree = self._construct_scope_tree(scope)

        children = scope_tree.keys()
        for child in list(scope_tree.keys()):
            if child == NOTES_KEY:
                continue

            # NB this call depends on scope_tree being sorted correctly
            # (construct will do a lookup, rather than passing the child dict directly).
            # Not unreasonable, but this is the only time this is explicitly depended-on.
            self._collapse_scope_tree(child)

            scope_tree[NOTES_KEY].extend(
                scope_tree[child][NOTES_KEY]
            )
            del scope_tree[child]

    def _add_by_day(self, scope: TimeScope) -> int:
        new_notes = list(self.filtered_query \
                         .filter(Note.time_scope_id == scope) \
                         .order_by(Note.time_scope_id.desc()) \
                         .all())

        notes_list = self._construct_scope_tree(scope)[NOTES_KEY]
        notes_list.extend(new_notes)
        return len(new_notes)

    def _add_by_week(self, scope: TimeScope) -> int:
        total_notes_count = 0
        for day_scope in scope.child_scopes:
            added_notes = self._add_by_day(TimeScope(day_scope))
            total_notes_count += added_notes

        new_notes = list(self.filtered_query \
                         .filter(Note.time_scope_id == scope) \
                         .order_by(Note.time_scope_id.asc()) \
                         .all())

        notes_list = self._construct_scope_tree(scope)[NOTES_KEY]
        notes_list.extend(new_notes)
        total_notes_count += len(new_notes)

        # Now, for the auto-promotion if child scopes aren't numerous enough
        if total_notes_count <= self.week_promotion_threshold:
            self._collapse_scope_tree(scope)

        return total_notes_count

    def _add_by_quarter(self, scope: TimeScope) -> int:
        total_notes_count = 0
        for week_scope in scope.child_scopes:
            added_notes = self._add_by_week(TimeScope(week_scope))
            total_notes_count += added_notes

        new_notes = list(self.filtered_query \
                         .filter(Note.time_scope_id == scope) \
                         .order_by(Note.time_scope_id.asc()) \
                         .all())

        notes_list = self._construct_scope_tree(scope)[NOTES_KEY]
        notes_list.extend(new_notes)
        total_notes_count += len(new_notes)

        if total_notes_count <= self.quarter_promotion_threshold:
            self._collapse_scope_tree(scope)

        return total_notes_count

    def add_by_scope(self, scope: TimeScope) -> None:
        if scope.is_quarter():
            self._add_by_quarter(scope)
        elif scope.is_week():
            self._add_by_week(scope)
        elif scope.is_day():
            self._add_by_day(scope)
        else:
            raise ValueError(f"TimeScope has unknown type: {repr(scope)}")

    def add_everything(self) -> None:
        # TODO: Remove scopes with empty NOTES_KEY
        notes = self.filtered_query.all()
        for n in notes:
            note_list = self._construct_scope_tree(TimeScope(n.time_scope_id))[NOTES_KEY]
            note_list.append(n)

        # Once we're done, iteratively check if we need to do collapsing
        for quarter in list(self.scope_tree.keys()):
            quarter_count = 0

            for week in list(self.scope_tree[quarter].keys()):
                week_count = 0

                # If this isn't a real week, but the quarter's notes:
                if week == NOTES_KEY:
                    quarter_count += len(self.scope_tree[quarter][week])
                    continue

                for day in list(self.scope_tree[quarter][week].keys()):
                    # If this isn't a real day, but the week's notes:
                    if day == NOTES_KEY:
                        week_count += len(self.scope_tree[quarter][week][day])
                        continue

                    week_count += len(self.scope_tree[quarter][week][day][NOTES_KEY])

                if week_count <= self.week_promotion_threshold:
                    self._collapse_scope_tree(week)

                quarter_count += week_count

            if quarter_count <= self.quarter_promotion_threshold:
                self._collapse_scope_tree(quarter)


def _render_n2_domains(n: Note, page_domains: List[str], scope_ids: List[str], ignore_type_domains: bool = True):
    def domain_to_css_color(domain: str) -> str:
        domain_hash = hashlib.sha256(domain.encode('utf-8')).hexdigest()
        domain_hash_int = int(domain_hash[0:4], 16)

        color_h = ((domain_hash_int + 4) % 8) * (256.0/8)
        return f"color: hsl({color_h}, 70%, 50%);"

    def domain_to_html_link(domain: str) -> str:
        return f'''<a href="/notes?domain={escape(domain)}{
            ''.join([f'&scope={scope_id}' for scope_id in scope_ids])
        }" style="{domain_to_css_color(domain)}">{domain}</a>'''

    def should_display_domain(d: str) -> bool:
        # Don't render any domains that are an exact match for the page
        if d in page_domains:
            return False

        # Ignore domains that start with `type: `, maybe
        if ignore_type_domains and d[:6] == "type: ":
            return False

        return True

    domains_as_html = [domain_to_html_link(d) for d in n.domain_ids if should_display_domain(d)]
    return " & ".join(domains_as_html)


def _render_n2_time(n: Note, scope):
    display_time = TimeScope(n.time_scope_id).minimize_vs(scope)
    # If we're showing a sub-day scope, draw the time, instead
    if TimeScope(scope).is_day() and n.sort_time:
        # For same-day notes, just show %H:%m
        if scope == TimeScope.from_datetime(n.sort_time):
            display_time = n.sort_time.strftime('%H:%M')
        # For different day, show the day _also_
        else:
            display_time = f'''{
                TimeScope.from_datetime(n.sort_time).minimize_vs(scope)
            } {
                n.sort_time.strftime('%H:%M')
            }'''

    return display_time


def edit_notes(domains: List[str], scope_ids: List[str]):
    def render_n2_desc(n: Note, scope):
        output_str = ""

        # Generate a <span> that holds some kind of sort_time
        output_str += f'<span class="time">{_render_n2_time(n, scope)}</span>\n'

        # Print the description
        output_str += f'<span class="desc">{n.desc}</span>\n'

        # And color-coded, hyperlinked domains
        output_str += f'<span class="domains">{_render_n2_domains(n, domains, scope_ids)}</span>\n'

        # detailed_desc, only if needed
        if n.detailed_desc:
            output_str += f'<div class="detailed-desc">{escape(n.detailed_desc)}</div>'

        return output_str

    def render_n2_json(n: Note) -> str:
        return escape(json.dumps(n.as_json(include_domains=True), indent=2))

    return render_template('notes-v2.html',
                           render_n2_desc=render_n2_desc,
                           render_n2_json=render_n2_json,
                           notes_tree=notes_json_tree(domains, scope_ids))


def edit_notes_simple(*args):
    """
    Render a list of Notes as simply as possible

    Still tries to exercise the same codepaths as a normal endpoint, though.
    """
    def render_n2_desc(n: Note):
        return n.desc

    def render_n2_json(n: Note) -> str:
        return escape(json.dumps(n.as_json(include_domains=True), indent=2))

    return render_template('notes-simple.html',
                           note_desc_as_html=render_n2_desc,
                           pretty_print_note=render_n2_json,
                           notes_list=args)


def notes_json_tree(domains: List[str], scope_ids: List[str]):
    ns = NoteStapler(domains_filter=domains)

    for scope_id in scope_ids:
        ns.add_by_scope(TimeScope(scope_id))

    if not scope_ids:
        ns.add_everything()

    return ns.scope_tree


def domain_stats(session):
    """
    Build and return statistics for every matching NoteDomain

    - how many notes are tied to that domain
    - (maybe) how many notes are _uniquely_ that domain
    - latest time_scope_id for that note (alphabetical sorting is fine)

    Response JSON format:

    ```
    {
      "account: credit card": {
        "latest_time_scope_id": "2021-ww32.2",
        "note_count": 26
      },
      "type: summary": {
        "latest_time_scope_id": "2009-ww09.1",
        "note_count": 3746
      }
    }
    ```
    """
    response_json = {}

    for nd in session.query(NoteDomain.domain_id).distinct():
        response_json[nd.domain_id] = {
            "latest": Note.query \
                .join(NoteDomain, NoteDomain.note_id == Note.note_id) \
                .filter(NoteDomain.domain_id == nd.domain_id) \
                .order_by(Note.time_scope_id.desc()) \
                .limit(1) \
                .one().time_scope_id,
            "count": NoteDomain.query \
                .filter_by(domain_id=nd.domain_id) \
                .count()
        }

    return response_json
