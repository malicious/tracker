from notes_v2.models import Note


def test_note_constructor():
    note = Note()
    assert note


def test_create(note_v2_session):
    note = Note(time_scope_id="2020-ww20.4", desc="status update")
    assert note.note_id is None

    note_v2_session.add(note)
    note_v2_session.flush()
    assert note.note_id is not None
