"""多智能体系统的工作流编排。"""

from .state import AgentOutput, AgentState

def __getattr__(name):
    if name!='AgentGraphManager':raise AttributeError(name)
    from .graph_manager import AgentGraphManager
    return AgentGraphManager

__all__ = ["AgentOutput", "AgentState", "AgentGraphManager"]
