import logging
import os
import string
from ast import literal_eval
from enum import Enum
from importlib import import_module
from io import BufferedReader
from typing import Any, Callable, Literal, Optional, Type, TypeVar, Union

import oyaml as yaml
from inquirer import Checkbox, List, Password, Text, prompt
from inquirer.questions import Question
from jinja2 import Template
from pydantic import BaseModel, Field, PrivateAttr, validator

from . import actions
from .actions.base import BaseAction
from .constants import BASE_RULE_JINJA_TEMPLATE
from .datatype import AttrDict
from .errors import InvalidAction, InvalidStep, MissingDependency
from .logger import log
from .utils import render_step_context

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]

try:
    from pydantic import EmailStr
except ImportError:
    EmailStr = None  # type: ignore[assignment, misc]

T = TypeVar("T")


class Input(BaseModel):
    class Types(str, Enum):
        text = "text"
        email = "email"
        password = "password"
        number = "number"
        list = "list"
        checkbox = "checkbox"

    key: str
    value: Optional[str]
    type: Types
    required: Optional[bool]
    default: Optional[str]
    choices: list[str] = Field(default_factory=list)
    description: str

    def get_value_validator(self) -> Optional[Callable[[str], Any]]:
        fn: Optional[Callable[[str], Any]] = str
        if self.type in (self.Types.checkbox, self.Types.list):
            fn = None  # type: ignore[assignment]
        elif self.type == self.Types.email:
            if EmailStr is None:
                raise MissingDependency("email-validator")
            fn = EmailStr
        elif self.type == self.Types.number:
            fn = int

        def validator(_, current: Any) -> bool:
            try:
                fn(current)
            except Exception:
                return False
            return True

        if fn:
            return validator

    def get_real_value(self) -> Optional[str]:
        v = self.value
        if v is None:
            v = self.default
        return v

    def get_widget(self) -> tuple[Type[Question], dict]:
        widget_obj = Text
        widget_params = {
            "name": self.key,
            "message": self.description,
            "default": self.get_real_value(),
            "ignore": lambda x: False if self.required else None,
            "validate": self.get_value_validator(),
        }
        valid_type = False
        if self.type in (self.Types.text, self.Types.email, self.Types.number):
            valid_type = True
        elif self.type == self.Types.password:
            valid_type = True
            widget_obj = Password
        elif self.type in (self.Types.list, self.Types.checkbox):
            valid_type = True
            widget_obj = Checkbox if self.type == self.Types.checkbox else List
            widget_params.pop("validate")
            widget_params["choices"] = self.choices

        if not valid_type:
            raise InvalidAction(f"Unknown input type {self.type!r}")

        return widget_obj, widget_params


class Action(BaseModel):
    name: str
    params: Optional[dict] = Field(default_factory=dict)
    klass: Optional[str] = Field("Action")
    _instance: Optional[BaseAction] = PrivateAttr(None)


class CommandRule(BaseModel):
    rule: str
    cmd: Union[str, dict]


