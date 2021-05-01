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
    sorted_domains = sorted([d for d in split_domains if d != ""])

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


def _find_existing_note(all_fields, fields_allow_list):
    unique_args = {}
    for field in fields_allow_list:
        if field in all_fields and all_fields[field] is not None:
            unique_args[field] = all_fields[field]
        else:
            # This helps with some kind of search error in the below `.filter_by` call,
            # specifically when a datetime (created_at?) doesn't exist, then a later
            # json.dumps() call fails because it doesn't know what to do with default-created datetimes.
            #
            # I think.
            unique_args[field] = None

    n = Note.query \
        .filter_by(**unique_args) \
        .one_or_none()
    # TODO: multiple isn't _that_ exceptional, handle the case without exceptions
    # - replace one_or_none() with all() and length checks (maybe)
    return n



def _add_note(session, domains: str, **kwargs) -> Optional[Note]:
    # Skip blank rows.
    # Happens sometimes when adding blank rows in a CSV editor
    if len(kwargs) == 0:
        return None

    # Check for an existing note
    try:
        # Do fast check for existing notes (sub-minimal set of unique fields)
        n = _find_existing_note(kwargs, ['time_scope_id', 'short_desc'])

        # Fast part: if nothing exists, just create a new note
        if not n:
            n = Note(**kwargs)
            session.add(n)

            try:
                session.commit()
            except StatementError as e:
                print(f"Hit exception when parsing: {e}")
                print(json.dumps(n.to_json(), indent=4))
                session.rollback()
                return None

    # If fast check returned multiple notes, do a more thorough check
    except MultipleResultsFound as e:
        try:
            n = _find_existing_note(kwargs, ['source', 'type', 'sort_time', 'time_scope_id', 'short_desc', 'desc'])
        except MultipleResultsFound as e:
            # super-failure case: multiple entries exist, just skip it
            print(e)
            print(json.dumps(kwargs, indent=4))
            return None

        # simpler case: exactly one note already exists
        if n is not None:
            pass

        # final case: just create a new note
        else:
            n = Note(**kwargs)
            session.add(n)

            try:
                session.commit()
            except StatementError as e:
                print(f"Hit exception when parsing: {e}")
                print(json.dumps(n.to_json(), indent=4))
                session.rollback()
                return None

    # Of all the fields we could care about, only domains are potentially updated.
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
