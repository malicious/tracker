import csv
import json
from typing import Dict, Iterator

from sqlalchemy.exc import StatementError

from notes.models import Note, NoteDomain, Domain


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
