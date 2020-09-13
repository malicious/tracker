import io

from notes.content import import_from_csv
from notes.models import Note


def test_note_constructor():
    note = Note(time_scope_id="2020-ww02.6")
    assert note


def test_create(session):
    note = Note(time_scope_id="2020-ww20.4", title="status update")
    assert note.note_id is None

    session.add(note)
    session.commit()
    assert note.note_id is not None


def test_csv_import_one(session):
    csv_test_file = """scope,desc,title,domains
2020—Q1,long description for Q1,,d3
"""

    import_from_csv(io.StringIO(csv_test_file), session)

    n: Note = Note.query
    assert n.one()


def test_csv_import_multiple(session):
    csv_test_file = """scope,desc,title,domains
2020—Q1,long description for Q1,,d3
2020-ww43,,short title,d1
2020-ww23.2,desc,title,d1
2019—Q4,desc,title2,d2
2020-ww23.2,desc 3,title 3,d4
"""

    import_from_csv(io.StringIO(csv_test_file), session)

    n: Note = Note.query
    assert n.first()
