import json
from datetime import datetime, timedelta
from typing import Tuple, List

from flask import current_app, render_template, url_for
from markupsafe import Markup, escape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notes_v2.models import Note, NoteDomain
from notes_v2.report.gather import notes_json_tree
from notes_v2.report.render import domain_to_css_color, render_day_svg, render_week_svg
from util import TimeScope, TimeScopeBuilder
# noinspection PyUnresolvedReferences
from . import counts, domains, gather, render
from .render import standalone_render_day_svg, standalone_render_week_svg
from .render_utils import _domain_to_html_link


def _render_n2_domains(
        db_session: Session,
        n: Note,
        domain_ids: Tuple[str],
        scope_ids: Tuple[str],
        single_page: bool,
        ignore_noisy_domains: bool = False,
) -> str:
    def should_display_domain(d: str) -> bool:
        """
        Don't render any domains that are an exact match for the page

        Note that for multi-domain pages, this _intentionally_ prints
        all domains, even if the note matches exactly. This is
        because domains are OR'd together, and it's not intuitive to
        have none of the domains printed.
        """
        if domain_ids == (d,):
            return False

        if ignore_noisy_domains:
            if d[:6] == "type: ":
                return False

        return True

    renderable_domains = [d for d in n.get_domain_ids() if should_display_domain(d)]
    if len(renderable_domains) == 0:
        return ""
    elif len(renderable_domains) == 1:
        # Don't need to do any querying if there's only one domain,
        # which is true for the majority of notes
        return _domain_to_html_link(renderable_domains[0], scope_ids, single_page)
    else:
        # TODO: Profile and decide whether memoizing this will help.
        # And also, whether we can do it with functools, or need flask.current_app.
        query = (
            select(NoteDomain.domain_id, func.count(NoteDomain.note_id))
            .where(NoteDomain.domain_id.in_(renderable_domains))
            .group_by(NoteDomain.domain_id)
            .order_by(func.count(NoteDomain.note_id).asc())
        )

        rendered_domains = []
        for domain_id, note_count in db_session.execute(query).all():
            rendered_domains.append(_domain_to_html_link(domain_id, scope_ids, single_page))

        return " & ".join(rendered_domains)


