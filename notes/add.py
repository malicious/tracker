import csv
import json
from typing import Optional

from dateutil import parser
from sqlalchemy.exc import StatementError
from sqlalchemy.orm.exc import MultipleResultsFound

from notes.models import Note, NoteDomain


def _add_domains_for(note_id, domain_str: str, session, do_commit: bool = True):
    """
    Pass `session` if you want this function to do the commit.
    """
    split_domains = [d.strip() for d in domain_str.split('&')]
    sorted_domains = sorted([d for d in split_domains if d is not ""])

    for domain_id in sorted_domains:
        if not domain_id:
            raise ValueError("Blank domain_id found, please check your parsing code (parsed from \"{domain_str}\")")

        new_link = NoteDomain(note_id=note_id, domain_id=domain_id)
        link = NoteDomain.query \
            .filter_by(note_id=note_id, domain_id=domain_id) \
            .one_or_none()
        if not link:
            session.add(new_link)
            link = new_link

    if do_commit:
        session.commit()


def _add_note(session, domains: str, **kwargs) -> Optional[Note]:
    # Skip blank rows.
    # Happens sometimes when adding blank rows in a CSV editor
    if len(kwargs) == 0:
        return None

    unique_args = {}
    for field in ['source', 'type', 'sort_time', 'time_scope_id', 'short_desc', 'desc']:
        if field in kwargs and kwargs[field]:
            unique_args[field] = kwargs[field]
        else:
            unique_args[field] = None

    # Check for an existing note
    try:
        n = Note.query \
            .filter_by(**unique_args) \
            .one_or_none()
    except MultipleResultsFound as e:
        print(e)
        print(json.dumps(kwargs, indent=4))
        return None

    if not n:
        # Otherwise just create a new note
        n = Note(**kwargs)
        session.add(n)

        try:
            session.commit()
        except StatementError as e:
            print(f"Hit exception when parsing: {e}")
            print(json.dumps(n.to_json(), indent=4))
            session.rollback()
            return None

    # Add domains, note to database
    try:
        _add_domains_for(n.note_id, domains, session)
    except (ValueError, StatementError) as e:
        print("Hit exception when parsing domains:")
        print(e)
        print("")
        print(json.dumps(n.to_json(), indent=4))
        print("")
        session.rollback()
        return None

    return n


def import_from_csv(csv_file, session):
    for csv_entry in csv.DictReader(csv_file):
        note_args = {}

        # 'scope' column can be blank in incomplete CSV files;
        # in those cases, just pass an incomplete dict to add_note and let it sort it out
        if csv_entry['scope']:
            note_args['time_scope_id'] = csv_entry['scope']

        for field in ['source', 'type', 'short_desc', 'desc']:
            value = csv_entry.get(field)
            if value:
                note_args[field] = value

        for field in ['created_at', 'sort_time']:
            value = csv_entry.get(field)
            if value:
                note_args[field] = parser.parse(csv_entry[field])

        _add_note(session, csv_entry['domains'], **note_args)
