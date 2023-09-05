import json
from collections import namedtuple
from datetime import datetime, timedelta
from typing import List

from flask import render_template
from markupsafe import escape

from notes_v2.models import Note, NoteDomain
from notes_v2.report.gather import notes_json_tree
from notes_v2.report.render import domain_to_css_color, render_day_svg, render_week_svg
from notes_v2.time_scope import TimeScope
# noinspection PyUnresolvedReferences
from . import gather, render


def _domain_to_html_link(domain: str, scope_ids: List[str] = []) -> str:
    escaped_domain = domain.replace('+', '%2B')
    escaped_domain = escape(escaped_domain)
    escaped_domain = escaped_domain.replace(' ', '+')
    escaped_domain = escaped_domain.replace('&', '%26')

    return f'''<a href="/notes?domain={escaped_domain}{
        ''.join([f'&scope={scope_id}' for scope_id in scope_ids])
    }" style="{domain_to_css_color(domain)}">{domain}</a>'''


def _render_n2_domains(n: Note, page_domains: List[str], scope_ids: List[str], ignore_noisy_domains: bool = False):
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

        if ignore_noisy_domains:
            if d[:6] == "type: ":
                return False

        return True

    domains_as_html = [_domain_to_html_link(d, scope_ids) for d in n.domain_ids if should_display_domain(d)]
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


def cache(key, generate_fn):
    """
    TODO: cache_dict is not actually shared where we want it to be

    Flask's development server (werkzeug) can reload the app without
    actually starting a new process, which leaves the n2/report cache
    with stale data. Remember to explicitly clear it on init.

    - TODO: Make this somehow-shared, so CLI state changes server state
    - TODO: This probably also does weird things for unit testing
    """
    if key not in cache_dict:
        # set max cache size, to be polite
        if len(cache_dict) > 1000:
            cache_dict.clear()

        cache_dict[key] = generate_fn()
    else:
        print(f"DEBUG: Found cached output for {key}")

    return cache_dict[key]


