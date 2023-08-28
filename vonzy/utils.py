import typing

import jinja2

from vonzy.logger import log

from .datatype import AttrDict

if typing.TYPE_CHECKING:
    from .schema import StepContext


def render_step_context(template: str, context: "StepContext") -> str:
    try:
        if template.startswith("{{") and template.endswith("}}"):
            rv = jinja2.Template(template).render(context.to_context())
        else:
            # use built-in str.format instead of string.Template.
            # By default python's str.format supports attribute fetching styles (aka, `getattr`) eg `obj.attr`.
            # While string.Template is not #cmiiw.
            # see: https://peps.python.org/pep-3101/#simple-and-compound-field-names
            kwargs = context.to_context()
            rv = template.format(**AttrDict(kwargs))
    except Exception as e:
        log.error(f"Error rendering template {template!r}: {e}")
        log.debug(f"Step context: {context}")
        raise

    return rv
