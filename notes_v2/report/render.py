import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List

from flask import render_template
from markupsafe import escape
from sqlalchemy import or_

from notes_v2.models import Note, NoteDomain
from notes_v2.time_scope import TimeScope


def domain_to_css_color(domain: str) -> str:
    domain_hash = hashlib.sha256(domain.encode('utf-8')).hexdigest()
    domain_hash_int = int(domain_hash[0:4], 16)

    color_h = ((domain_hash_int + 4) % 8) * (256.0/8)
    return f"color: hsl({color_h}, 70%, 50%);"


def _stroke_color(d):
    domain_hash = hashlib.sha256(d.encode('utf-8')).hexdigest()
    domain_hash_int = int(domain_hash[0:4], 16)

    color_h = ((domain_hash_int + 4) % 8) * (256.0/8)
    return f"stroke: hsl({color_h}, 70%, 50%);"


def render_day_svg(day_scope, day_notes, svg_width=800) -> str:
    """
    Valid timezones range from -12 to +14 or so (historical data gets worse),
    so set an expected range of +/-12 hours, rather than building in proper
    timezone support.
    """
    start_time = datetime.strptime(day_scope, '%G-ww%V.%u') + timedelta(hours=-12)
    width_factor = svg_width / (48*60*60)

    # Pre-populate the list of notes, so we can be assured this is working
    rendered_notes = [
        f'<line x1="{svg_width*1/4}" y1="15" x2="{svg_width*1/4}" y2="85" stroke="black" />',
        f'<text x="{svg_width/2}" y="{85}" text-anchor="middle" opacity="0.5" style="font-size: 12px">{day_scope}</text>',
        f'<line x1="{svg_width*3/4}" y1="15" x2="{svg_width*3/4}" y2="85" stroke="black" />',
        f'<text x="{svg_width}" y="{85}" text-anchor="end" opacity="0.5" style="font-size: 12px">{(start_time + timedelta(hours=36)).strftime("%G-ww%V.%u")}</text>',
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

    for note in day_notes:
        if not note.sort_time:
            continue

        dot_color = "stroke: black"
        if note.domain_ids:
            dot_color = _stroke_color(note.domain_ids[0])

        svg_element = '''<circle cx="{:.3f}" cy="{:.3f}" r="{}" style="fill: none; {}" />'''.format(
            x_pos(note.sort_time),
            y_pos(note.sort_time),
            5,
            dot_color,
        )
        rendered_notes.append(svg_element)

    return '''<svg width="{}" height="100">{}</svg>'''.format(
        svg_width,
        '\n'.join(rendered_notes)
    )


def render_week_svg(week_scope, notes_dict, svg_width=800, row_height=50) -> str:
    def draw_line(hour, row):
        return '<line x1="{:.3f}" y1="{}" x2="{:.3f}" y2="{}" stroke="black" opacity="0.3" />'.format(
            svg_width * hour/24,
            row * row_height + 15, # TODO: this basically assumes height = 50
            svg_width * hour/24,
            row * row_height + 35,
        )

    # Pre-populate some lines, for the week of 8 days
    rendered_notes = []

    # First row is only 12 hours
    for hour in range(12,25):
        rendered_notes.append(draw_line(hour, 0))
    # Normal, non-chopped days
    for row in range(1,8):
        for hour in range(1,25):
            svg = draw_line(hour, row)
            rendered_notes.append(svg)
    # Last row is only 12 hours
    for hour in range(1,13):
        rendered_notes.append(draw_line(hour, 8))

    # day boundary lines
    for row in range(1,8):
        rendered_notes.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="black" />'.format(
            0,
            row * row_height + 10,
            0,
            row * row_height + 50
        ))

    # Rendering notes
    start_time = datetime.strptime(week_scope + '.1', '%G-ww%V.%u') - timedelta(days=1)
    width_factor = svg_width / (24*60*60)

    def x_pos(t):
        seconds_since_midnight = (t - start_time).total_seconds() % (24*60*60)
        return seconds_since_midnight * width_factor

    def y_pos(t):
        row = int((t - start_time).total_seconds() / (24*60*60))
        return row * row_height + 0.5 * row_height

    # Read actual notes
    if "notes" in notes_dict:
        del notes_dict["notes"]

    for day_scope, day_dict in notes_dict.items():
        row = int(day_scope[-1])
        day_label = f'<text x="{svg_width/2}" y="{row * row_height + 42}" text-anchor="middle" opacity="0.5" style="font-size: 8px">{day_scope}</text>'
        rendered_notes.append(day_label)

        for note in day_dict["notes"]:
            if not note.sort_time:
                continue

            dot_color = "stroke: black"
            if note.domain_ids:
                dot_color = _stroke_color(note.domain_ids[0])

            svg_element = '<circle cx="{:.3f}" cy="{:.3f}" r="{}" style="fill: none; {}" />'.format(
                x_pos(note.sort_time),
                y_pos(note.sort_time),
                5,
                dot_color
            )
            rendered_notes.append(svg_element)

    return '''<svg width="{}" height="{}">{}</svg>'''.format(
        svg_width,
        9 * row_height,
        '\n'.join(rendered_notes)
    )