def edit_notes(domains: List[str], scope_ids: List[str]):
    render_kwargs = {}

    title_words = [f'domain={d}' for d in domains]
    title_words.extend([f'scope={ts}' for ts in scope_ids])
    # TODO: Timing app truncates the last character or two
    render_kwargs['page_title'] = escape('/notes?' + '&'.join(title_words))

    def as_week_header(week_scope):
        week_scope_desc = datetime.strptime(week_scope + '.1', '%G-ww%V.%u').strftime('%G-ww%V-%b-%d')
        return '週: <a href="/notes?scope={}{}" id="{}">{}</a>'.format(
            week_scope,
            ''.join([f'&domain={d}' for d in domains]),
            week_scope,
            week_scope_desc)

    render_kwargs['as_week_header'] = as_week_header

    def as_quarter_header(quarter_scope):
        return 'quarter: <a href="/notes?scope={}{}" id="{}">{}</a>'.format(
            quarter_scope,
            ''.join([f'&domain={d}' for d in domains]),
            quarter_scope,
            quarter_scope)

    render_kwargs['as_quarter_header'] = as_quarter_header

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
        def generate_fn():
            notes_tree = notes_json_tree(domains, scope_ids)
            return jinja_render_fn(notes_tree)

        # Do not cache the current day.
        if datetime.utcnow().strftime('%G-ww%V.%u') in scope_ids:
            return generate_fn()
        # Do not cache the current week.
        if datetime.utcnow().strftime('%G-ww%V') in scope_ids:
            return generate_fn()
        # TODO: Do not cache the current quarter.
        return cache(
            key=(tuple(domains), tuple(scope_ids),),
            generate_fn=generate_fn)

    def memoized_render_day_svg(day_scope, day_dict):
        return cache(
            ("day_svg-cache-entry", day_scope, tuple(domains),),
            lambda: render_day_svg(day_scope, day_dict))

    render_kwargs['render_day_svg'] = memoized_render_day_svg

    def memoized_render_week_svg(week_scope, week_dict):
        return cache(
            ("week_svg-cache-entry", week_scope, tuple(domains),),
            lambda: render_week_svg(week_scope, week_dict))

    render_kwargs['render_week_svg'] = memoized_render_week_svg

    # If this is limited to one scope, link to prev/next scopes as well.
    if len(scope_ids) == 1:
        def _scope_to_html_link(scope_id: str) -> str:
            return '<a href="/notes?scope={}{}">{}</a>'.format(
                scope_id,
                ''.join([f'&domain={d}' for d in domains]),
                scope_id)

        if TimeScope(scope_ids[0]).is_day():
            next_dt = datetime.strptime(scope_ids[0], '%G-ww%V.%u') + timedelta(days=1)
            render_kwargs['next_scope'] = _scope_to_html_link(TimeScope.from_datetime(next_dt))
            prev_dt = datetime.strptime(scope_ids[0], '%G-ww%V.%u') + timedelta(days=-1)
            render_kwargs['prev_scope'] = _scope_to_html_link(TimeScope.from_datetime(prev_dt))

        elif TimeScope(scope_ids[0]).is_week():
            next_dt = datetime.strptime(scope_ids[0] + '.1', '%G-ww%V.%u') + timedelta(days=7)
            render_kwargs['next_scope'] = _scope_to_html_link(next_dt.strftime('%G-ww%V'))
            prev_dt = datetime.strptime(scope_ids[0] + '.1', '%G-ww%V.%u') + timedelta(days=-7)
            render_kwargs['prev_scope'] = _scope_to_html_link(prev_dt.strftime('%G-ww%V'))

        elif TimeScope(scope_ids[0]).is_quarter():
            year = int(scope_ids[0][:4])
            quarter = int(scope_ids[0][-1])
            next_quarter = f"{year}—Q{quarter + 1}"
            prev_quarter = f"{year}—Q{quarter - 1}"
            if quarter == 1:
                prev_quarter = f"{year - 1}—Q4"
            if quarter == 4:
                next_quarter = f"{year + 1}—Q1"

            render_kwargs['next_scope'] = _scope_to_html_link(next_quarter)
            render_kwargs['prev_scope'] = _scope_to_html_link(prev_quarter)

    domains_as_html = [_domain_to_html_link(d, scope_ids) for d in domains]
    render_kwargs['domain_header'] = " & ".join(domains)
    render_kwargs['domain_header_html'] = " & ".join(domains_as_html)

    return render_template('notes-v2.html',
                           cached_render=memoized_render_notes,
                           render_n2_desc=render_n2_desc,
                           render_n2_json=render_n2_json,
                           **render_kwargs)


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
    DomainInfo = namedtuple("DomainInfo", "domain_id time_scope_id count")
    domain_infos = []

    # Get the latest note for each domain_id we have
    for nd in session.query(NoteDomain.domain_id).distinct():
        latest_note = Note.query \
            .join(NoteDomain, NoteDomain.note_id == Note.note_id) \
            .filter(NoteDomain.domain_id == nd.domain_id) \
            .order_by(Note.time_scope_id.desc()) \
            .limit(1) \
            .one()

        count = NoteDomain.query \
            .filter_by(domain_id=nd.domain_id) \
            .count()

        domain_infos.append(DomainInfo(
            domain_id=nd.domain_id,
            time_scope_id=latest_note.time_scope_id,
            count=count))

    domain_infos.sort(key=lambda x: x.time_scope_id, reverse=True)
    domain_rows = []

    for di in domain_infos:
        domain_row = "<div>{}{}{}</div>".format(
            f"<span style=\"padding-right: 24px;\">{di.time_scope_id}</span>",
            f"<span style=\"padding-right: 24px;\">{di.count}</span>",
            _domain_to_html_link(di.domain_id)
        )
        domain_rows.append(domain_row)

    return "\n".join(domain_rows)
