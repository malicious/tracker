import json

import jsondiff

from notes_v2.models import Note


def test_get_note(test_client, note_v2_session):
    n = Note(time_scope_id="2021-ww21.2", desc="shorte")
    note_v2_session.add(n)
    note_v2_session.commit()

    r = test_client.get('/v2/note/1')
    assert r.response

    response_json = json.loads(r.get_data())
    diff = jsondiff.diff(n.as_json(include_domains=True), response_json)
    assert not diff
