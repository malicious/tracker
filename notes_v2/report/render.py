import functools
import hashlib
import itertools
from datetime import datetime, timedelta
from typing import Iterable, Tuple

from flask import Response, current_app
from markupsafe import escape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notes_v2.models import Note, NoteDomain
from notes_v2.report.gather import notes_json_tree
from notes_v2.time_scope import TimeScope

default_dot_render_offset = 0


@functools.lru_cache
def _domain_hue(d: str) -> str:
    domain_hash = hashlib.sha256(d.encode('utf-8')).hexdigest()
    domain_hash_int = int(domain_hash[0:4], 16)

    color_h = (domain_hash_int % 12) * (256.0 / 12)
    return f"{color_h:.2f}"


@functools.lru_cache
def domain_to_css_color(d: str) -> str:
    """
    Map the domain string to a visually-distinct CSS color.

    Current implementation hashes the domain string, then takes the first 4
    characters as a base-16 number, which is then mapped to one of 8 final HSL
    colors.

    TODO: We could probably do with more than equally-spaced "hue" values
    """
    return f"color: hsl({_domain_hue(d)}, 80%, 40%);"


@functools.lru_cache
def _dot_radius_and_styling(
    db_session: Session,
    domain_ids: Tuple[str],
    note: Note,
) -> Tuple[str, str]:
    if not note.detailed_desc and not note.get_domain_ids():
        return 8, f'style="fill: rgba(0, 0, 0, 0.2);"'

    # Use the rarest domain, and figure out how big to make the dot
    domain_id0, note_count = db_session.execute(
        select(NoteDomain.domain_id, func.count(NoteDomain.note_id))
        .where(NoteDomain.domain_id.in_(list(note.get_domain_ids())))
        .group_by(NoteDomain.domain_id)
        .order_by(func.count(NoteDomain.note_id).asc())
        .limit(1)
    ).one()

    # Do an initial estimate of dot size based on note length
    if note.detailed_desc is not None and len(note.detailed_desc) > 1_000:
        dot_radius = min(40, len(note.detailed_desc) / 200)
        dot_opacity = min(0.6, max(0.2, 1.0 - len(note.detailed_desc) / 8_000))

    # Otherwise, estimate the rarity of the domain
    else:
        # Check if we've cached a note count somewhere
        if not hasattr(current_app, 'total_note_count'):
            current_app.total_note_count = db_session.execute(
                select(func.count(Note.note_id))
            ).scalar()

        dot_radius_weight = 0.1 * current_app.total_note_count / note_count
        dot_radius = min(14, dot_radius_weight + 2)
        dot_opacity = 0.3

    # Make in-focus domains a little more consistent
    if domain_id0 in domain_ids:
        dot_radius = min(40, dot_radius + 6)

    return dot_radius, f'style="fill: hsl({_domain_hue(domain_id0)}, 80%, 40%); fill-opacity: {dot_opacity:.2f}"'


def tooltip_cache(key, generate_fn):
    if not hasattr(current_app, 'tooltip_cache_dict'):
        current_app.tooltip_cache_dict = {}

    if key not in current_app.tooltip_cache_dict:
        current_app.tooltip_cache_dict[key] = generate_fn()

    return current_app.tooltip_cache_dict[key]


def _domain_ids_tooltip(
        db_session: Session | None,
        note: Note,
        do_sort_domain_ids: bool = True,
):
    """
    Returns a formatted list of domain_ids, suitable for an `svg * > title`
    """
    def sort_domain_ids(domain_ids: Tuple[str]):
        sorted_domain_rows = db_session.execute(
            select(NoteDomain.domain_id)
            .where(NoteDomain.domain_id.in_(domain_ids))
            .group_by(NoteDomain.domain_id)
            .order_by(func.count(NoteDomain.note_id).asc())
        ).all()

        for (domain_id,) in sorted_domain_rows:
            yield domain_id

    domain_ids = tuple(sorted(note.get_domain_ids()))
    if not do_sort_domain_ids:
        return escape('\n'.join(domain_ids)) or "[no domains]"

    def generate_fn():
        sorted_domains = sort_domain_ids(domain_ids)
        return escape('\n'.join(sorted_domains)) or "[no domains]"

    return tooltip_cache(domain_ids, generate_fn)


