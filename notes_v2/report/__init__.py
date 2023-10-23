import functools
import json
from collections import namedtuple
from datetime import datetime, timedelta
from typing import Tuple

from flask import current_app, render_template, url_for
from markupsafe import Markup, escape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notes_v2.models import Note, NoteDomain
from notes_v2.report.gather import notes_json_tree
from notes_v2.report.render import domain_to_css_color, render_day_svg, render_week_svg
from notes_v2.time_scope import TimeScope
# noinspection PyUnresolvedReferences
from . import gather, render
from .render import standalone_render_day_svg, standalone_render_week_svg


@functools.lru_cache(maxsize=100_000)
def _domain_to_html_link(
    domain_id: str,
    scope_ids: Tuple[str],
    single_page: bool,
) -> str:
    escaped_domain = domain_id.replace('+', '%2B')
    escaped_domain = escape(escaped_domain)
    escaped_domain = escaped_domain.replace(' ', '+')
    escaped_domain = escaped_domain.replace('&', '%26')

    return f'''<a href="/notes?domain={escaped_domain}{
        ''.join([f'&scope={scope_id}' for scope_id in scope_ids])
    }{
        "&single_page=true" if single_page else ""
    }" style="{domain_to_css_color(domain_id)}">{domain_id}</a>'''


