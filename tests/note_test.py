import io

from notes.models import Note


def test_note_constructor():
    note = Note(time_scope_id="2020-ww02.6")
    assert note


def test_create(session):
    note = Note(time_scope_id="2020-ww20.4", short_desc="status update")
    assert note.note_id is None

    session.add(note)
    session.commit()
    assert note.note_id is not None
