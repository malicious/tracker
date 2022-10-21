import csv
import json
from typing import Optional

from dateutil import parser
from sqlalchemy.exc import StatementError

from notes.models import Note, NoteDomain


def _special_tokenize(domain_str):
    split_domains = []
    token = ""
    token_index = 0

    while True:
        #print(f"remaining: \"{token}\" + \"{domain_str[token_index:]}\"")
        current_index = domain_str.find('&', token_index)
        if current_index == -1:
            token += domain_str[token_index:]
            split_domains.append(token)
            break

        # If this ampersand is part of a pair, split the first chunk into token parser
        if domain_str[current_index:current_index + 2] == '&&':
            token += domain_str[token_index:current_index + 1]
            token_index = current_index + 2
            continue
        # Otherwise, it just gets to be its own token
        else:
            token += domain_str[token_index:current_index]
            split_domains.append(token)
            token = ""
            token_index = current_index + 1

    return split_domains


def _add_domains_for(note_id, domain_str: str, session, do_commit: bool = True):
    """
    Pass `session` if you want this function to do the commit.

    CSV files can use "&&" as an escape, as we handle that specially.
    """
    if "&&" in domain_str:
        split_domains = [d.strip() for d in _special_tokenize(domain_str)]
    else:
        split_domains = [d.strip() for d in domain_str.split('&')]

    sorted_domains = sorted([d for d in split_domains if d != ""])

    for domain_id in sorted_domains:
        if not domain_id:
            raise ValueError("Blank domain_id found, please check your parsing code (parsed from \"{domain_str}\")")

        link_exists = session.query( \
            NoteDomain.query \
                .filter_by(note_id=note_id, domain_id=domain_id) \
                .exists()
        ).scalar()
        if not link_exists:
            new_link = NoteDomain(note_id=note_id, domain_id=domain_id)
            session.add(new_link)

    if do_commit:
        session.commit()


def _generate_note_query(all_fields, fields_allow_list):
    unique_args = {}
    for field in fields_allow_list:
        if field in all_fields and all_fields[field] is not None:
            unique_args[field] = all_fields[field]

    return Note.query.filter_by(**unique_args)


def _add_note(session, domains: str, **kwargs) -> Optional[Note]:
    # Skip blank rows.
    # Happens sometimes when adding blank rows in a CSV editor
    if len(kwargs) == 0:
        return None

    # Do fast check for existing notes (sub-minimal set of unique fields)
    inexact_match_exists = session.query( \
        _generate_note_query(kwargs, ['time_scope_id', 'short_desc']) \
            .exists()
    ).scalar()
    if not inexact_match_exists:
        # Fast part: if nothing exists, just create a new note
        n = Note(**kwargs)
        session.add(n)

        try:
            session.commit()
        except StatementError as e:
            print(f"Hit exception when parsing: {e}")
            print(json.dumps(n.to_json(), indent=4))
            session.rollback()
            return None

    # If any results were returned, do a more thorough check
    thorough_query = _generate_note_query(kwargs, ['source', 'type', 'sort_time', 'time_scope_id', 'short_desc'])
    results_exist = session.query(thorough_query.exists()).scalar()
    if results_exist:
        results = thorough_query.all()
        if len(results) > 1:
            print("Multiple results found for query")
            print(json.dumps(kwargs, indent=4, default=str))
            return None

        n = results[0]
    else:
        # final case: just create a new note
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
    # Import speed on current system is approx 100 rows/second
    # TODO: Replace random numbers with an actual per-unit-time measurement
    #       (max of time or rows, for rate limiting)
    IMPORT_BATCH_SIZE = 200
    rows_read = 0

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

        # Print status messages, for long imports
        rows_read += 1
        if rows_read % IMPORT_BATCH_SIZE == 0:
            print(f"Parsed CSV row: {rows_read}")

    if rows_read >= IMPORT_BATCH_SIZE:
        print(f"Finished importing {rows_read} rows")
