from datetime import datetime

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


def test_to_json(note_v2_session):
    note = Note(time_scope_id="2123-ww45.6", desc="json testing report")
    note_v2_session.add(note)
    note_v2_session.flush()

    note_as_json = note.as_json()
    assert note_as_json['note_id'] == note.note_id
    assert note_as_json['time_scope_id'] == note.time_scope_id
    assert note_as_json['desc'] == note.desc


def test_to_from_json(note_v2_session):
    note = Note(time_scope_id="2123-ww45.6", desc="json testing report")
    note_v2_session.add(note)
    note_v2_session.flush()

    note_dict = note.as_json()
    del note_dict['note_id']

    note2 = Note.from_dict(note_dict)
    note_v2_session.add(note2)
    note_v2_session.commit()

    assert note2.note_id
    assert note2.time_scope_id == note.time_scope_id
    assert note2.sort_time == note.sort_time
    assert note2.source == note.source
    assert note2.desc == note.desc
    assert note2.detailed_desc == note.detailed_desc
    assert note2.created_at == note.created_at


def test_to_from_json_with_datetime(note_v2_session):
    note1 = Note(time_scope_id="2000-ww20.2", desc="854509e8")
    note1.sort_time = None
    note1.source = "note source #68506007"
    note1.detailed_desc = "note detailed_description, but shortened to _desc"
    note1.created_at = datetime.now()
    note_v2_session.add(note1)
    note_v2_session.commit()

    note_dict = note1.as_json()
    del note_dict['note_id']

    note2 = Note.from_dict(note_dict)
    note_v2_session.add(note2)
    note_v2_session.commit()

    assert note2.note_id
    assert note2.time_scope_id == note1.time_scope_id
    assert note2.sort_time == note1.sort_time
    assert note2.source == note1.source
    assert note2.desc == note1.desc
    assert note2.detailed_desc == note1.detailed_desc
    assert note2.created_at == note1.created_at
