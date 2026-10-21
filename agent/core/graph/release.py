"""Explicit release allowlist: a generated candidate is never an active dataset."""
RELEASED_VERSIONS = frozenset({'legacy', 'kg_v1', 'kg_v2'})


def require_released_version(version):
    if version not in RELEASED_VERSIONS:
        raise ValueError('图谱候选版本尚未发布，不能启用或用于推理：' + str(version))
