import hashlib
from datetime import datetime, timedelta

from notes_v2.time_scope import TimeScope


def domain_to_css_color(domain: str) -> str:
    domain_hash = hashlib.sha256(domain.encode('utf-8')).hexdigest()
    domain_hash_int = int(domain_hash[0:4], 16)

    color_h = ((domain_hash_int + 4) % 8) * (256.0 / 8)
    return f"color: hsl({color_h}, 70%, 50%);"


def _stroke_color(d):
    domain_hash = hashlib.sha256(d.encode('utf-8')).hexdigest()
    domain_hash_int = int(domain_hash[0:4], 16)

    color_h = ((domain_hash_int + 4) % 8) * (256.0 / 8)
    return f"stroke: hsl({color_h}, 70%, 50%);"


def render_day_svg(day_scope, day_notes, svg_width=800) -> str:
    """
    Valid timezones range from -12 to +14 or so (historical data gets worse),
    so set an expected range of +/-12 hours, rather than building in proper
    timezone support.
    """
    start_time = datetime.strptime(day_scope, '%G-ww%V.%u') + timedelta(hours=-12)
    width_factor = svg_width / (48 * 60 * 60)

    rendered_notes = []

    # draw the hour lines + notes on top
    for hour in range(1, 48):
        svg = '<line ' \
            f'x1="{svg_width*hour/48:.3f}" y1="40" ' \
            f'x2="{svg_width*hour/48:.3f}" y2="60" ' \
            f'stroke="black" opacity="0.1" />'
        rendered_notes.append(svg)

    for note in day_notes:
        if not note.sort_time:
            continue

        dot_color = "stroke: black"
        if note.domain_ids:
            dot_color = _stroke_color(note.domain_ids[0])

        hour_offset = (note.sort_time - start_time).total_seconds() % 3600
        svg_element = '''<circle cx="{:.3f}" cy="{:.3f}" r="{}" style="fill: none; {}" />'''.format(
            ((note.sort_time - start_time).total_seconds() - hour_offset + 1800) * width_factor,
            hour_offset / 3600 * 100,
            5,
            dot_color,
        )
        rendered_notes.append(svg_element)

    # finally, the overall text labels
    rendered_notes.extend([
        f'<line x1="{svg_width*1/4}" y1="15" x2="{svg_width*1/4}" y2="85" stroke="black" />',
        f'<text x="{svg_width/2}" y="{85}" text-anchor="middle" opacity="0.5" style="font-size: 12px">{day_scope}</text>',
        f'<line x1="{svg_width*3/4}" y1="15" x2="{svg_width*3/4}" y2="85" stroke="black" />',
        f'<text x="{svg_width}" y="{85}" text-anchor="end" opacity="0.5" style="font-size: 12px">{(start_time + timedelta(hours=36)).strftime("ww%V.%u")}</text>',
    ])

    return '''<svg width="{}" height="100">{}</svg>'''.format(
        svg_width,
        '\n'.join(rendered_notes)
    )


def render_week_svg(week_scope, notes_dict) -> str:
    """
    Render data vertically, like a weekly calendar.
    """
    hours_before = 12
    hours_after = 12
    col_width = 100
    col_width_and_right_margin = 104
    row_height = 20

    rendered_notes = []

    def draw_hour(column, row):
        """
        This "weekly" svg is usually split into 9 columns and 24 rows.

        For ease, this is expected to be 90px x 20px.
        """
        hour_line = '<line x1="{:.3f}" y1="{}" ' \
            'x2="{:.3f}" y2="{}" ' \
            'stroke="black" opacity="0.1" />'.format(
                column * col_width_and_right_margin + col_width/2 - 10,
                row * row_height,
                column * col_width_and_right_margin + col_width/2 + 10,
                row * row_height)

        # Draw the every-6-hours lines special
        if row % 6 == 0:
            hour_line = '<line x1="{:.3f}" y1="{}" x2="{:.3f}" y2="{}" stroke="black" opacity="0.4" />'.format(
                column * col_width_and_right_margin + col_width/2 - 15,
                row * row_height,
                column * col_width_and_right_margin + col_width/2 + 15,
                row * row_height)

        rendered_notes.append(hour_line)

    # render the pre-monday, if needed
    for row in range(24-hours_before,24):
        draw_hour(column=0, row=row)

    # and now the "normal" days
    for column in range(1,8):
        for row in range(1,24):
            draw_hour(column, row)

        day_label = f'<text x="{column * col_width_and_right_margin + col_width/2}" y="{24 * row_height - 8}" ' \
            f'text-anchor="middle" opacity="0.5" style="font-size: 10px">{week_scope[5:] + "." + str(column)}</text>'
        rendered_notes.append(day_label)

    # and the after-sunday
    for row in range(1,hours_after+1):
        draw_hour(column=8, row=row)

    # and the actual tasks
    def render_note_dot(note):
        """
        TODO: This is hard-coded to expect that the SVG chart starts on previous Sunday.
        """
        if not note.sort_time:
            return
        if not TimeScope(note.time_scope_id).is_day():
            return

        column = note.sort_time.isoweekday()
        if column == 1 and note.time_scope_id[-1] == "7":
            column = 8
        if column == 7 and note.time_scope_id[-1] == "1":
            column = 0
        day_scope_time = datetime(note.sort_time.year, note.sort_time.month, note.sort_time.day)

        dot_color = "stroke: black"
        if note.domain_ids:
            dot_color = _stroke_color(note.domain_ids[0])

        # calculate the sub-hour offset for the dot, scaled to include some margins on the hour-block
        dot_radius = 5
        dot_x_offset = ((note.sort_time - day_scope_time).total_seconds() % (60*60)) / (60*60)
        dot_x_offset = dot_radius + dot_x_offset * (col_width - 2 * dot_radius)

        svg_element = '<circle cx="{:.3f}" cy="{:.3f}" r="{}" {} />'.format(
            column * col_width_and_right_margin + dot_x_offset,
            int((note.sort_time - day_scope_time).total_seconds() / (60*60)) * row_height + row_height / 2,
            dot_radius,
            f'style="fill: none; {dot_color}" tracker-note-id="{note.note_id}"')
        rendered_notes.append(svg_element)

    for day_scope, day_dict in notes_dict.items():
        if day_scope == "notes":
            for note in day_dict:
                render_note_dot(note)
        else:
            for note in day_dict['notes']:
                render_note_dot(note)

    return '''<svg width="{}" height="{}">\n  {}\n</svg>'''.format(
        9 * col_width_and_right_margin,
        24 * row_height,
        '\n  '.join(rendered_notes))
