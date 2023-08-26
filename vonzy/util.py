import jinja2
import typing

from .datatype import AttrDict
from vonzy.logger import log

if typing.TYPE_CHECKING:
    from .schema import StepContext

def render_step_context(template: str, context: 'StepContext') -> str:
    try:
        if template.startswith("{{") and template.endswith("}}"):
            rv = jinja2.Template(template).render(context)
        else:
            # use built-in str.format instead of string.Template.
            # By default python's str.format supports attribute fetching styles (aka, `getattr`) eg `obj.attr`.
            # While string.Template is not #cmiiw.
            # see: https://peps.python.org/pep-3101/#simple-and-compound-field-names
            kwargs = {
                "env": context.env,
                "inputs": context.inputs,
                "steps": context.steps
            }
            rv = template.format(**AttrDict(kwargs))
    except Exception as e:
        log.error(f"Error rendering template {template!r}: {e}")
        log.debug(f"context: {context}")
        raise

    return rv