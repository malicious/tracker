from typing import Dict, Iterator

from notes.models import Note, NoteDomain


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
