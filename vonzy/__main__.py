from typer import Typer, Option, Context, FileText
from rich import print
from typing import Optional
from yaml import safe_load
from .schema import Workflow
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
        config = safe_load(config)
        workflow = Workflow(**config)
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