def _render_n2_time(
        n: Note,
        scope_ids: Tuple[str],
        reference_scope: TimeScope,
) -> str:
    # For complex scope sets, we need to keep the year + do no minimization.
    scope_id_years = set([ts[0:4] for ts in scope_ids])
    if n.time_scope_id[0:4] not in scope_id_years:
        if n.sort_time:
            return TimeScopeBuilder.day_scope_from_dt(n.sort_time)
        else:
            return n.time_scope_id

    # For notes without a sort_time, just dump the date
    if not n.sort_time:
        return TimeScope(n.time_scope_id).as_short_str(reference_scope)

    # For same-day notes, just show %H:%M
    if reference_scope.is_day():
        if reference_scope == TimeScopeBuilder.day_scope_from_dt(n.sort_time):
            return n.sort_time.strftime('%H:%M')

    return "{} {}".format(
        TimeScopeBuilder.day_scope_from_dt(n.sort_time).as_short_str(reference_scope),
        n.sort_time.strftime('%H:%M'),
    )


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
    url_kwargs = {
        'domain': domains,
        'scope': scope_ids,
    }
    if single_page:
        url_kwargs['single_page'] = single_page

    title_words = [f'domain={d}' for d in domains]
    title_words.extend([f'scope={ts}' for ts in scope_ids])
    # NB Timing app truncates the last character/s, so append a few for no reason.
    render_kwargs['page_title'] = escape('/notes?' + '&'.join(title_words) + '  ')

    def as_week_header(week_scope: TimeScope) -> str:
        scope_kwargs = dict(url_kwargs)
        scope_kwargs['scope'] = week_scope
        scope_url = url_for(".do_render_matching_notes", **scope_kwargs)

        range: List[str] = list(week_scope.children)
        def as_words(day_scope_index):
            return datetime.strptime(range[day_scope_index], '%G-ww%V.%u').strftime('%b %d')

        return (
            f'週: <a href="{scope_url}" id="{week_scope}">'
            f'{week_scope} | {as_words(0)} - {as_words(-1)}'
            '</a>'
        )

    render_kwargs['as_week_header'] = as_week_header

    def as_quarter_header(quarter_scope: TimeScope) -> str:
        scope_kwargs = dict(url_kwargs)
        scope_kwargs['scope'] = quarter_scope
        scope_url = url_for(".do_render_matching_notes", **scope_kwargs)
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
            f'<div class="time" title="{n.sort_time}">{_render_n2_time(n, scope_ids, TimeScope(scope_id))}</div>\n'
            # Print the description
            f'<div class="desc">{do_markdown_filter(n.desc)}</div>\n'
            # And color-coded, hyperlinked domains
            f'<div class="domains">{_render_n2_domains(db_session, n, domains, scope_ids, single_page)}</div>\n'
        )

    def render_n2_json(n: Note) -> str:
        note_json = n.as_json(include_domains=True)
        # Add extra debugging info
        if note_json.get('detailed_desc'):
            note_json['detailed_desc_length'] = len(note_json['detailed_desc'])

        return cache(
            key=("note json", n.note_id),
            generate_fn=lambda: json.dumps(note_json, indent=2))

    def memoized_render_notes(jinja_render_fn):
        def generate_fn():
            notes_tree = notes_json_tree(db_session, domains, scope_ids)
            return jinja_render_fn(notes_tree)

        # Do not cache the current day.
        uncacheable_day_scope = TimeScope(datetime.now().strftime('%G-ww%V.%u'))

        if (
            uncacheable_day_scope in scope_ids
            or uncacheable_day_scope.parent_week in scope_ids
            or uncacheable_day_scope.parent_quarter in scope_ids
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
            src_kwargs = {
                'day_scope': day_scope,
                'domain': domains,
            }
            if disable_caching:
                src_kwargs['disable_caching'] = "true"

            src = url_for(
                ".do_render_svg_day",
                **src_kwargs,
            )
            return f'<img class="day-svg-external" src="{src}" width="960px" height="96px" />'

        if disable_caching:
            return render_day_svg(db_session, domains, day_scope, day_dict_notes)
        else:
            return cache(
                key=("/svg.day cache entry", day_scope, domains),
                generate_fn=lambda: render_day_svg(db_session, domains, day_scope, day_dict_notes))

    render_kwargs['render_day_svg'] = memoized_render_day_svg

    def memoized_maybe_render_week_svg(week_scope, week_dict):
        disable_caching: bool = False
        if datetime.now().strftime('%G-ww%V') == week_scope:
            disable_caching = True
        # Sometimes, we render a week <svg> for a single day.
        # This makes the rendering weird and incomplete, so don't cache it.
        if len(scope_ids) == 1 and TimeScope(scope_ids[0]).is_day:
            disable_caching = True

        render_inline: bool = single_page
        if not render_inline:
            if disable_caching:
                src = url_for(
                    ".do_render_svg_week",
                    week_scope=week_scope,
                    domain=domains,
                    disable_caching="true",
                )
                return f'<img class="week-svg-external" src="{src}" />'
            else:
                link_kwargs = dict(url_kwargs)
                link_kwargs['single_page'] = 'true'

                image_src = url_for(
                    ".do_render_svg_week",
                    week_scope=week_scope,
                    domain=domains,
                )
                link_href = url_for(".do_render_matching_notes", **link_kwargs)
                return (
                    f'<a href="{link_href}">'
                    f'<img class="week-svg-external" src="{image_src}" width="1008px" height="480px" />'
                    f'</a>'
                )

        if disable_caching:
            return render_week_svg(db_session, domains, week_scope, week_dict)
        else:
            return cache(
                key=("/svg.week cache entry", week_scope, domains),
                generate_fn=lambda: render_week_svg(db_session, domains, week_scope, week_dict))

    render_kwargs['maybe_render_week_svg'] = memoized_maybe_render_week_svg

    # If this is limited to one scope, link to prev/next scopes as well.
    if len(scope_ids) == 1:
        def _scope_to_html_link(scope_id: str) -> str:
            scope_kwargs = dict(url_kwargs)
            scope_kwargs['scope'] = scope_id
            return '<a href="{}">{}</a>'.format(
                url_for(".do_render_matching_notes", **scope_kwargs),
                scope_id)

        scope_id0 = TimeScope(list(scope_ids)[0])

        if scope_id0.is_day:
            next_dt = datetime.strptime(scope_id0, '%G-ww%V.%u') + timedelta(days=1)
            render_kwargs['next_scope'] = _scope_to_html_link(TimeScopeBuilder.day_scope_from_dt(next_dt))
            prev_dt = datetime.strptime(scope_id0, '%G-ww%V.%u') + timedelta(days=-1)
            render_kwargs['prev_scope'] = _scope_to_html_link(TimeScopeBuilder.day_scope_from_dt(prev_dt))

        elif scope_id0.is_week:
            next_dt = datetime.strptime(scope_id0 + '.1', '%G-ww%V.%u') + timedelta(days=7)
            render_kwargs['next_scope'] = _scope_to_html_link(next_dt.strftime('%G-ww%V'))
            prev_dt = datetime.strptime(scope_id0 + '.1', '%G-ww%V.%u') + timedelta(days=-7)
            render_kwargs['prev_scope'] = _scope_to_html_link(prev_dt.strftime('%G-ww%V'))

        elif scope_id0.is_quarter:
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

    if domains:
        # TODO: Sort domains by length-of-domain_id, for prettier rendering.
        #       Should also check whether rarity sort is useful.
        domains_as_html = [_domain_to_html_link(d, scope_ids, single_page) for d in domains]
        domains_as_html = '\n & '.join(f'<span>{d}</span>' for d in domains_as_html)

        render_kwargs['scope_nav_header'] = Markup(
            f'<div>\n{domains_as_html}\n</div>\n' +
            '<div class="close"><a href="{}">[x]</a></div>'.format(
                url_for(".do_render_matching_notes", scope=scope_ids, single_page=single_page),
            )
        )

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