def render_day_svg(
    db_session: Session,
    domains: Tuple[str],
    day_scope_id: str,
    day_notes,
    svg_width: int = 960,
    initial_indent_str: str = ' ' * 4,
    additional_indent_str: str = '  ',
) -> str:
    """
    Valid timezones range from -12 to +14 or so (historical data gets worse),
    so set an expected range of +/-12 hours, rather than building in proper
    timezone support.

    Heights and their gutters:

    - height is 96 because it's close to 100, and a multiple of 6 (hours are split into six segments)
    - hour lines are between 0.40 and 0.60 of this
    """
    start_time = datetime.strptime(day_scope_id, '%G-ww%V.%u') + timedelta(hours=-12)
    width_factor = svg_width / (48 * 60 * 60)
    height_factor = 96

    def draw_hour_lines() -> Iterable[str]:
        # draw the hour lines on top
        for hour in range(1, 48):
            yield (
                '<line '
                f'x1="{svg_width * hour / 48:.3f}" y1="{0.4 * height_factor:.3f}" '
                f'x2="{svg_width * hour / 48:.3f}" y2="{0.6 * height_factor:.3f}" '
                f'stroke="black" opacity="0.1" />'
            )

    # the overall day boundaries + text label(s)
    def draw_other_elements() -> Iterable[str]:
        yield (
            '<line '
            f'x1="{svg_width * 1 / 4}" y1="{0.15 * height_factor:.3f}" '
            f'x2="{svg_width * 1 / 4}" y2="{0.85 * height_factor:.3f}" stroke="black" />'
        )
        yield (
            f'<text x="{svg_width / 2}" y="{0.85 * height_factor:.3f}" '
            'text-anchor="middle" opacity="0.5" style="font-size: 12px">'
            f'{(start_time + timedelta(hours=12)).strftime("%G-ww%V.%u-%b-%d")}</text>'
        )
        yield (
            '<line '
            f'x1="{svg_width * 3 / 4}" y1="{0.15 * height_factor:.3f}" '
            f'x2="{svg_width * 3 / 4}" y2="{0.85 * height_factor:.3f}" stroke="black" />'
        )
        yield (
            '<text x="{svg_width}" y="{0.85 * height_factor:.3f}" '
            'text-anchor="end" opacity="0.5" style="font-size: 12px">'
            f'{(start_time + timedelta(hours=36)).strftime("ww%V.%u")}</text>'
        )

    # and the actual note circles
    def draw_note_dots(render_if_missing_time: bool = True) -> Iterable[str]:
        for note in day_notes:
            if hasattr(note, 'sort_time') and note.sort_time:
                seconds_offset = (note.sort_time - start_time).total_seconds()
            elif render_if_missing_time:
                seconds_offset = default_dot_render_offset
            else:
                continue

            dot_radius, dot_styling = _dot_radius_and_styling(db_session, domains, note)
            hour_offset = seconds_offset % 3600

            yield '''<circle cx="{:.3f}" cy="{:.3f}" r="{}" {}><title>{}</title></circle>'''.format(
                (seconds_offset - hour_offset + 1800) * width_factor,
                hour_offset / 3600 * height_factor,
                dot_radius,
                dot_styling,
                _domain_ids_tooltip(db_session, note),
            )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'id="{day_scope_id}" '
        f'width="{svg_width}" '
        f'height="{height_factor}">'
        + ('\n' + initial_indent_str + additional_indent_str).join(
            itertools.chain(
                [''],
                draw_hour_lines(),
                draw_other_elements(),
                draw_note_dots(),
            ))
        + '\n' + initial_indent_str + '</svg>'
    )


def standalone_render_day_svg(db_session, domains, day_scope, disable_caching):
    week_scope = day_scope.get_parent()
    quarter_scope = week_scope.get_parent()

    quarter_notes = notes_json_tree(db_session, domains, [day_scope])[quarter_scope]
    week_notes = quarter_notes[week_scope]
    day_notes = week_notes[day_scope]

    svg_text = render_day_svg(db_session, domains, day_scope, day_notes['notes'])
    response = Response(svg_text, mimetype='image/svg+xml')
    if not disable_caching:
        response.cache_control.max_age = 31536000
    return response


