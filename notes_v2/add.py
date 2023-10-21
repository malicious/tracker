import csv
import json
import logging
import sys
from os import path
from typing import Dict, Optional, Set

from dateutil import parser
from sqlalchemy.exc import IntegrityError, PendingRollbackError

from notes_v2.models import Note, NoteDomain

_valid_csv_fields = ['created_at', 'sort_time', 'time_scope_id', 'domains', 'source', 'desc', 'detailed_desc']

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def tokenize_domain_ids(encoded_domain_ids: str):
    next_domain_id = ""
    current_token_start = 0

    while True:
        next_ampersand_index = encoded_domain_ids.find('&', current_token_start)

        # no more ampersands, return the rest of the string
        if next_ampersand_index == -1:
            next_domain_id += encoded_domain_ids[current_token_start:]
            yield next_domain_id
            break

        # If this ampersand is part of a pair (encoded), skip the first one
        if encoded_domain_ids[next_ampersand_index:next_ampersand_index + 2] == '&&':
            next_domain_id += encoded_domain_ids[current_token_start:next_ampersand_index + 1]
            current_token_start = next_ampersand_index + 2
            continue

        # Otherwise, it just gets to be its own token
        else:
            next_domain_id += encoded_domain_ids[current_token_start:next_ampersand_index]
            yield next_domain_id
            next_domain_id = ""
            current_token_start = next_ampersand_index + 1


def _special_tokenize(
        encoded_domain_ids: str,
        strip: bool=True,
) -> Set[str]:
    split_domain_ids = tokenize_domain_ids(encoded_domain_ids)

    if strip:
        split_domain_ids = map(str.strip, split_domain_ids)

    return set(d for d in split_domain_ids if d)


def _add_domains(session, note_id, encoded_domain_ids: str, expect_duplicates: bool = False):
    for domain_id in _special_tokenize(encoded_domain_ids):
        if expect_duplicates:
            nd_exists = session.query(
                NoteDomain.query
                .filter_by(note_id=note_id, domain_id=domain_id)
                .exists()
            ).scalar()
            if nd_exists:
                continue

        new_nd = NoteDomain(note_id=note_id, domain_id=domain_id)
        session.add(new_nd)


def one_from_csv(
        session,
        csv_entry: Dict,
        expect_duplicates: bool,
) -> Optional[Note]:
    # Filter CSV file to only have valid columns
    present_fields = [field for field in _valid_csv_fields if field in csv_entry.keys()]
    csv_entry = {field: csv_entry[field] for field in present_fields if csv_entry[field]}
    if not csv_entry:
        return None

    encoded_domain_ids = None
    if csv_entry.get('domains'):
        encoded_domain_ids = csv_entry['domains']
        del csv_entry['domains']

    target_note = None
    if expect_duplicates:
        try:
            inexact_match_exists = session.query(
                Note.query.filter_by(time_scope_id=csv_entry['time_scope_id'],
                                     desc=csv_entry['desc'])
                .exists()
            ).scalar()

        # TODO: Handle this properly, don't just do whatever the error message says.
        #       This happened from having duplicate/identical entries right before?
        except PendingRollbackError:
            logger.warning(csv_entry)
            session.rollback()
            raise

        if inexact_match_exists:
            matchmaker_dict = dict(csv_entry)
            for field in ['sort_time', 'created_at']:
                # db search needs datetime objects, not the CSV string
                if field in matchmaker_dict:
                    matchmaker_dict[field] = parser.parse(matchmaker_dict[field])

            thorough_match = Note.query.filter_by(**matchmaker_dict).all()

            if len(thorough_match) > 1:
                return None
            elif len(thorough_match) == 1:
                target_note = thorough_match[0]

    if not target_note:
        target_note = Note.from_dict(csv_entry)

        # If we're creating a new Note, flush it to SQLAlchemy ORM
        # so we can add matching NoteDomains.
        if target_note:
            session.add(target_note)
            session.flush()

    if encoded_domain_ids:
        _add_domains(session, target_note.note_id, encoded_domain_ids,
                     expect_duplicates=expect_duplicates if target_note else False)

    return target_note


def all_from_csv(
        session,
        csv_file,
        expect_duplicates: bool,
):
    times_todo_ignored = 0
    times_import_failed = 0

    reader = csv.DictReader(csv_file)
    for entry_index, csv_entry in enumerate(reader):
        try:
            one_from_csv(session, csv_entry, expect_duplicates)

            if (entry_index + 1) % 1000 == 0:
                logger.info(f"Imported {entry_index + 1:7_} entries so far, up to {import_source}")

        except (KeyError, IntegrityError):
            if "todo" in csv_entry["domains"]:
                times_todo_ignored += 1
                continue

            logger.warning('\n'.join([
                "Couldn't import CSV row: ",
                json.dumps(csv_entry, indent=2, ensure_ascii=False),
                '',
            ]))

            times_import_failed += 1
            continue

    if times_todo_ignored > 0:
        logger.warning(f"Ignored malformed CSV rows with domain \"todo\" "
                       f"({times_todo_ignored} times in {path.basename(csv_file.name)})")

    # TODO: There's some overlap between import fails and \"todo\" notes,
    #       clarify in a way that makes it clear what the user should do
    if times_import_failed > 0:
        logger.warning(f"Failed to import {times_import_failed} additional rows from {path.basename(csv_file.name)}")

    session.commit()


def all_to_csv(
        outfile=sys.stdout,
        write_note_id: bool=False,
):
    def one_to_csv(n: Note) -> Dict:
        note_as_json = n.as_json(include_domains=True)
        if not write_note_id:
            del note_as_json['note_id']

        if 'domains' in note_as_json:
            split_domains = [d.replace('&', '&&') for d in note_as_json['domains']]
            encoded_domain_ids = " & ".join(split_domains)

            note_as_json['domains'] = encoded_domain_ids

        return note_as_json

    fieldnames = list(_valid_csv_fields)
    if write_note_id:
        fieldnames.append('note_id')

    # Write permitted fields to CSV
    writer = csv.DictWriter(outfile, fieldnames=fieldnames, lineterminator='\n')
    writer.writeheader()

    # TODO: Can't `map(csv.DictWriter.writerow)`, why?
    for n_csv in map(one_to_csv, Note.query.all()):
        writer.writerow(n_csv)

