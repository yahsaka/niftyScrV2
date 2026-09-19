from dataclasses import dataclass
from src.config import ExecutionConfig, StrategyConfig


@dataclass
class Context:
    workspace: dict
    store: object
    snapshot: dict
    registry: object
    signals: list
    dark: bool

    @property
    def strategy(self):
        return StrategyConfig(**self.workspace["strategy"])

    @property
    def execution(self):
        return ExecutionConfig(**self.workspace["execution"])

    def save(self, **changes):
        workspace = {**self.workspace, **changes}
        self.workspace = self.store.save(workspace)
        return self.workspace
