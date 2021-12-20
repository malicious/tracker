import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List

from flask import render_template
from markupsafe import escape
from sqlalchemy import or_

from notes_v2.models import Note, NoteDomain
from notes_v2.report.gather import notes_json_tree
from notes_v2.report.render import domain_to_css_color, render_day_svg, render_week_svg
from notes_v2.time_scope import TimeScope
# noinspection PyUnresolvedReferences
from . import gather, render


def _render_n2_domains(n: Note, page_domains: List[str], scope_ids: List[str], ignore_type_domains: bool = True):
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
                           render_day_svg=render_day_svg,
                           render_week_svg=render_week_svg)


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


def domains(session):
    """
    Build and return human-readable page that lists domains + their info
    """
    domain_rows = []

    for nd in session.query(NoteDomain.domain_id).distinct():
        domain_row = "<div>{}</div>".format(
            nd.domain_id
        )
        domain_rows.append(domain_row)

    return "\n".join(domain_rows)

