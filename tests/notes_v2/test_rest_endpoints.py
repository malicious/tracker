import json

import jsondiff

from notes_v2.models import Note, NoteDomain


def test_get_note(test_client, note_v2_session):
    n = Note(time_scope_id="2021-ww21.2", desc="shorte")
    note_v2_session.add(n)
    note_v2_session.commit()

    r = test_client.get('/v2/note/1')
    assert r.response

    response_json = json.loads(r.get_data())
    diff = jsondiff.diff(n.as_json(include_domains=True), response_json)
    assert not diff


def test_get_domain_stats(test_client, note_v2_session):
    n = Note(time_scope_id="2021-ww32.2", desc="stacked note")
    note_v2_session.add(n)
    note_v2_session.flush()

    for d in ["domain 1", "domain 2", "d3", "d4"]:
        nd = NoteDomain(note_id=n.note_id, domain_id=d)
        note_v2_session.add(nd)
    note_v2_session.commit()

    assert len(NoteDomain.query.all()) == 4

    # Test actual REST API
    r = test_client.get('/v2/stats/domains')
    j = json.loads(r.get_data())

    assert "domain 1" in j


def test_domain_stats_no_domains(test_client):
    # Test actual REST API
    r = test_client.get('/v2/stats/domains')
    j = json.loads(r.get_data())

    assert not j
