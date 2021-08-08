from notes_v2.models import Note


def test_note_constructor():
    note = Note()
    assert note
