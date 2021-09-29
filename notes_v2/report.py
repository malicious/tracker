import hashlib
import json
from datetime import datetime, timedelta
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
        self.week_promotion_threshold = 14
        self.quarter_promotion_threshold = 8

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
        #
        # Note that for multi-domain pages, this _intentionally_ prints
        # all domains, even if the note matches exactly. This is
        # because domains are OR'd together, and it's not intuitive to
        # have none of the domains printed.
        #
        if len(page_domains) == 1 and d == page_domains[0]:
            return False

        # Ignore domains that start with `type: `, maybe
        if ignore_type_domains and d[:6] == "type: ":
            return False

        return True

    domains_as_html = [domain_to_html_link(d) for d in n.domain_ids if should_display_domain(d)]
    return " & ".join(domains_as_html)


def _render_n2_time(n: Note, scope: TimeScope) -> str:
    display_time = TimeScope(n.time_scope_id).minimize_vs(scope)

    # If we're showing a sub-day scope, draw the time, instead
    if scope.is_day() and n.sort_time:
        # For same-day notes, just show %H:%M
        if scope == TimeScope.from_datetime(n.sort_time):
            display_time = n.sort_time.strftime('%H:%M')
        # For different day, show the day _also_
        else:
            display_time = f'''{
                TimeScope.from_datetime(n.sort_time).minimize_vs(scope)
            } {
                n.sort_time.strftime('%H:%M')
            }'''
    # Anything in a week scope is usually "reduced"; append %H:%M also
    elif scope.is_week() and n.sort_time:
        display_time = "{} {}".format(
            TimeScope.from_datetime(n.sort_time).minimize_vs(scope),
            n.sort_time.strftime('%H:%M'))

    return display_time


cache_dict = {}


def clear_html_cache():
    """
    TODO: cache_dict is not actually shared where we want it to be

    Flask's development server (werkzeug) can reload the app without
    actually starting a new process, which leaves the n2/report cache
    with stale data. Remember to explicitly clear it on init.

    - TODO: Make this somehow-shared, so CLI state changes server state
    - TODO: This probably also does weird things for unit testing
    """
    cache_dict.clear()


def edit_notes(domains: List[str], scope_ids: List[str]):
    def as_week_header(scope):
        return "週: " + datetime.strptime(scope + '.1', '%G-ww%V.%u').strftime('%G-ww%V-%b-%d')

    def render_day_svg(day_scope, notes, svg_width=800) -> str:
        """
        Valid timezones range from -12 to +14 or so (historical data gets worse),
        so set an expected range of +/-12 hours, rather than building in proper
        timezone support.
        """
        start_time = datetime.strptime(day_scope, '%G-ww%V.%u') + timedelta(hours=-12)
        width_factor = svg_width / (48*60*60)

        def stroke_color(d):
            domain_hash = hashlib.sha256(d.encode('utf-8')).hexdigest()
            domain_hash_int = int(domain_hash[0:4], 16)

            color_h = ((domain_hash_int + 4) % 8) * (256.0/8)
            return f"stroke: hsl({color_h}, 70%, 50%);"

        # Pre-populate the list of notes, so we can be assured this is working
        rendered_notes = [
            '',
            f'<line x1="{svg_width*1/4}" y1="15" x2="{svg_width*1/4}" y2="85" stroke="black" />',
            f'<text x="{svg_width/2}" y="{85}" text-anchor="middle" opacity="0.5" style="font-size: 12px">{day_scope}</text>',
            f'<line x1="{svg_width*3/4}" y1="15" x2="{svg_width*3/4}" y2="85" stroke="black" />',
            f'<text x="{svg_width}" y="{85}" text-anchor="end" opacity="0.5" style="font-size: 12px">{(start_time + timedelta(hours=36)).strftime("%G-ww%V.%u")}</text>',
            '',
        ]

        for hour in range(1, 48):
            svg = f'<line x1="{svg_width*hour/48:.3f}" y1="40" x2="{svg_width*hour/48:.3f}" y2="60" stroke="black" opacity="0.1" />'
            rendered_notes.append(svg)

        def x_pos(t):
            return (t - start_time).total_seconds() * width_factor

        def y_pos(t):
            """Scales the "seconds" of sort_time to the y-axis, from 20-80

            Add 30 seconds so the :00 time lines up with the middle of the chart
            """
            start_spot = 20
            seconds_only = ((note.sort_time - start_time).total_seconds() + 30) % 60

            return start_spot + seconds_only

        for note in notes:
            if not note.sort_time:
                continue

            dot_color = "stroke: black"
            if note.domain_ids:
                dot_color = stroke_color(note.domain_ids[0])

            svg_element = '''<circle cx="{:.3f}" cy="{:.3f}" r="{}" style="fill: none; {}" />'''.format(
                x_pos(note.sort_time),
                y_pos(note.sort_time),
                5,
                dot_color,
            )
            rendered_notes.append(svg_element)

        svg = '''<svg width="800" height="100">{}</svg>'''.format(
            '\n'.join(rendered_notes)
        )
        return svg

    def render_n2_desc(n: Note, scope_id):
        output_str = ""

        # Generate a <span> that holds some kind of sort_time
        output_str += f'<span class="time">{_render_n2_time(n, TimeScope(scope_id))}</span>\n'

        # Print the description
        output_str += f'<span class="desc">{n.desc}</span>\n'

        # And color-coded, hyperlinked domains
        output_str += f'<span class="domains">{_render_n2_domains(n, domains, scope_ids)}</span>\n'

        return output_str

    def render_n2_json(n: Note) -> str:
        return json.dumps(n.as_json(include_domains=True), indent=2)

    def memoized_render_notes(jinja_render_fn):
        cache_key = (tuple(domains), tuple(scope_ids),)
        if cache_key not in cache_dict:
            # set max cache size, to be polite
            if len(cache_dict) > 1000:
                clear_html_cache()

            notes_tree = notes_json_tree(domains, scope_ids)
            cache_dict[cache_key] = jinja_render_fn(notes_tree)
        else:
            print(f"DEBUG: Found cached output for {cache_key}")

        return cache_dict[cache_key]


    return render_template('notes-v2.html',
                           as_week_header=as_week_header,
                           cached_render=memoized_render_notes,
                           domain_header=' & '.join(domains),
                           render_n2_desc=render_n2_desc,
                           render_n2_json=render_n2_json,
                           render_day_svg=render_day_svg)


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