class Step(BaseModel):
    id: str
    name: str
    use: Union[Action, str]
    rule: Optional[str]
    commands: list[Union[str, CommandRule]] = Field(default_factory=list)
    steps: list["Step"] = Field(default_factory=list)

    @validator("id", always=True)
    def validate_id(cls, v: str):
        if v == "result":
            raise InvalidStep(
                f"The step cannot have id='result' as this will be used to store the result of the step."
            )
        return v

    def load_action(self, sc: "StepContext") -> Action:
        use_action = self.use
        if isinstance(use_action, str):
            use_action = Action(name=use_action)

        log.info(f"Loading action {use_action.name!r}")
        try:
            action_name = use_action.name.lstrip(".")
            action_class = actions.__cached_actions__.get(action_name)
            if not action_class:
                action_module = import_module(action_name)
                action_class: Optional[BaseAction] = getattr(
                    action_module, use_action.klass, None
                )
                if action_class is None:
                    raise InvalidAction(f"Action object not found in {action_name!r}")
                else:
                    actions.__cached_actions__[action_name] = action_class

            log.info(f"Action {action_name!r} loaded")
            action_params = {}
            for k, v in (use_action.params or {}).items():
                if isinstance(v, str):
                    v = render_step_context(v, context=sc)
                if isinstance(v, list):
                    nv = []
                    for vv in v:
                        if isinstance(vv, str):
                            vv = render_step_context(vv, context=sc)
                        nv.append(vv)
                    v = nv
                action_params[k] = v

            action_instance = action_class(**action_params)
            log.debug(f"Action {action_instance} initialized")
            use_action._instance = action_instance
            return use_action

        except ImportError:
            raise InvalidAction(f"Action {action_name!r} not found")

    def _validate_rule(self, expr: str, sc: "StepContext") -> bool:
        rule_expr = string.Template(BASE_RULE_JINJA_TEMPLATE).substitute(expr=expr)
        result = Template(rule_expr).render(sc.to_context())
        rv = literal_eval(result)
        return rv

    def run(self, sc: "StepContext", *, parent_step_ids: Optional[list[str]] = None):
        step_id = self.id
        steps_ctx = sc.steps
        if not isinstance(steps_ctx, AttrDict):
            steps_ctx = AttrDict()
            sc.steps = steps_ctx

        sc.steps = steps_ctx
        _current_step_data: Optional[AttrDict] = None
        if parent_step_ids:
            for sid in parent_step_ids:
                if _current_step_data:
                    _current_step_data = _current_step_data.get(sid)
                else:
                    _current_step_data = steps_ctx.get(sid)

                if _current_step_data is None:
                    raise InvalidStep(f"Step {sid!r} not found -> {parent_step_ids}")

        if not _current_step_data:
            _current_step_data = steps_ctx

        realname = render_step_context(self.name, context=sc)
        self.name = realname
        log.info(f"Running step {self.name!r} #{step_id}")
        result_class = StepResult
        if self.rule:
            rule_passed = self._validate_rule(self.rule, sc)
            if not rule_passed:
                log.info(f"Step {self.id!r} skipped")
                result = result_class(step=self, status="skipped", value=None)
                _current_step_data[step_id] = AttrDict(result=result)
                yield result
                return

        action_obj = self.load_action(sc)
        result = None
        try:
            action_obj._instance.initialize()
            commands = action_obj._instance.handle_commands(self.commands, context=sc)
            for cmd in commands:
                if isinstance(cmd, CommandRule):
                    if not self._validate_rule(cmd.rule, sc):
                        log.debug(f"Command {cmd.cmd!r} skipped.")
                        continue
                    cmd = cmd.cmd

                kwargs = {}
                args = (cmd,)
                kwargs["context"] = sc
                action_obj._instance.execute(*args, **kwargs)
            result = result_class(step=self, status="success", value=None)
        except Exception as e:
            result = result_class(step=self, status="error", value=e)
        finally:
            try:
                action_obj._instance.cleanup()
            except Exception as e:
                log.error(
                    f"Error cleaning up action {action_obj.name!r} on step {self.id!r}: {e}"
                )
                result = result_class(step=self, status="error", value=e)

        _R = result.dict(exclude={"step"})
        log.info(f"Step {self.id!r} finished with status={_R['status']}")
        log.debug(f"Result {_R} for step {self.id!r}")
        _current_step_data[step_id] = AttrDict(result=result)
        yield result
        for child_step in self.steps:
            if parent_step_ids is None:
                parent_step_ids = [self.id]
            else:
                parent_step_ids.append(self.id)

            for child_result in child_step.run(sc, parent_step_ids=parent_step_ids):
                yield child_result


class StepResult(BaseModel):
    step: Step
    status: Literal["success", "error", "skipped"]
    value: Optional[Any]


class StepContext(BaseModel):
    env: AttrDict
    inputs: Optional[AttrDict]
    steps: Optional[AttrDict[str, StepResult]]

    def to_context(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "inputs": self.inputs,
            "steps": self.steps,
        }


class Workflow(BaseModel):
    name: str
    log_level: str = "NOTSET"
    env_file: Optional[Union[str, list[str]]] = None
    inputs: list[Input] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)

    _source_file: Optional[str] = PrivateAttr(None)

    @validator("log_level")
    def _validate_and_set_log_level(cls, v: str):
        v = v.upper()
        if v not in logging._nameToLevel:
            raise ValueError(f"Invalid log level {v!r}")
        log.setLevel(v)
        return v

    def before_run(self, sc: StepContext):
        questions: list[Question] = []
        for input in self.inputs:
            widget_class, widget_params = input.get_widget()
            default = widget_params["default"]
            if isinstance(default, str):
                default = render_step_context(default, context=sc)

            widget_params["default"] = default
            widget = widget_class(**widget_params)
            questions.append(widget)

        values = prompt(questions, raise_keyboard_interrupt=True)
        return values

    def load_env_file(self):
        if load_dotenv is not None and self.env_file:
            env_file = self.env_file
            if not isinstance(env_file, list):
                env_file = [env_file]

            for f in env_file:
                load_dotenv(f)

    @classmethod
    def parse_config(cls, config: BufferedReader):
        data = yaml.safe_load(config)
        instance = cls(**data)
        instance._source_file = config.name
        return instance

    @classmethod
    def load_config(cls, src: str):
        with open(src, "rb") as f:
            return cls.parse_config(f)

    def run(self, step_ids: Optional[list[str]] = None):
        self.load_env_file()
        try:
            ctx = StepContext(
                env=AttrDict(**os.environ),
            )
            inputs_ctx = self.before_run(ctx)
            if inputs_ctx:
                ctx.inputs = inputs_ctx

            ctx.steps = AttrDict()
            have_steps_ids = isinstance(step_ids, list)
            for step in self.steps:
                if have_steps_ids and step.id not in step_ids:
                    ctx.steps[step.id] = AttrDict(
                        result=StepResult(step=step, status="skipped", value=None)
                    )
                    continue
                for result in step.run(ctx):
                    yield result
        except KeyboardInterrupt:
            log.info("Cancelled by user.")
        except Exception as e:
            log.error(f"Error: {e}", exc_info=True)

        yield
