import functools
from typing import Tuple

from markupsafe import escape

from notes_v2.report import domain_to_css_color

max_cache_size = 25_000
"""
This is based on the number of notes in a query,
where the query takes like 10+ seconds to render.
"""


@functools.lru_cache(maxsize=max_cache_size)
def _domain_to_html_link(
        domain_id: str,
        scope_ids: Tuple[str],
        single_page: bool,
) -> str:
    escaped_domain = domain_id.replace('+', '%2B')
    escaped_domain = escape(escaped_domain)
    escaped_domain = escaped_domain.replace(' ', '+')
    escaped_domain = escaped_domain.replace('&', '%26')

    return f'''<a href="/notes?domain={escaped_domain}{
        ''.join([f'&scope={scope_id}' for scope_id in scope_ids])
    }{
        "&single_page=true" if single_page else ""
    }" style="{domain_to_css_color(domain_id)}">{domain_id}</a>'''
