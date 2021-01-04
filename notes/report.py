import json
import re
from collections import defaultdict
from typing import Dict, Iterator

from flask import render_template

from notes.models import Note, NoteDomain
from tasks.time_scope import TimeScopeUtils, TimeScope


def _list_domains(note_id) -> Iterator:
    note_domains = NoteDomain.query \
        .filter(NoteDomain.note_id == note_id) \
        .all()
    return [nd.domain_id for nd in note_domains]


def report_one_note(note_id) -> Dict:
    note: Note = Note.query \
        .filter(Note.note_id == note_id) \
        .one()

    return {
        "note": note.to_json(),
        "domains": _list_domains(note_id),
    }


def report_notes(page_scope, page_domain):
    response_by_quarter = _report_notes_for(page_scope, page_domain)
    return _format_as_html(page_scope, page_domain, response_by_quarter)


class NotesFormatter:
    """
    Format of the final notes_by_scope sent out:

    {
        "2020—Q3": {
            "summaries": List[Note],
            "notes": List[Note],
            "child_scopes": {
                "2020-ww33": {
                    "summaries": List[Note],
                    "child_scopes": {
                        "2020-ww33.1": {
                            "notes": List[Note],
                        },
                    },
                },
                "2020-ww34": {
                    "notes": List[Note],
                },
            },
        },
    }
    """

    def __init__(self):
        self.scope_to_summaries_dict = defaultdict(list)
        self.scope_to_events_dict = defaultdict(list)
        self.scope_to_notes_dict = defaultdict(list)
        self.scope_to_parent_scopes_dict = {}

    def add_note(self, n: Note):
        """
        This is the only time Notes are sorted into special summary/event types.
        """
        # Add the note to its dict
        s = TimeScope(n.time_scope_id)

        # Note that summaries go into their _enclosing_ scope.
        # Except for quarters, which they don't have such a thing.
        if n.type == "summary":
            enclosing_scope = TimeScopeUtils.enclosing_scope(s)[0]
            self.scope_to_summaries_dict[enclosing_scope].append(n)
            self.add_scope(enclosing_scope)
        elif n.type == "event" or (n.type and n.type[0:7] == "event: "):
            self.scope_to_events_dict[s].append(n)
            self.add_scope(s)
        else:
            self.scope_to_notes_dict[s].append(n)
            self.add_scope(s)

    def add_scope(self, s: TimeScope):
        """
        Add the scope to its parents
        """
        enclosing_scope = TimeScopeUtils.enclosing_scope(s)[0]
        # If our parent is the same as us, ignore and move on
        if enclosing_scope == s:
            self.scope_to_parent_scopes_dict[s] = None
            return

        self.scope_to_parent_scopes_dict[s] = enclosing_scope
        self.add_scope(enclosing_scope)

    def report(self):
        def sort_and_attach(target_scope, target_dict):
            def note_sorter(n: Note):
                if not n.sort_time:
                    return TimeScope(n.time_scope_id).start

                return n.sort_time

            if target_scope in self.scope_to_summaries_dict:
                self.scope_to_summaries_dict[target_scope].sort(key=note_sorter)
                target_dict["summaries"] = self.scope_to_summaries_dict[target_scope]

            if target_scope in self.scope_to_events_dict:
                self.scope_to_events_dict[target_scope].sort(key=note_sorter)
                target_dict["events"] = self.scope_to_events_dict[target_scope]

            if target_scope in self.scope_to_notes_dict:
                self.scope_to_notes_dict[target_scope].sort(key=note_sorter)
                target_dict["notes"] = self.scope_to_notes_dict[target_scope]

        response_by_quarter = {}

        # Filter for anything on a _quarter_ scope
        for quarter_scope in [s for s in self.scope_to_parent_scopes_dict.keys() if s.type == TimeScope.Type.quarter]:
            response_by_quarter[quarter_scope] = {}
            sort_and_attach(quarter_scope, response_by_quarter[quarter_scope])

        # Filter for anything on a _week_ scope
        for week_scope, quarter_scope in [kv for kv in self.scope_to_parent_scopes_dict.items() if
                                          kv[0].type == TimeScope.Type.week]:
            if not "child_scopes" in response_by_quarter[quarter_scope]:
                response_by_quarter[quarter_scope]["child_scopes"] = {}

            response_by_quarter[quarter_scope]["child_scopes"][week_scope] = {}
            sort_and_attach(week_scope, response_by_quarter[quarter_scope]["child_scopes"][week_scope])

        # Filter for anything on a _day_ scope
        for day_scope, week_scope in [kv for kv in self.scope_to_parent_scopes_dict.items() if
                                      kv[0].type == TimeScope.Type.day]:
            quarter_scope = self.scope_to_parent_scopes_dict[week_scope]
            if not "child_scopes" in response_by_quarter[quarter_scope]["child_scopes"][week_scope]:
                response_by_quarter[quarter_scope]["child_scopes"][week_scope]["child_scopes"] = {}

            response_by_quarter[quarter_scope]["child_scopes"][week_scope]["child_scopes"][day_scope] = {}
            sort_and_attach(day_scope,
                            response_by_quarter[quarter_scope]["child_scopes"][week_scope]["child_scopes"][day_scope])

        return response_by_quarter

    def report_as_json(self):
        # return JSON directly
        def scope_notes_to_json(scopes_dict):
            """
            Return a new dict with the child elements mapped via Note.to_json()
            """
            json_dict = {}
            for scope, notes in scopes_dict.items():
                notes_as_json = {}
                for k, v in notes.items():
                    if k == "child_scopes":
                        notes_as_json[k] = scope_notes_to_json(v)
                    else:
                        notes_as_json[k] = [n.to_json() for n in v]

                json_dict[scope] = notes_as_json

            return json_dict

        return scope_notes_to_json(self.report())


