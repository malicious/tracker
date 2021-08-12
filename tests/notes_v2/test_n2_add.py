import io

from notes_v2.add import _special_tokenize, all_from_csv, all_to_csv
from notes_v2.models import Note, NoteDomain


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
    assert len(Note.query.all()) == 1
    assert Note.query.one()


def test_from_csv_full(note_v2_session):
    csv_test_file = """source,created_at,sort_time,time_scope_id,source,desc,detailed_desc,domains
,,,2021-ww21.1,,"still, minimally-populated task",,
,,,2021-ww21.1,,second minimal task,,
,,,2021-ww21.1,,aaand a third task,,
,,,2021-ww21.1,,"please automate this CSV editing",,
,,,2021-ww21.2,,"still, minimally-populated task",,domain: 21.1 & domain: 21.2
,2021-07-01 00:00,,2021-ww22.1,,task but with datetime,,
,2021-07-01 00:00,,2021-ww22.2,,task but with datetime,,domain: 22.1 & domain: 22.2 &&_&&
behind the waterfall,2021-07-02 23:59:48.001,2021-08-02 23:59:48.002,2021-ww23.1,doubled source field,task but with datetime,,
behind the waterfall,2021-07-02 23:59:48.001,2021-08-02 23:59:48.002,2021-ww23.2,doubled source field,task but with datetime,,d-d-d-domain
"""
    all_from_csv(note_v2_session, io.StringIO(csv_test_file), expect_duplicates=False)

    assert len(Note.query.all()) == 9


def test_from_csv_duplicate(note_v2_session):
    duplicitous_csv_test_file = """time_scope_id,desc
2021-ww31.6,"long, long description, with commas"
"""
    all_from_csv(note_v2_session, io.StringIO(duplicitous_csv_test_file), expect_duplicates=False)
    all_from_csv(note_v2_session, io.StringIO(duplicitous_csv_test_file), expect_duplicates=True)

    assert len(Note.query.all()) == 1
    assert Note.query.one()


def test_to_from_csv(note_v2_session):
    import_export_test_file = """created_at,sort_time,time_scope_id,source,desc,detailed_desc,domains
,,2021-ww31.6,,"long, long description, with commas",,
"""
    all_from_csv(note_v2_session, io.StringIO(import_export_test_file), expect_duplicates=False)
    assert len(Note.query.all()) > 0

    outfile = io.StringIO()
    all_to_csv(outfile)
    assert outfile.getvalue() == import_export_test_file


def test_to_from_csv_stress(note_v2_session):
    io_test_file = """created_at,sort_time,time_scope_id,source,desc,detailed_desc,domains
,,2021-ww31.6,,"long, long description, with commas",,
2000-01-01 00:00:00,,2021-ww31.7,"maybe-invalid\r\ncopy-pasted CRLF newlines",okie desc,,domains: no
2000-01-01 00:00:00,2021-08-08 15:37:55.679000,2021-ww31.7,,"escaped ""desc""
with regular LF-only newline",unniecode ❲😎😎😎❳,domains: no & domains: yes
"""
    expected_count = 3

    input_data = io_test_file
    for _ in range(5):
        # Clear existing DB contents, if needed
        NoteDomain.query.delete()
        Note.query.delete()
        note_v2_session.commit()

        # Import
        all_from_csv(note_v2_session, io.StringIO(input_data), expect_duplicates=False)
        assert len(Note.query.all()) == expected_count

        # Export
        outfile = io.StringIO()
        all_to_csv(outfile)

        assert outfile.getvalue() == input_data
        input_data = outfile.getvalue()

    assert input_data == io_test_file


def test_with_blank_lines(note_v2_session):
    csv_test_file = """time_scope_id,desc
2021-ww32.2,desc early
,
,
2021-ww32.2,desc later
"""
    all_from_csv(note_v2_session, io.StringIO(csv_test_file), expect_duplicates=False)
    assert len(Note.query.all()) == 2


def test_with_extra_columns(note_v2_session):
    csv_test_file = """time_scope_id,desc,fake_column,super fake column
2021-ww32.2,desc early,,
2021-ww32.2,desc later,,
"""
    all_from_csv(note_v2_session, io.StringIO(csv_test_file), expect_duplicates=False)
    assert len(Note.query.all()) == 2


def test_with_note_id(note_v2_session):
    io_test_file = """created_at,sort_time,time_scope_id,source,desc,detailed_desc,domains
,,2021-ww31.6,,"long, long description, with commas",
2000-01-01 00:00:00,,2021-ww31.7,"maybe-invalid\r\ncopy-pasted CRLF newlines",okie desc,,domains: no
2000-01-01 00:00:00,2021-08-08 15:37:55.679000,2021-ww31.7,,"escaped ""desc""
with regular LF-only newline",unniecode ❲😎😎😎❳,domains: no & domains: yes
"""

    # Do import/export loop _once_, to get note_id's added to file
    all_from_csv(note_v2_session, io.StringIO(io_test_file), expect_duplicates=False)

    note_id_annotated_version = io.StringIO()
    all_to_csv(note_id_annotated_version, write_note_id=True)

    # Now, stress test, with the note_id's intact
    input_string = note_id_annotated_version.getvalue()
    for _ in range(3):
        NoteDomain.query.delete()
        Note.query.delete()
        note_v2_session.commit()

        input_stringio = io.StringIO(input_string)
        all_from_csv(note_v2_session, input_stringio, expect_duplicates=False)

        output_stringio = io.StringIO()
        all_to_csv(output_stringio, write_note_id=True)

        assert output_stringio.getvalue() == note_id_annotated_version.getvalue()
        assert output_stringio.getvalue() == note_id_annotated_version.getvalue()
        input_string = output_stringio.getvalue()
