from typing import Dict, Iterator

from notes.models import Note, NoteDomain


def _list_domains(note_id) -> Iterator:
    note_domains = NoteDomain.query \
        .filter(NoteDomain.note_id == note_id) \
        .all()
    return [nd.domain_id for nd in note_domains]


def report_one_note(note_id) -> Dict:
    note: Note = Note.query \
        .filter(Note.note_id == note_id) \
        .one()

    return {
        "note": note.to_json(),
        "domains": _list_domains(note_id),
    }