def _report_notes_for(scope, domain):
    base_query = Note.query \
        .join(NoteDomain, Note.note_id == NoteDomain.note_id)

    if scope:
        scopes = [
            *TimeScopeUtils.enclosing_scope(scope, recurse=True),
            scope,
            *TimeScopeUtils.child_scopes(scope)
        ]
        base_query = base_query \
            .filter(Note.time_scope_id.in_(scopes))

    if domain:
        base_query = base_query \
            .filter(NoteDomain.domain_id.like(domain + "%"))

    fmt = NotesFormatter()
    for note in base_query.all():
        fmt.add_note(note)

    return fmt.report()


def _format_as_html(scope, domain, response_by_quarter):
    kwargs = {}

    def match_domains(n: Note) -> str:
        domains = filter(lambda x: x != domain, _list_domains(n.note_id))
        if not domains:
            return ""

        def domain_to_html(d):
            if scope:
                return f'<a href="/report-notes?scope={scope}&domain={d}">{d.replace(" ", "&nbsp;")}</a>'
            else:
                return f'<a href="/report-notes?domain={d}">{d.replace(" ", "&nbsp;")}</a>'

        domains = [domain_to_html(d) for d in domains]
        return ", ".join(domains)

    kwargs["match_domains"] = match_domains

    def week_lengthener(scope) -> str:
        if scope.type == TimeScope.Type.week:
            return scope.lengthen()
        else:
            return scope

    kwargs["week_lengthener"] = week_lengthener

    def desc_to_html(desc: str):
        # escape anything that makes the HTML weird
        desc = re.sub(r'<', r'&lt;', desc)
        # make newlines have effect
        desc = re.sub('\r\n', r'<br />', desc)
        desc = re.sub('\n', r'<br />', desc)
        # make markdown links clickable
        desc = re.sub(r'\[(.+?)]\((.+?)\)',
                      r"""[\1](<a href="\2">\2</a>)""",
                      desc)
        return desc

    kwargs["desc_to_html"] = desc_to_html

    def pretty_print_note(note: Note):
        as_json = report_one_note(note.note_id)
        as_json['note']['desc'] = '[truncated, see note_id link for details]'
        # tag domain strings so we can turn them into links
        clickable_domains = [f'domain: {d}' for d in as_json['domains']]
        as_json['domains'] = clickable_domains

        as_text = json.dumps(as_json, indent=4, ensure_ascii=False)
        # make note_ids clickable
        as_text = re.sub(r'"note_id": (\d*),',
                         r'<a href="/note/\1">"note_id": \1</a>,',
                         as_text)
        # make domains clickable
        if scope:
            as_text = re.sub(r'"domain: (.+)"',
                             f'<a href="/report-notes?scope={scope}&domain=\\1">"\\1"</a>',
                             as_text)
        else:
            as_text = re.sub(r'"domain: (.+)"',
                             r'<a href="/report-notes?domain=\1">"\1"</a>',
                             as_text)

        return as_text

    kwargs["pretty_print_note"] = pretty_print_note

    def shorten_sort_time(dt) -> str:
        return str(dt)[11:16]

    kwargs["shorten_sort_time"] = shorten_sort_time

    def safen(s: str) -> str:
        if not s:
            return s

        s = s.replace(": ", "-")
        s = s.replace(" ", "-")
        return s

    kwargs["safen"] = safen

    kwargs["doc_title"] = "[report-notes]"
    if scope:
        kwargs["doc_title"] = kwargs["doc_title"] + f" scope={scope}"
    if domain:
        kwargs["doc_title"] = kwargs["doc_title"] + f" domain={domain}"

    if scope:
        prev_scope = TimeScopeUtils.prev_scope(scope)
        if domain:
            kwargs["prev_scope"] = f'<a href="/report-notes?scope={prev_scope}&domain={domain}">{prev_scope}</a>'
        else:
            kwargs["prev_scope"] = f'<a href="/report-notes?scope={prev_scope}">{prev_scope}</a>'

        next_scope = TimeScopeUtils.next_scope(scope)
        if domain:
            kwargs["next_scope"] = f'<a href="/report-notes?scope={next_scope}&domain={domain}">{next_scope}</a>'
        else:
            kwargs["next_scope"] = f'<a href="/report-notes?scope={next_scope}">{next_scope}</a>'

    return render_template('note.html',
                           response_by_quarter=response_by_quarter,
                           **kwargs)
