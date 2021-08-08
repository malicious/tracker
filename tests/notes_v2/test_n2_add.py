import io

from notes_v2.add import _special_tokenize, all_from_csv
from notes_v2.models import Note


def test_tokenize_simple():
    assert _special_tokenize('') == []
    assert _special_tokenize('&') == []
    assert _special_tokenize('&&') == ['&']

    assert _special_tokenize('a & b') == ['a', 'b']
    assert _special_tokenize('a && b') == ['a & b']


def test_tokenize_annoying():
    assert _special_tokenize('R&&R & R') == sorted(['R&R', 'R'])
    assert _special_tokenize('&&&& & && & &') == sorted(['&&', '&'])


def test_from_csv_minimal(note_v2_session):
    minimal_csv_test_file = """time_scope_id,desc
2021-ww31.6,"long, long description, with commas"
"""
    all_from_csv(note_v2_session, io.StringIO(minimal_csv_test_file), expect_duplicates=False)

    # one row == one note
    assert Note.query.one()
