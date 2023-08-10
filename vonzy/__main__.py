from typer import Typer, Option, Context, FileText
from rich import print, tree
from typing import Optional
from .schema import Workflow, Step
from pathlib import Path

app = Typer(
    name="vonzy",
    help="A beautiful task runner for your projects 😎",
    no_args_is_help=True
)

@app.callback(invoke_without_command=True)
def main(
    ctx: Context,
    config: Optional[FileText] = Option(Path.cwd() / "vonzy.yml", "-c", "--config", help="Configuration file"),
):
    if not config:
        print("No config file found")
        ctx.abort()
    
    try:
        workflow = Workflow.parse_config(config)
        ctx.obj = workflow
    except Exception as e:
        print("Error:", e)

@app.command()
def run(
    ctx: Context,
):
    """
    Run workflow
    """
    
    workflow: Workflow = ctx.obj
    list(workflow.run())

@app.command()
def steps(
    ctx: Context,
):
    """
    Show workflow steps
    """
    
    workflow: Workflow = ctx.obj
    comp = tree.Tree(f"List of steps of the {workflow.name!r} workflow")
    def _add_to_root(tr: tree.Tree, label: str, children: list[Step]):
        r = tr.add(label)
        for c in children:
            _add_to_root(r, c.name, c.steps)

    have_steps = True
    for step in workflow.steps:
        if step.steps:
            _add_to_root(comp, step.name, step.steps)
        else:
            comp.add(step.name)
    else:
        have_steps = False
        print(f"0 steps found in {workflow._source_file!r}")
    
    if have_steps:
        print(comp)