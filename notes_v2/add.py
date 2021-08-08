import csv
import json
from typing import List

from notes_v2.models import Note, NoteDomain


def _special_tokenize(encoded_domain_ids: str, strip_and_sort: bool = True) -> List[str]:
    split_domain_ids = []

    next_domain_id = ""
    current_token_start = 0

    while True:
        next_ampersand_index = encoded_domain_ids.find('&', current_token_start)

        # no more ampersands, return the rest of the string
        if next_ampersand_index == -1:
            next_domain_id += encoded_domain_ids[current_token_start:]
            split_domain_ids.append(next_domain_id)
            break

        # If this ampersand is part of a pair (encoded), add the first one
        if encoded_domain_ids[next_ampersand_index:next_ampersand_index + 2] == '&&':
            next_domain_id += encoded_domain_ids[current_token_start:next_ampersand_index + 1]
            current_token_start = next_ampersand_index + 2
            continue

        # Otherwise, it just gets to be its own token
        else:
            next_domain_id += encoded_domain_ids[current_token_start:next_ampersand_index]
            split_domain_ids.append(next_domain_id)
            next_domain_id = ""
            current_token_start = next_ampersand_index + 1

    if strip_and_sort:
        split_domain_ids = [d.strip() for d in split_domain_ids]
        split_domain_ids = sorted([d for d in split_domain_ids if d])

    return split_domain_ids


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


def one_from_csv(session, csv_entry, expect_duplicates: bool) -> Note:
    encoded_domain_ids = ""
    if 'domains' in csv_entry:
        encoded_domain_ids = csv_entry['domains']
        del csv_entry['domains']

    target_note = None
    if expect_duplicates:
        inexact_match_exists = session.query(
            Note.query.filter_by(time_scope_id=csv_entry['time_scope_id'],
                                 desc=csv_entry['desc'])
                .exists()
        ).scalar()
        if inexact_match_exists:
            thorough_match = Note.query.filter_by(**csv_entry).all()
            if len(thorough_match) > 1:
                print(f"WARN: Skipping CSV row with duplicate entries {json.dumps(csv_entry, indent=2)}")
                return None
            elif len(thorough_match) == 1:
                target_note = thorough_match[0]

    if not target_note:
        target_note = Note.from_dict(csv_entry)
        session.add(target_note)
        session.flush()

    _add_domains(session, target_note.note_id, encoded_domain_ids,
                 expect_duplicates=expect_duplicates if target_note else False)
    return target_note


def all_from_csv(session, csv_file, expect_duplicates: bool):
    for csv_entry in csv.DictReader(csv_file):
        one_from_csv(session, csv_entry, expect_duplicates)

    session.commit()
