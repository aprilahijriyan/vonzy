import typing
from pathlib import Path

from rich import print, tree
from typer import Context, FileText, Option, Typer

from .schema import Step, Workflow

app = Typer(
    name="vonzy",
    help="Simple task runner for automation 😎",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: Context,
    config: FileText = Option(
        Path.cwd() / "vonzy.yml", "-c", "--config", help="Configuration file"
    ),
):
    if not config:
        print("No config file found")
        ctx.abort()

    try:
        workflow = Workflow.parse_config(config)
        ctx.obj = workflow
    except Exception as e:
        print("Error:", e)
        ctx.abort()


@app.command()
def run(
    ctx: Context,
    step_ids: typing.Optional[list[str]] = Option(
        None,
        "-s",
        "--step",
        help="Step IDs to run",
    ),
):
    """
    Run workflow
    """

    workflow: Workflow = ctx.obj
    list(workflow.run(step_ids=step_ids))


@app.command()
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
