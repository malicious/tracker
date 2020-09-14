import csv
import itertools
import json
import re
from datetime import datetime
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


def _add_domains_for(note_id, domain_str: str, session, do_commit: bool = True):
    """
    Pass `session` if you want this function to do the commit.
    """
    sorted_domains = sorted([d.strip() for d in domain_str.split('&') if not None])
    if not sorted_domains:
        raise ValueError(f"No valid domains provided for Note")

    for domain_id in sorted_domains:
        new_domain = Domain(domain_id=domain_id)
        domain = Domain.query \
            .filter_by(domain_id=new_domain.domain_id) \
            .one_or_none()
        if not domain:
            session.add(new_domain)
            domain = new_domain

        new_link = NoteDomain(note_id=note_id, domain_id=domain.domain_id)
        link = NoteDomain.query \
            .filter_by(note_id=note_id, domain_id=domain.domain_id) \
            .one_or_none()
        if not link:
            session.add(new_link)
            link = new_link

    if do_commit:
        session.commit()


def import_from_csv(csv_file, session):
    for csv_entry in csv.DictReader(csv_file):
        # Check for a pre-existing Note before adding one
        new_note = Note.from_csv(csv_entry)
        note = Note.query \
            .filter_by(time_scope_id=new_note.time_scope_id,
                       desc=new_note.desc,
                       title=new_note.title) \
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
        if 'domains' not in csv_entry or not csv_entry['domains']:
            raise ValueError(f"No domains specified for Note: \n{json.dumps(csv_entry, indent=4)}")

        try:
            _add_domains_for(note.note_id, csv_entry['domains'], session)
        except (ValueError, StatementError):
            print(json.dumps(csv_entry, indent=4))
            raise ValueError(f"No valid domains for Note: \n{json.dumps(csv_entry, indent=4)}")


def add_note_from_cli(session):
    desc = input(f'{"Enter description (blank to quit)": <40}: ')
    if not desc:
        return None

    # Read other attributes
    created_at = datetime.now()
    today_scope = TimeScope(created_at.strftime("%G-ww%V.%u"))
    requested_scope = input(f'{f"Enter scope [{today_scope}]": <40}: ')
    if not requested_scope:
        requested_scope = today_scope
    try:
        requested_scope = TimeScope(requested_scope)
        requested_scope.get_type()
    except ValueError as e:
        print(e)
        return None
    print(f"{'': <2}parsed as {requested_scope}")

    # Read enough things to create a Note
    requested_domains = input(f'{f"Enter domains, separated by &": <40}: ')
    source = input(f'{"Enter title (optional)": <40}: ')

    n = Note(
        time_scope_id=requested_scope,
        desc=desc,
        created_at=created_at,
        is_summary=True,
        source=source,
    )

    try:
        session.add(n)
        session.commit()
    except StatementError as e:
        print("")
        print("Hit exception when parsing:")
        print(json.dumps(n.to_json(), indent=4))
        session.rollback()
        return None

    # Add domains, note to database
    try:
        _add_domains_for(n.note_id, requested_domains, session)
    except (ValueError, StatementError):
        print("")
        print("Hit exception when parsing:")
        print(json.dumps(n.to_json(), indent=4))
        session.rollback()
        return None

    return n


def add_from_cli(session):
    all_notes = []

    while True:
        n = add_note_from_cli(session)
        if not n:
            break

        all_notes.append(n)
        print(f"  successfully added Note: {n.note_id}")
        print("")

    # Done, print output
    # TODO: print as CSV
    print(json.dumps([n.to_json() for n in all_notes], indent=4))


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
            .order_by(Note.time_scope_id) \
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

        # Replace spaces in domain names, so they don't break
        domains = [d.replace(' ', '&nbsp;') for d in domains]

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
