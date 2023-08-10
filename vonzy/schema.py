import logging
import os
from pydantic import BaseModel, Field, PrivateAttr, validator
from typing import Literal, Optional, Callable, Any, Union
from enum import Enum
from .errors import InvalidStep, MissingDependency, InvalidAction
from jinja2 import Template
from ast import literal_eval
from importlib import import_module
from .actions.base import BaseAction
from inquirer import Text, Password, List, Checkbox, prompt
from inquirer.questions import Question
from .constants import BASE_RULE_JINJA_TEMPLATE
from . import actions
from addict import Dict
from .logger import log

import string

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from pydantic import EmailStr
except ImportError:
    EmailStr = None

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
        fn = str
        if self.type in (self.Types.checkbox, self.Types.list):
            fn = None
        elif self.type == self.Types.email:
            if EmailStr is None:
                raise MissingDependency("email-validator")
            fn = EmailStr
        elif self.type == self.Types.number:
            fn = int
        
        def validator(_, current: Any) -> bool:
            try:
                fn(current)
            except Exception as e:
                return False
            return True
        
        if fn:
            return validator
        
    def get_real_value(self) -> str:
        v = self.value
        if v is None:
            v = self.default
        
        return self.value

    def get_widget(self) -> Question:
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
            widget_params["choices"] = self.choices
        
        if not valid_type:
            raise InvalidAction(f"Unknown input type {self.type!r}")
        
        return widget_obj(**widget_params)

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
    commands: list[Union[str, dict, CommandRule]] = Field(default_factory=list)
    steps: list['Step'] = Field(default_factory=list)

    def load_action(self) -> Action:
        use_action = self.use
        if isinstance(use_action, str):
            use_action = Action(name=use_action)
        
        log.info(f"Loading action {use_action.name!r}")
        try:
            action_name = use_action.name.lstrip(".")
            action_class = actions.__cached_actions__.get(action_name)
            if not action_class:
                action_module = import_module(action_name)
                action_class = getattr(action_module, use_action.klass, None)
                if action_class is None:
                    raise InvalidAction(f"Action object not found in {action_name!r}")
                else:
                    actions.__cached_actions__[action_name] = action_class
            
            log.info(f"Action {action_name!r} loaded")
            action_params = use_action.params or {}
            log.debug(f"Initializing action {action_name!r} with params {action_params}")
            action_instance = action_class(**action_params)
            log.debug(f"Action {action_name!r} initialized")
            use_action._instance = action_instance
            return use_action

        except ImportError:
            raise InvalidAction(f"Action {action_name!r} not found")
    
    def _validate_rule(self, expr: str, sc: 'StepContext') -> bool:
        rule_expr = string.Template(BASE_RULE_JINJA_TEMPLATE).substitute(expr=expr)
        result = Template(rule_expr).render(sc)
        rv = literal_eval(result)
        return rv
    
    def run(self, sc: 'StepContext', *, parent_step_ids: Optional[list[str]] = None):
        step_id = self.id
        steps_ctx = sc.steps
        if not isinstance(steps_ctx, Dict):
            steps_ctx = Dict()
            sc.steps = steps_ctx

        sc.steps = steps_ctx
        _current_step_data: Optional[Dict] = None
        if parent_step_ids:
            for sid in parent_step_ids:
                if _current_step_data:
                    _current_step_data = _current_step_data.get(sid)
                else:
                    _current_step_data: Dict = steps_ctx.get(sid)
                
                if _current_step_data is None:
                    raise InvalidStep(f"Step {sid!r} not found -> {parent_step_ids}")
    
        if not _current_step_data:
            _current_step_data = steps_ctx
    
        log.info(f"Running step {self.id!r} with context {sc.ctx}")
        log.debug(f"StepContext {sc}")
        result_class = StepResult
        if self.rule:
            if not self._validate_rule(self.rule, sc):
                log.info(f"Step {self.id!r} skipped")
                result = result_class(step=self, status="skipped", value=None)
                _current_step_data[step_id] = {"result": result}
                yield result
        
        action_obj = self.load_action()
        result = None
        try:
            action_obj._instance.initialize()
            for cmd in self.commands:
                if isinstance(cmd, CommandRule):
                    log.debug(f"Command rule {cmd.rule!r} detected. Executing...")
                    if not self._validate_rule(cmd.rule, sc):
                        log.debug(f"Command {cmd.cmd!r} skipped.")
                        continue
                    cmd = cmd.cmd
                
                kwargs = {}
                args = ()
                if isinstance(cmd, dict):
                    kwargs.update(cmd)
                else:
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
                log.error(f"Error cleaning up action {action_obj.name!r} on step {self.id!r}: {e}")
                result = result_class(step=self, status="error", value=e)
        
        _R = result.dict(exclude={'step'})
        log.info(f"Step {self.id!r} finished with result {_R}")
        _current_step_data[step_id] = {"result": result}
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
    ctx: Dict
    steps: Optional[Dict[str, StepResult]]

class Workflow(BaseModel):
    name: str
    log_level: str = "NOTSET"
    env_file: Optional[Union[str, list[str]]] = None
    inputs: list[Input]
    steps: list[Step]

    __context__: Dict = PrivateAttr(Dict())
 
    @validator("log_level")
    def _validate_and_set_log_level(cls, v: str):
        v = v.upper()
        if v not in logging._nameToLevel:
            raise ValueError(f"Invalid log level {v!r}")
        log.setLevel(v)
        return v
 
    def before_run(self):
        prompts: list[Question] = []
        for input in self.inputs:
            widget = input.get_widget()
            prompts.append(widget)
        
        values = prompt(prompts, raise_keyboard_interrupt=True)
        self.__context__.update(values)

    def load_env_file(self):
        if load_dotenv and self.env_file:
            env_file = self.env_file
            if not isinstance(env_file, list):
                env_file = [env_file]
            
            for f in env_file:
                load_dotenv(f)
            
        self.__context__.update(os.environ)

    def run(self):
        self.load_env_file()
        try:
            self.before_run()
            ctx = StepContext(
                ctx=self.__context__
            )
            for step in self.steps:
                for result in step.run(ctx):
                    yield result
        except KeyboardInterrupt as e:
            log.info("Cancelled by user.")
        except Exception as e:
            log.error(f"Error: {e}")

        yield
