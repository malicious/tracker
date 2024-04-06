import functools
import hashlib
from typing import Tuple

from flask import current_app
from markupsafe import escape

max_cache_size = 25_000
"""
This is based on the number of notes in a query,
where the query takes like 10+ seconds to render.
"""


@functools.lru_cache(maxsize=max_cache_size)
def _domain_hue(d: str) -> str:
    domain_hash = hashlib.sha256(d.encode('utf-8')).hexdigest()
    domain_hash_int = int(domain_hash[0:4], 16)

    color_h = (domain_hash_int % 12) * (256.0 / 12)
    return f"{color_h:.2f}"


@functools.lru_cache(maxsize=max_cache_size)
def domain_to_css_color(d: str) -> str:
    """
    Map the domain string to a visually-distinct CSS color.

    Current implementation hashes the domain string, then takes the first 4
    characters as a base-16 number, which is then mapped to one of 8 final HSL
    colors.

    TODO: We could probably do with more than equally-spaced "hue" values
    """
    return f"color: hsl({_domain_hue(d)}, 80%, 40%);"


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


def cache(key, generate_fn):
    print(f"cache: key={key}")

    if not hasattr(current_app, 'cache_dict'):
        current_app.cache_dict = {}

    if key not in current_app.cache_dict:
        current_app.cache_dict[key] = generate_fn()

    return current_app.cache_dict[key]


def render_cache(func):
    def caching_wrapper(*args, **kwargs):
        return cache(
            key=(func.__name__, args, str(kwargs)),
            generate_fn=lambda: func(*args, **kwargs))

    return caching_wrapper


def render_cache_generator(*args, **kwargs):
    """
    NB All output from the original function is stored in a list!
    """
    def decorate2(func):
        cache_keys = (args, str(kwargs))
        def special_wrapper(*args, **kwargs):
            return cache(
                key=(cache_keys, args, str(kwargs)),
                generate_fn=lambda: list(func(*args, **kwargs)))

        return special_wrapper

    return decorate2
