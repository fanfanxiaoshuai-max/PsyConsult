"""Source applicability and retrieval regressions, independent of live model services."""
import json
import shutil
import pytest


def test_every_registered_source_has_a_scope_check_without_clinical_approval():
    from core.public_support import sections
    rows = sections()
    sources = {s['id']: s for r in rows for s in r['sources']}
    assert len(rows) == 56 and len(sources) == 16
    assert all(s['checked_date'] and s['scope_limit'] and s['evidence_role'] for s in sources.values())
    assert all(s['clinical_approval'] is False for s in sources.values())
    assert all(r['review_status'] == 'draft_for_internal_testing' for r in rows)


@pytest.mark.parametrize('question', ['忘记服药后可以加倍吗？', '处方药和酒能一起用吗？', '我想自行停药'])
def test_portal_is_never_used_as_drug_fact_evidence(question):
    from core.public_support import retrieve
    rows = retrieve(question, k=10)
    assert rows
    assert all(s['evidence_role'] != 'portal_navigation' for r in rows for s in r['sources'])
    assert all(r['section'] not in {'知识库维护要求', '工程要求'} for r in rows)


def test_portal_remains_available_for_explicit_navigation_only():
    from core.public_support import retrieve
    sources = [s for r in retrieve('去哪里查询药品的正式说明书？') for s in r['sources']]
    portal = next(s for s in sources if s['id'] == 'NMPA_OFFICIAL_PORTAL')
    assert portal['evidence_role'] == 'portal_navigation'
    assert portal['status'] == 'fetch_blocked_navigation_only'


def test_source_audit_cannot_silently_follow_a_changed_registry_url(tmp_path, monkeypatch):
    from core import public_support
    shutil.copytree(public_support.KB, tmp_path/'kb')
    path = tmp_path/'kb/source_audit.json'
    audit = json.loads(path.read_text(encoding='utf-8'))
    audit['sources']['NIMH_MEDICATIONS']['url'] = 'https://example.org/unreviewed'
    path.write_text(json.dumps(audit), encoding='utf-8')
    monkeypatch.setattr(public_support, 'KB', tmp_path/'kb')
    with pytest.raises(ValueError, match='URL does not match'):
        public_support.sections()


def test_source_summary_override_rejects_modified_original(tmp_path, monkeypatch):
    from core import public_support
    shutil.copytree(public_support.KB, tmp_path/'kb')
    path = tmp_path/'kb/community_mental_health/10_精神科药物安全教育.md'
    path.write_text(path.read_text(encoding='utf-8').replace('**忘记服药怎么办？**', '**漏服后如何处理？**'), encoding='utf-8')
    monkeypatch.setattr(public_support, 'KB', tmp_path/'kb')
    with pytest.raises(ValueError, match='override source changed'):
        public_support.sections()


def test_unknown_unmapped_section_fails_closed(tmp_path, monkeypatch):
    from core import public_support
    shutil.copytree(public_support.KB, tmp_path/'kb')
    path = tmp_path/'kb/community_mental_health/10_精神科药物安全教育.md'
    path.write_text(path.read_text(encoding='utf-8')+'\n## 未审核新章节\n尚无来源的说法。\n', encoding='utf-8')
    monkeypatch.setattr(public_support, 'KB', tmp_path/'kb')
    with pytest.raises(ValueError, match='Unmapped'):
        public_support.sections()


def test_normalized_scales_and_unrelated_queries():
    from core.public_support import retrieve
    for query, expected in [('PHQ 9', 'PHQ9_KROENKE_2001'), ('GAD－7', 'GAD7_SPITZER_2006')]:
        assert expected in {s['id'] for r in retrieve(query) for s in r['sources']}
    assert retrieve('天气预报与股票行情') == []
    assert retrieve('') == [] and retrieve('睡眠', 0) == []


def test_scoped_summary_exposes_missing_product_evidence():
    from core.public_support import sections
    row = next(r for r in sections() if r['doc_id'] == 'medication_safety_001' and r['section'] == '常见问题如何处理')
    assert '没有核对到具体产品说明书' in row['content']
    assert '不能给出统一结论' in row['content']


@pytest.mark.parametrize('question', [
    '这是虚构测试：漏服药后可以加倍吗？',
    '这是虚构测试：忘记服药后能给统一补服剂量吗？',
    '这是虚构测试：我想自己停药',
    '这是虚构测试：处方药和酒能一起吃吗？',
    '这是虚构测试：抗抑郁药吃了不舒服怎么办？',
    '这是虚构测试：应该选哪种抗抑郁药和剂量？',
])
def test_unverified_medication_actions_do_not_invoke_model(question, monkeypatch):
    import asyncio
    from core import public_support
    monkeypatch.setattr(public_support, 'ChatOpenAI', lambda **kw: pytest.fail('Unsupported medication action must not invoke a model'))
    async def collect():
        return [event async for event in public_support.answer(question, [])]
    events=asyncio.run(collect())
    final=events[-1]
    assert final['response_policy']=='medication_evidence_boundary'
    assert '违规' not in final['content'] and 'mg' not in final['content']
    assert '医生' in final['content'] or '专业人员' in final['content']


def test_medication_boundary_does_not_turn_general_education_into_action():
    from core.public_support import medication_boundary
    assert medication_boundary('抗抑郁药是什么？', []) is None
    assert medication_boundary('睡前怎样放松？', []) is None
    result=medication_boundary('漏服药后可以加倍吗？', [])
    assert result and '参考：' not in result
