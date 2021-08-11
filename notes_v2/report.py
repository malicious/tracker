import hashlib
import json

from flask import render_template

from notes_v2.models import Note, NoteDomain


def _render_n2_domains(n: Note):
    def domain_to_css_color(domain: str) -> str:
        domain_hash = hashlib.sha256(domain.encode('utf-8')).hexdigest()
        domain_hash_int = int(domain_hash[0:4], 16)

        color_h = ((domain_hash_int + 4) % 8) * (256.0/8)
        return f"color: hsl({color_h}, 70%, 50%);"

    def domain_to_html_link(domain: str) -> str:
        # TODO: Convert to <a> once domain filters are in place
        return f'<span style="{domain_to_css_color(domain)}">{domain}</span>'

    domains_as_html = [domain_to_html_link(d) for d in n.domain_ids]
    return " & ".join(domains_as_html)


def edit_notes():
    def render_n2_desc(n: Note):
        output_str = ""

        # Generate a <span> that holds some kind of sort_time
        output_str += f'<span class="time">{n.time_scope_id}</span>\n'

        # Print the description
        output_str += f'<span class="desc">{n.desc}</span>\n'

        # And color-coded, hyperlinked domains
        output_str += f'<span class="domains">{_render_n2_domains(n)}</span>\n'

        # detailed_desc, only if needed
        if n.detailed_desc:
            output_str += f'<div class="detailed-desc">{n.detailed_desc}</div>'

        return output_str

    def render_n2_json(n: Note) -> str:
        return json.dumps(n.as_json(include_domains=True), indent=2)

    return render_template('notes-v2.html',
                           render_n2_desc=render_n2_desc,
                           render_n2_json=render_n2_json,
                           notes_list=Note.query.all())


def edit_notes_simple(*args):
    """
    Render a list of Notes as simply as possible

    Still tries to exercise the same codepaths as a normal endpoint, though.
    """
    def render_n2_desc(n: Note):
        return n.desc

    def render_n2_json(n: Note) -> str:
        return json.dumps(n.as_json(include_domains=True), indent=2)

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
