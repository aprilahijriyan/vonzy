import functools
import typing

from click import Context as ClickContext
from rich import print, tree
from typer import Context, FileText, Option, Typer

from .schema import Step, Workflow

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

app = Typer(
    name="vonzy",
    help="Simple task runner for automation 😎",
    no_args_is_help=True,
)


def required_workflow(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        ctx: ClickContext = None
        for value in kwargs.values():
            if isinstance(value, ClickContext):
                ctx = value
                break
        if isinstance(ctx, ClickContext):
            workflow = ctx.obj
            if not isinstance(workflow, Workflow):
                print(
                    f"Error: no workflow found. use 'vonzy -c ...' option to load workflow file."
                )
                ctx.abort()
        return fn(*args, **kwargs)

    return wrapper


@app.callback(invoke_without_command=True)
def main(
    ctx: Context,
    config: FileText = Option(None, "-c", "--config", help="Configuration file"),
):
    if not config:
        return

    try:
        workflow = Workflow.parse_config(config)
        ctx.obj = workflow
    except Exception as e:
        print("Error:", e)
        ctx.abort()


@app.command()
@required_workflow
def run(
    ctx: Context,
    step_ids: typing.Optional[list[str]] = Option(
        None,
        "-s",
        "--step",
        help="Step IDs to run",
    ),
    env_file: typing.Optional[list[str]] = Option(
        None,
        "-e",
        "--env",
        help="Environment variables file (dotenv format)",
    ),
):
    """
    Run workflow
    """

    if load_dotenv is None and env_file:
        print(
            f"Error: you used the '-e' option but you haven't installed the python-dotenv module."
        )
        ctx.abort()

    for f in env_file:
        load_dotenv(f, override=True)

    workflow: Workflow = ctx.obj
    list(workflow.run(step_ids=step_ids))


@app.command()
@required_workflow
def steps(
    ctx: Context,
):
    """
    Show workflow steps
    """

    workflow: Workflow = ctx.obj
    comp = tree.Tree(f"List of steps in the {workflow.name!r} workflow")

    def _add_to_root(tr: tree.Tree, label: str, children: list[Step]):
        r = tr.add(label)
        for c in children:
            _add_to_root(r, c.name, c.steps)

    have_steps = len(workflow.steps) > 0
    for step in workflow.steps:
        if step.steps:
            _add_to_root(comp, step.name, step.steps)
        else:
            comp.add(step.name)

    if have_steps:
        print(comp)
    else:
        print(f"0 steps found in {workflow._source_file!r}")
