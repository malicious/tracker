from flask import render_template
from markupsafe import Markup
from sqlalchemy import select, func

from .render_utils import _domain_to_html_link
from ..models import NoteDomain, Note
from ..time_scope import TimeScope


def stats(session):
    """
    Build and return statistics for every matching NoteDomain

    - how many notes are tied to that domain
    - (maybe) how many notes are _uniquely_ that domain
    - latest time_scope_id for that note (alphabetical sorting is fine)

    Response JSON format:

    ```
    {
      "account: credit card": {
        "latest_time_scope_id": "2021-ww32.2",
        "note_count": 26
      },
      "type: summary": {
        "latest_time_scope_id": "2009-ww09.1",
        "note_count": 3746
      }
    }
    ```
    """
    response_json = {}

    for nd in session.query(NoteDomain.domain_id).distinct():
        response_json[nd.domain_id] = {
            "latest": Note.query
                .join(NoteDomain, NoteDomain.note_id == Note.note_id)
                .filter(NoteDomain.domain_id == nd.domain_id)
                .order_by(Note.time_scope_id.desc())
                .limit(1)
                .one().time_scope_id,
            "count": NoteDomain.query
                .filter_by(domain_id=nd.domain_id)
                .count()
        }

    return response_json


def render_stats(
        session,
        query_limiter,
):
    """
    Build and return human-readable page that lists domains + their info
    """
    # @dataclass
    class DomainInfo:
        domain_id: str
        domain_id_link: str

        earliest: TimeScope
        latest: TimeScope

        count: int
        count_str: str

    def render_domains(
            max_notes_cutoff: int = 100,
    ):
        query = query_limiter(
            select(
                NoteDomain.domain_id,
                func.min(Note.time_scope_id),
                func.max(Note.time_scope_id),
                func.max(Note.sort_time),
                func.count(Note.note_id),
            )
            .join(NoteDomain, NoteDomain.note_id == Note.note_id)
            # Filter out any time_scope_ids that contain an emdash, since they mess up the ordering dramatically
            .filter(func.not_(Note.time_scope_id.contains('—')))
            .group_by(NoteDomain.domain_id)
            .order_by(
                func.max(Note.time_scope_id).desc(),
                func.max(Note.sort_time).desc())
        )

        rows = session.execute(query).all()
        for row in rows:
            info = DomainInfo()

            info.earliest = TimeScope(row[1])
            info.latest = TimeScope(row[2])

            info.domain_id = row[0]
            info.domain_id_link = Markup(_domain_to_html_link(info.domain_id, (), None))

            info.latest = info.latest.minimize_vs(info.earliest)

            info.count = row[4]
            info.count_str = f"{info.count:_}"

            # If there's too many notes, limit it to the latest quarter scope
            if info.count > max_notes_cutoff:
                target_scope = info.latest
                while target_scope.get_parent():
                    target_scope = target_scope.get_parent()

                info.domain_id_link = Markup(_domain_to_html_link(
                    info.domain_id,
                    (target_scope,),
                    None,
                ))

            yield info

    return render_template(
        'notes/domains.html',
        domains_generator=render_domains(),
    )
