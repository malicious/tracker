import csv
import json
import logging
import sys
from dataclasses import dataclass
from os import path
from typing import Dict, Optional, Set

from dateutil import parser
from sqlalchemy.exc import IntegrityError, PendingRollbackError

from notes_v2.models import Note, NoteDomain

_valid_csv_fields = [
    'created_at',
    'sort_time',
    'desc',
    'detailed_desc',
    'domains',
    'time_scope_id',
    'source',
    'metadata',
]

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

    # Backfill older content that only has `source` field, and not `metadata`
    if not csv_entry.get('metadata'):
        if csv_entry.get('source'):
            csv_entry['metadata'] = f"- source: {csv_entry.get('source')}"

    if 'source' in csv_entry:
        del csv_entry['source']

    # Parse the `domains` field a little specially.
    encoded_domain_ids = None
    if csv_entry.get('domains'):
        encoded_domain_ids = csv_entry['domains']
        del csv_entry['domains']

    # Finally, upsert the new note.
    # NB Now that we have `import_source` tracking, it's probably okay to skip the checking.
    target_note = None
    if expect_duplicates:
        try:
            inexact_match_exists = session.query(
                Note.query.filter_by(time_scope_id=csv_entry['time_scope_id'],
                                     desc=csv_entry['desc'])
                .exists()
            ).scalar()

        except KeyError:
            logger.warning(csv_entry)
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
    @dataclass
    class ImportResult:
        ignored_todo: int = 0
        import_failed_parser_error: int = 0
        import_failed_integrity_error: int = 0
        import_succeeded: int = 0

    result = ImportResult()

    reader = csv.DictReader(csv_file)
    for entry_index, csv_entry in enumerate(reader):
        try:
            one_from_csv(session, csv_entry, expect_duplicates)
            result.import_succeeded += 1

            if (entry_index + 1) % 1000 == 0:
                logger.debug(f"{csv_file.name} => reviewed {entry_index + 1:7_} CSV rows so far")

        except parser.ParserError as e:
            if print_details:
                logger.warning(e)

            result.import_failed_parser_error += 1
            continue

        # TODO: Handle this properly, don't just do whatever the error message says.
        #       This happened from having duplicate/identical entries right before?
        except PendingRollbackError:
            logger.warning(csv_entry)
            session.rollback()

            # Instead of re-raising the exception, end import and expect user to re-run
            return

        except (KeyError, IntegrityError) as e:
            if (
                    "domains" in csv_entry
                    and "todo" in csv_entry.get("domains")
            ):
                result.ignored_todo += 1
                continue

            logger.warning('\n'.join([
                f"Couldn't import CSV row, {e}: ",
                json.dumps(csv_entry, indent=2, ensure_ascii=False),
                '',
            ]))

            result.import_failed_integrity_error += 1
            continue

    if result.ignored_todo > 0:
        logger.warning(f"{csv_file.name}: Ignored {result.ignored_todo} malformed CSV rows with domain \"todo\"")

    if result.import_failed_parser_error > 0:
        logger.warning(f"{csv_file.name}: Failed to import {result.import_failed_parser_error} rows due to parsing error, check file contents")

    session.commit()
    logger.info(f"Imported {result.import_succeeded} notes from {csv_file.name}")

    if print_details:
        logger.info(result)


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

