"""Resolve one immutable knowledge binding per turn; ContextVar is task/thread local."""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import RLock
from functools import lru_cache
import hashlib
from .audit import ROOT,digest
from .snapshot_repository import SnapshotRepository

_current=ContextVar('knowledge_binding',default=None)
_bindings=OrderedDict()
_lock=RLock()

@lru_cache(maxsize=1)
def answer_policy_fingerprint():
    """Restarting after a prompt/reference fix must not revive pre-fix cached answers."""
    paths=('agent/agents/diagnosis_agent.py','agent/agents/treatment_agent.py',
           'agent/agents/orchestrator.py','agent/agents/drug_review_agent.py',
           'agent/core/graph/evidence_report.py','agent/core/clinical_reference.py','agent/core/clinical_consistency.py',
           'agent/tools/vector_tool.py','agent/tools/synonym_tool.py',
           'app/service/chat_service.py',
           'agent/config/symptom_synonyms.json','mock_data/icd11_anxiety.md')
    return hashlib.sha256(b''.join((ROOT/path).read_bytes() for path in paths)).hexdigest()[:16]

@dataclass(frozen=True)
class KnowledgeBinding:
    version:str
    name:str
    checksum:str
    repository:object

    @property
    def identity(self):return 'runtime-v8-'+answer_policy_fingerprint()+':'+self.version+':'+self.checksum

    def metadata(self):return dict(version=self.version,name=self.name,checksum=self.checksum,identity=self.identity)

def _remember(binding):
    with _lock:
        _bindings[binding.identity]=binding;_bindings.move_to_end(binding.identity)
        while len(_bindings)>128:_bindings.popitem(last=False)
    return binding

def resolve_binding():
    from .project_workbench import workbench
    release=workbench.selected_release()
    if release:
        repository=SnapshotRepository(release)
        return _remember(KnowledgeBinding(repository.version,repository.label,repository.sha256,repository))
    from .repository import GraphRepository
    repository=GraphRepository()
    from .release import require_released_version
    require_released_version(repository.version)
    folder=ROOT/'mock_data'/repository.version
    checksum=digest({p.name:p.read_text(encoding='utf-8-sig') for p in sorted(folder.glob('*.json'))})
    return _remember(KnowledgeBinding(repository.version,repository.version,checksum,repository))

def binding_from_metadata(metadata):
    identity=metadata['identity']
    with _lock:binding=_bindings.get(identity)
    if binding is not None:
        if binding.metadata()!=metadata:raise ValueError('Knowledge binding metadata mismatch')
        return binding
    # A restored checkpoint must resolve the specified release, never the latest pointer.
    if metadata['version'].startswith('project-'):
        from .project_workbench import workbench
        repository=SnapshotRepository(workbench.published_release(metadata['version']))
    else:
        from .repository import GraphRepository
        repository=GraphRepository(metadata['version'])
    binding=KnowledgeBinding(metadata['version'],metadata['name'],metadata['checksum'],repository)
    if binding.identity!=identity:raise ValueError('Knowledge binding identity mismatch')
    if getattr(repository,'is_snapshot',False) and repository.sha256!=binding.checksum:raise ValueError('Pinned release changed')
    return _remember(binding)

@contextmanager
def use_binding(binding):
    token=_current.set(binding)
    try:yield binding
    finally:_current.reset(token)

def current_binding():return _current.get()

def current_repository():
    return (current_binding() or resolve_binding()).repository

def knowledge_prompt():
    binding=current_binding()
    if binding is None:return ''
    return ('\n内部检索上下文：当前图谱版本为'+binding.name+'（'+binding.version+'）。图谱工具已固定至此版本。'
        '逐条保留返回记录的适用条件、来源地区、人群、制剂、数值方向和不确定性。'
        '未找到记录时说明覆盖不足，不得把旧对话或模型常识当作该版本的检索证据。'
        '其他文献检索工具是独立资料来源，应与图谱记录分别标明，不宣称它们属于该图谱版本。\n')
