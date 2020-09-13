import csv
import itertools
import json
import re
from typing import Dict, Iterator

from flask import render_template
from sqlalchemy.exc import StatementError

from notes.models import Note, NoteDomain, Domain
from tasks.time_scope import TimeScopeUtils, TimeScope


def list_domains(note_id) -> Iterator:
    note_domains = NoteDomain.query \
        .filter(NoteDomain.note_id == note_id) \
        .all()
    return [nd.domain_id for nd in note_domains]


def note_to_json(note_id) -> Dict:
    note = Note.query \
        .filter(Note.note_id == note_id) \
        .one()

    note_domains = NoteDomain.query \
        .filter(NoteDomain.note_id == note_id) \
        .all()

    return {
        "note": note.to_json(),
        "domains": list_domains(note_id),
    }


def import_from_csv(csv_file, session):
    for csv_entry in csv.DictReader(csv_file):
        # Check for a pre-existing Note before adding one
        new_note = Note.from_csv(csv_entry)
        note = Note.query \
            .filter_by(time_scope_id=new_note.time_scope_id, desc=new_note.desc, title=new_note.title) \
            .one_or_none()
        if not note:
            session.add(new_note)
            note = new_note
            try:
                session.commit()
            except StatementError as e:
                print("Hit exception when parsing:")
                print(json.dumps(csv_entry, indent=4))
                session.rollback()
                continue

        # Then create the linked Domains
        if not csv_entry['domains']:
            raise ValueError(f"No domains specified for Note: \n{json.dumps(csv_entry, indent=4)}")

        sorted_domains = sorted([domain_str.strip() for domain_str in csv_entry['domains'].split('&') if not None])
        if not sorted_domains:
            print(json.dumps(csv_entry, indent=4))
            raise ValueError(f"No valid domains for Note: \n{json.dumps(csv_entry, indent=4)}")

        for domain_id in sorted_domains:
            new_domain = Domain(domain_id=domain_id)
            domain = Domain.query \
                .filter_by(domain_id=new_domain.domain_id) \
                .one_or_none()
            if not domain:
                session.add(new_domain)
                domain = new_domain

            new_link = NoteDomain(note_id=note.note_id, domain_id=domain.domain_id)
            link = NoteDomain.query \
                .filter_by(note_id=note.note_id, domain_id=domain.domain_id) \
                .one_or_none()
            if not link:
                session.add(new_link)
                link = new_link

        # Commit per Note, since Domains are likely to overlap
        session.commit()


def report_notes_by_domain(domain, session):
    # Get a top-level list of every TimeScope matching this Domain
    time_scopes = session.query(Note.time_scope_id) \
        .join(NoteDomain, Note.note_id == NoteDomain.note_id) \
        .filter(NoteDomain.domain_id == domain) \
        .all()
    # We need to flatten this list, for some reason
    time_scopes = set(itertools.chain.from_iterable(time_scopes))
    if not time_scopes:
        return {"error": f"No matching time_scopes for: {repr(domain)}"}

    # Find the week-TimeScopes that apply to our notes
    week_scopes = set(itertools.chain.from_iterable(
        TimeScopeUtils.enclosing_scope(TimeScope(s), TimeScope.Type.week) for s in time_scopes))

    notes_by_week = {}
    for week in sorted(week_scopes, reverse=True):
        day_summaries = Note.query \
            .join(NoteDomain, Note.note_id == NoteDomain.note_id) \
            .filter(NoteDomain.domain_id == domain) \
            .filter(Note.time_scope_id.like(week + ".%")) \
            .filter(Note.is_summary.is_(True)) \
            .all()

        day_week_long_notes = Note.query \
            .join(NoteDomain, Note.note_id == NoteDomain.note_id) \
            .filter(NoteDomain.domain_id == domain) \
            .filter(Note.time_scope_id.like(week + "%")) \
            .filter(Note.is_summary.isnot(True)) \
            .all()

        notes_by_week[week] = day_summaries + day_week_long_notes

    # And find the quarter-TimeScopes that apply
    notes_by_quarter = {}
    for week in sorted(week_scopes, reverse=True):
        quarter = TimeScopeUtils.enclosing_scope(week, TimeScope.Type.quarter)[0]
        # Create the dict that will hold the week's notes
        if quarter not in notes_by_quarter:
            notes_by_quarter[quarter] = {"quarter-notes": []}

            # Look up the quarter-specific notes
            quarter_notes = Note.query \
                .join(NoteDomain, Note.note_id == NoteDomain.note_id) \
                .filter(NoteDomain.domain_id == domain) \
                .filter(Note.time_scope_id == quarter) \
                .all()
            notes_by_quarter[quarter]["quarter-notes"] += quarter_notes

        # Look up weekly summaries
        week_summaries = Note.query \
            .join(NoteDomain, Note.note_id == NoteDomain.note_id) \
            .filter(NoteDomain.domain_id == domain) \
            .filter(Note.time_scope_id == week) \
            .filter(Note.is_summary.is_(True)) \
            .all()

        notes_by_quarter[quarter]["quarter-notes"] += week_summaries
        notes_by_quarter[quarter][week] = notes_by_week[week]

    """
    Format of the final notes_by_scope passed in:

    {
        "2020—Q3": {
            "quarter-notes": List[Note],
            "2020-ww33": List[Note],
            "2020-ww34": List[Note],
        },
    }
    """

    def match_domains(n: Note) -> str:
        domains = filter(lambda x: x != domain, list_domains(n.note_id))
        if not domains:
            return ""

        return ", ".join(domains)

    def time_scope_lengthener(note) -> str:
        return TimeScope(note.time_scope_id).lengthen()

    def desc_to_html(desc: str):
        # make HTML comments visible
        desc = re.sub(r'<!', r'&lt;!', desc)
        # make newlines have effect
        desc = re.sub('\n', r'<br />', desc)
        # make markdown links clickable
        desc = re.sub(r'\[(.+?)]\((.+?)\)',
                      r"""[\1](<a href="\2">\2</a>)""",
                      desc)
        return desc

    return render_template('note.html',
                           desc_to_html=desc_to_html,
                           match_domains=match_domains,
                           notes_by_quarter=notes_by_quarter,
                           time_scope_lengthener=time_scope_lengthener)