def _render_n2_domains(
        n: Note,
        domain_ids: Tuple[str],
        scope_ids: Tuple[str],
        single_page: bool,
        ignore_noisy_domains: bool = False,
):
    def should_display_domain(d: str) -> bool:
        # Don't render any domains that are an exact match for the page
        #
        # Note that for multi-domain pages, this _intentionally_ prints
        # all domains, even if the note matches exactly. This is
        # because domains are OR'd together, and it's not intuitive to
        # have none of the domains printed.
        #
        if domain_ids == (d,):
            return False

        if ignore_noisy_domains:
            if d[:6] == "type: ":
                return False

        return True

    return " & ".join(
        _domain_to_html_link(d, scope_ids, single_page)
        for d in n.get_domain_ids()
        if should_display_domain(d))


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
            }&nbsp;{
                n.sort_time.strftime('%H:%M')
            }'''
    # Anything in a week scope is usually "reduced"; append %H:%M also
    elif scope.is_week() and n.sort_time:
        display_time = "{}&nbsp;{}".format(
            TimeScope.from_datetime(n.sort_time).minimize_vs(scope),
            n.sort_time.strftime('%H:%M'))

    return display_time


def cache(key, generate_fn):
    if not hasattr(current_app, 'cache_dict'):
        current_app.cache_dict = {}

    if key not in current_app.cache_dict:
        current_app.cache_dict[key] = generate_fn()

    return current_app.cache_dict[key]


def render_matching_notes(
        db_session: Session,
        domains: Tuple[str],
        scope_ids: Tuple[str],
        single_page: bool,
):
    render_kwargs = {}

    title_words = [f'domain={d}' for d in domains]
    title_words.extend([f'scope={ts}' for ts in scope_ids])
    # TODO: Timing app truncates the last character or two
    render_kwargs['page_title'] = escape('/notes?' + '&'.join(title_words))

    def as_week_header(week_scope: TimeScope) -> str:
        scope_url = url_for(
            ".do_render_matching_notes",
            scope=week_scope,
            domain=domains,
            single_page=single_page,
        )

        range: List[str] = week_scope.get_child_scopes()
        def as_words(day_scope_index):
            return datetime.strptime(range[day_scope_index], '%G-ww%V.%u').strftime('%b %d')

        return (
            f'週: <a href="{scope_url}" id="{week_scope}">'
            f'{week_scope} | {as_words(0)} - {as_words(-1)}'
            '</a>'
        )

    render_kwargs['as_week_header'] = as_week_header

    def as_quarter_header(quarter_scope: TimeScope) -> str:
        scope_url = url_for(
            ".do_render_matching_notes",
            scope=quarter_scope,
            domain=domains,
            single_page=single_page,
        )
        return (
            f'<a href="{scope_url}" id="{quarter_scope}">'
            f'quarter: {quarter_scope}'
            '</a>'
        )

    render_kwargs['as_quarter_header'] = as_quarter_header

    def do_markdown_filter(text):
        filter = current_app.jinja_env.filters.get('markdown')
        return filter(text)

    def render_n2_desc(n: Note, scope_id):
        return (
            # Some kind of sort_time
            f'<div class="time" title="{n.sort_time}">{_render_n2_time(n, TimeScope(scope_id))}</div>\n'
            # Print the description
            f'<div class="desc">{do_markdown_filter(n.desc)}</div>\n'
            # And color-coded, hyperlinked domains
            f'<div class="domains">{_render_n2_domains(n, domains, scope_ids, single_page)}</div>\n'
        )

    def render_n2_json(n: Note) -> str:
        return cache(
            key=("note json", n.note_id),
            generate_fn=lambda: json.dumps(n.as_json(include_domains=True), indent=2))

    def memoized_render_notes(jinja_render_fn):
        def generate_fn():
            notes_tree = notes_json_tree(db_session, domains, scope_ids)
            return jinja_render_fn(notes_tree)

        # Do not cache the current day.
        uncacheable_day_scope = TimeScope(datetime.now().strftime('%G-ww%V.%u'))

        if (
            uncacheable_day_scope in scope_ids
            or uncacheable_day_scope.get_parent() in scope_ids
            or uncacheable_day_scope.get_parent().get_parent() in scope_ids
        ):
            return generate_fn()

        # For a normal page, just cache the normal render.
        if not single_page:
            return cache(
                key=("/notes", tuple(domains), tuple(scope_ids),),
                generate_fn=generate_fn)

        # For a `single_page`'d request, try to write two cache entries.
        sp_result = cache(
            key=("/notes single_page", tuple(domains), tuple(scope_ids),),
            generate_fn=generate_fn)

        cache(
            key=("/notes", tuple(domains), tuple(scope_ids),),
            generate_fn=lambda: sp_result)

        return sp_result

    def memoized_render_day_svg(day_scope, day_dict_notes):
        disable_caching: bool = False
        if datetime.now().strftime('%G-ww%V.%u') == day_scope:
            disable_caching = True

        render_inline: bool = single_page
        if not render_inline:
            src = url_for(
                ".do_render_svg_day",
                day_scope=day_scope,
                domain=domains,
                disable_caching=disable_caching,
            )
            return f'<img src="{src}" />'

        if disable_caching:
            return render_day_svg(db_session, day_scope, day_dict_notes)
        else:
            return cache(
                key=("/svg.day cache entry", day_scope, tuple(domains),),
                generate_fn=lambda: render_day_svg(db_session, day_scope, day_dict_notes))

    render_kwargs['render_day_svg'] = memoized_render_day_svg

    def memoized_maybe_render_week_svg(week_scope, week_dict):
        disable_caching: bool = False
        if datetime.now().strftime('%G-ww%V') == week_scope:
            disable_caching = True
        # Sometimes, we render a week <svg> for a single day.
        # This makes the rendering weird and incomplete, so don't cache it.
        if week_scope not in scope_ids:
            disable_caching = True

        render_inline: bool = single_page
        if not render_inline:
            src = url_for(
                ".do_render_svg_week",
                week_scope=week_scope,
                domain=domains,
                disable_caching=disable_caching,
            )
            return f'<img src="{src}" />'

        if disable_caching:
            return render_week_svg(db_session, week_scope, week_dict)
        else:
            return cache(
                key=("/svg.week cache entry", week_scope, tuple(domains),),
                generate_fn=lambda: render_week_svg(db_session, week_scope, week_dict))

    render_kwargs['maybe_render_week_svg'] = memoized_maybe_render_week_svg

    # If this is limited to one scope, link to prev/next scopes as well.
    if len(scope_ids) == 1:
        def _scope_to_html_link(scope_id: str) -> str:
            return '<a href="/notes?scope={}{}{}">{}</a>'.format(
                scope_id,
                ''.join([f'&domain={d}' for d in domains]),
                "&single_page=true" if single_page else "",
                scope_id)

        scope_id0 = TimeScope(list(scope_ids)[0])

        if scope_id0.is_day():
            next_dt = datetime.strptime(scope_id0, '%G-ww%V.%u') + timedelta(days=1)
            render_kwargs['next_scope'] = _scope_to_html_link(TimeScope.from_datetime(next_dt))
            prev_dt = datetime.strptime(scope_id0, '%G-ww%V.%u') + timedelta(days=-1)
            render_kwargs['prev_scope'] = _scope_to_html_link(TimeScope.from_datetime(prev_dt))

        elif scope_id0.is_week():
            next_dt = datetime.strptime(scope_id0 + '.1', '%G-ww%V.%u') + timedelta(days=7)
            render_kwargs['next_scope'] = _scope_to_html_link(next_dt.strftime('%G-ww%V'))
            prev_dt = datetime.strptime(scope_id0 + '.1', '%G-ww%V.%u') + timedelta(days=-7)
            render_kwargs['prev_scope'] = _scope_to_html_link(prev_dt.strftime('%G-ww%V'))

        elif scope_id0.is_quarter():
            year = int(scope_id0[:4])
            quarter = int(scope_id0[-1])
            next_quarter = f"{year}—Q{quarter + 1}"
            prev_quarter = f"{year}—Q{quarter - 1}"
            if quarter == 1:
                prev_quarter = f"{year - 1}—Q4"
            if quarter == 4:
                next_quarter = f"{year + 1}—Q1"

            render_kwargs['next_scope'] = _scope_to_html_link(next_quarter)
            render_kwargs['prev_scope'] = _scope_to_html_link(prev_quarter)

    domains_as_html = [_domain_to_html_link(d, scope_ids, single_page) for d in domains]
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
            "latest": Note.query
                .join(NoteDomain, NoteDomain.note_id == Note.note_id)
                .filter(NoteDomain.domain_id == nd.domain_id)
                .order_by(Note.time_scope_id.desc())
                .limit(1)
                .one().time_scope_id,
            "count": NoteDomain.query
                .filter_by(domain_id=nd.domain_id)
                .count()
        }

    return response_json


def render_note_domains(
        session,
        query_limiter,
):
    """
    Build and return human-readable page that lists domains + their info
    """
    # @dataclass
    class DomainInfo:
        domain_id: str
        domain_id_link: str

        earliest: TimeScope
        latest: TimeScope

        count: int
        count_str: str

    def render_domains():
        query = query_limiter(
            select(
                NoteDomain.domain_id,
                func.min(Note.time_scope_id),
                func.max(Note.time_scope_id),
                func.max(Note.sort_time),
                func.count(Note.note_id),
            )
            .join(NoteDomain, NoteDomain.note_id == Note.note_id)
            .group_by(NoteDomain.domain_id)
            .order_by(func.max(Note.sort_time).desc())
        )

        rows = session.execute(query).all()
        for row in rows:
            info = DomainInfo()

            info.domain_id = row[0]
            info.domain_id_link = Markup(_domain_to_html_link(info.domain_id, (), None))

            info.earliest = TimeScope(row[1])
            info.latest = TimeScope(row[2])

            info.latest = info.latest.minimize_vs(info.earliest)

            info.count = row[4]
            info.count_str = f"{info.count:_}"

            yield info

    return render_template(
        'note-domains.html',
        domains_generator=render_domains(),
    )

