import csv
import json
import sys
from typing import List, Dict, Optional

from dateutil import parser
from sqlalchemy.exc import IntegrityError

from notes_v2.models import Note, NoteDomain


_valid_csv_fields = ['created_at', 'sort_time', 'time_scope_id', 'domains', 'source', 'desc', 'detailed_desc']


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


def one_from_csv(session, csv_entry, expect_duplicates: bool) -> Optional[Note]:
    # Filter CSV file to only have valid columns
    present_fields = [field for field in _valid_csv_fields if field in csv_entry.keys()]
    csv_entry = { field: csv_entry[field] for field in present_fields if csv_entry[field] }
    if not csv_entry:
        return None

    encoded_domain_ids = None
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
        if target_note:
            session.add(target_note)
            session.flush()

    if encoded_domain_ids:
        _add_domains(session, target_note.note_id, encoded_domain_ids,
                     expect_duplicates=expect_duplicates if target_note else False)

    return target_note


def all_from_csv(session, csv_file, expect_duplicates: bool):
    for csv_entry in csv.DictReader(csv_file):
        try:
            one_from_csv(session, csv_entry, expect_duplicates)
        except (KeyError, IntegrityError):
            print('-' * 72)
            print(f"WARN: Couldn\'t import CSV row")
            print(json.dumps(csv_entry, indent=2))
            print()
            continue

    session.commit()


def all_to_csv(outfile=sys.stdout, write_note_id: bool = False):
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
    writer = csv.DictWriter(outfile, fieldnames=fieldnames, lineterminator='\n')

    writer.writeheader()
    for n in Note.query.all():
        writer.writerow(one_to_csv(n))