def render_week_svg(
        db_session: Session,
        domains: Tuple[str],
        week_scope_id: str,
        notes_dict,
        initial_indent_str: str = ' ' * 4,
        additional_indent_str: str = '  ',
) -> str:
    """
    Render data vertically, like a weekly calendar.
    """
    hours_before = 12
    hours_after = 12
    col_width = 108
    col_width_and_right_margin = col_width + 4
    row_height = 20

    def _draw_hour_line(column, row) -> str:
        """
        This "weekly" svg is usually split into 9 columns and 24 rows.

        For ease, this is expected to be 90px x 20px.
        """
        # Draw the every-6-hours lines special
        if row % 6 == 0:
            return '<line x1="{:.3f}" y1="{}" x2="{:.3f}" y2="{}" stroke="black" opacity="0.4" />'.format(
                column * col_width_and_right_margin + col_width / 2 - 15,
                row * row_height,
                column * col_width_and_right_margin + col_width / 2 + 15,
                row * row_height
            )
        else:
            return '<line x1="{:.3f}" y1="{}" x2="{:.3f}" y2="{}" stroke="black" opacity="0.1" />'.format(
                column * col_width_and_right_margin + col_width / 2 - 10,
                row * row_height,
                column * col_width_and_right_margin + col_width / 2 + 10,
                row * row_height
            )

    def draw_hour_lines() -> Iterable[str]:
        # render the pre-monday, if needed
        for row in range(24 - hours_before, 24):
            yield _draw_hour_line(column=0, row=row)

        # and now the "normal" days
        for column in range(1, 8):
            for row in range(1, 24):
                yield _draw_hour_line(column, row)

        # and the after-sunday
        for row in range(1, hours_after + 1):
            yield _draw_hour_line(column=8, row=row)

        # and text for the "normal" days
        for column in range(1, 8):
            day_label = (
                '<text '
                f'x="{column * col_width_and_right_margin + col_width / 2}" y="{24 * row_height - 8}" '
                'text-anchor="middle" opacity="0.5" style="font-size: 10px">'
                f'{week_scope_id[5:] + "." + str(column)}'
                '</text>'
            )
            yield day_label

    # and the actual individual notes
    def _draw_note_dot(note, render_if_missing_time: bool = True) -> str | None:
        """
        TODO: This is hard-coded to expect that the SVG chart starts on previous Sunday.
        """
        if hasattr(note, 'sort_time') and note.sort_time:
            day_scope_time = datetime(note.sort_time.year, note.sort_time.month, note.sort_time.day)
            seconds_offset = (note.sort_time - day_scope_time).total_seconds()

            # Push some notes to the start/end of the week, based on the time scope
            render_column = note.sort_time.isoweekday()
            if render_column == 1 and note.time_scope_id[-1] == "7":
                render_column = 8
            if render_column == 7 and note.time_scope_id[-1] == "1":
                render_column = 0

        elif render_if_missing_time:
            if TimeScope(note.time_scope_id).is_day():
                # just dump the dot in the top row
                seconds_offset = default_dot_render_offset
                note_time_scope = datetime.strptime(note.time_scope_id, "%G-ww%V.%u")
                render_column = note_time_scope.isoweekday()

            elif TimeScope(note.time_scope_id).is_week():
                seconds_offset = 0
                render_column = 0

            else:
                return None

        else:
            return None

        # calculate the sub-hour offset for the dot, scaled to include some margins on the hour-block
        dot_radius, dot_styling = _dot_radius_and_styling(db_session, domains, note)
        dot_x_offset = (seconds_offset % (60 * 60)) / (60 * 60)
        dot_x_offset = dot_radius + dot_x_offset * (col_width - 2 * dot_radius)

        return '<circle cx="{:.3f}" cy="{:.3f}" r="{}" {} {}><title>{}</title></circle>'.format(
            render_column * col_width_and_right_margin + dot_x_offset,
            int(seconds_offset / (60 * 60)) * row_height + row_height / 2,
            dot_radius,
            dot_styling,
            f'tracker-note-id="{note.note_id}"',
            _domain_ids_tooltip(db_session, note),
        )

    def draw_note_dots() -> Iterable[str]:
        for day_scope, day_dict in notes_dict.items():
            if day_scope == "notes":
                for note in day_dict:
                    yield _draw_note_dot(note)
            else:
                for note in day_dict['notes']:
                    yield _draw_note_dot(note)

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{9 * col_width_and_right_margin}" '
        f'height="{24 * row_height}">'
        # Dump all background boxes into one group, because otherwise
        # there are so many that it slows down browser tools.
        + ('\n' + initial_indent_str + additional_indent_str)
        + '<g group-id="hour-lines">{}</g>'.format(
            ('\n' + initial_indent_str + additional_indent_str).join(draw_hour_lines())
        )
        + ('\n' + initial_indent_str + additional_indent_str)
        + '<g group-id="note-dots">{}</g>'.format(
            ('\n' + initial_indent_str + additional_indent_str).join(
                (dot for dot in draw_note_dots() if dot is not None),
            ))
        + '\n' + initial_indent_str + '</svg>'
    )


def standalone_render_week_svg(db_session, domains, week_scope, disable_caching):
    quarter_scope = week_scope.get_parent()

    quarter_notes = notes_json_tree(db_session, domains, [week_scope])[quarter_scope]
    week_notes = quarter_notes[week_scope]

    svg_text = render_week_svg(db_session, domains, week_scope, week_notes)
    response = Response(svg_text, mimetype='image/svg+xml')
    if not disable_caching:
        response.cache_control.max_age = 31536000
    return response
