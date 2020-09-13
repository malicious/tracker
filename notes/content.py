from typing import Dict

from notes.models import Note, NoteDomain


def note_to_json(note_id) -> Dict:
    note = Note.query \
        .filter(Note.note_id == note_id) \
        .one()

    note_domains = NoteDomain.query \
        .filter(NoteDomain.note_id == note_id) \
        .all()

    return {
        "note": note.to_json(),
        "domains": [nd.domain_id for nd in note_domains],
    }
