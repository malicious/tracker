import io
import json

import jsondiff

from notes_v2.add import all_from_csv
from notes_v2.report.gather import NoteStapler
from util import TimeScope


def test_stapler_basic(note_v2_session):
    ns = NoteStapler(note_v2_session, [], week_promotion_threshold=9, quarter_promotion_threshold=17)
    assert ns

    ns._construct_scope_tree(TimeScope("2021-ww32.3"))

    ref_st = {
        "2021—Q3": {
            "2021-ww32": {
                "2021-ww32.3": {
                    "notes": [],
                },
                "notes": [],
            },
            "notes": [],
        }
    }
    assert not jsondiff.diff(ref_st, ns.scope_tree)


def test_stapler_collapse(note_v2_session):
    ns = NoteStapler(note_v2_session, [], week_promotion_threshold=0, quarter_promotion_threshold=0)
    ns._construct_scope_tree(TimeScope("2021-ww32.3"))
    ns._construct_scope_tree(TimeScope("2021-ww31.7"))
    ns._collapse_scope_tree(TimeScope("2021—Q3"))

    assert not jsondiff.diff(ns.scope_tree, {
        "2021—Q3": {
            "notes": []
        }
    })


def test_domain_filtering(test_client, note_v2_session):
    io_test_file = """created_at,sort_time,time_scope_id,source,desc,detailed_desc,domains
,,2021-ww31.6,,"long, long description, with commas",,
2000-01-01 00:00:00,,2021-ww31.7,"maybe-invalid\r\ncopy-pasted CRLF newlines",okie desc,,domains: no
2000-01-01 00:00:00,2021-08-08 15:37:55.679000,2021-ww31.7,,"escaped ""desc""
with regular LF-only newline",unniecode ❲😎😎😎❳,domains: no & domains: yes
"""
    all_from_csv(note_v2_session, io.StringIO(io_test_file), expect_duplicates=False)

    r = test_client.get('/v2/notes?domain=domains:%20no')
    j = json.loads(r.get_data())

    assert ['2021—Q3'] == list(j.keys())
    assert ['notes'] == list(j['2021—Q3'].keys())
    assert 2 == len(j['2021—Q3']['notes'])
