"""Deterministic section retrieval with source-role constraints; no LLM or network."""
from collections import Counter
import math
import re
import unicodedata

METHOD = 'local_section_bm25_v2'

# Language variants, not test-query/source-ID routing. Expanded words receive less weight.
ALIASES = (
    ('抑郁', '抑郁症', '抑郁障碍', 'depression'),
    ('焦虑', '焦虑症', '焦虑障碍', 'anxiety'),
    ('睡眠', '失眠', '睡不好', '睡不着', '睡前', '入睡'),
    ('家人', '亲人', '朋友', '陪伴', '支持'),
    ('压力', '担忧', '应对', 'stress'),
    ('药物', '用药', '服药', '吃药', '处方药', '抗抑郁药'),
    ('停药', '断药', '停服'),
    ('漏服', '忘记服药', '忘吃药', '忘记吃药'),
    ('不良反应', '副作用', '吃了不舒服'),
    ('酒精', '喝酒', '和酒'),
    ('剂量', '药量', '加倍'),
    ('求助', '就医', '看医生', '门诊'),
    ('phq9', 'phq-9'), ('gad7', 'gad-7'),
)
STOP = {'什么', '怎么', '如何', '可以', '是不是', '一个', '我的', '自己', '需要', '应该', '哪些', '这个', '最近', '事情'}


def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    return re.sub(r'\b(phq|gad)\s*[-—]?\s*([79])\b', r'\1\2', text)


def tokens(text):
    text = normalize(text)
    result = re.findall(r'[a-z]+[a-z0-9]*|\d+', text)
    for run in re.findall(r'[\u4e00-\u9fff]+', text):
        if len(run) == 1:
            continue
        result.extend(run[i:i+2] for i in range(len(run)-1) if run[i:i+2] not in STOP)
    return result


def rank(query, rows, k):
    if not query.strip() or k <= 0:
        return []
    normalized = normalize(query)
    query_terms = {token: 1.0 for token in tokens(query)}
    for group in ALIASES:
        if any(normalize(word) in normalized for word in group):
            for word in group:
                for token in tokens(word):
                    query_terms.setdefault(token, .35)
    # Full title helps select the relevant topic, heading/body resolve the specific question.
    fields = [(Counter(tokens(r['title'])), Counter(tokens(r['section'])), Counter(tokens(r['content']))) for r in rows]
    frequencies = Counter()
    for title, heading, body in fields:
        frequencies.update(set(title) | set(heading) | set(body))
    average = sum(sum(body.values()) for _, _, body in fields) / max(1, len(fields))
    ranked = []
    navigation = any(word in normalized for word in ('查询', '说明书', '官网', '药监', '查找', '哪里查'))
    for row, (title, heading, body) in zip(rows, fields):
        if row['section'] in {'知识库维护要求', '工程要求'}:
            continue
        if any(s['evidence_role'] == 'portal_navigation' for s in row['sources']) and not navigation:
            continue
        score = 0.0
        length = sum(body.values())
        for term, weight in query_terms.items():
            idf = math.log(1 + (len(rows)-frequencies[term]+.5)/(frequencies[term]+.5))
            tf = body[term]
            body_score = tf*2.2/(tf+1.2*(.25+.75*length/max(average, 1))) if tf else 0
            score += weight*idf*(body_score + .65*bool(title[term]) + 1.5*bool(heading[term]))
        # Do not return broad documents for completely unrelated queries.
        if not any(t in title or t in heading or t in body for t in query_terms):
            continue
        if score > 0:
            ranked.append(dict(row, retrieval_score=round(score, 6)))
    return sorted(ranked, key=lambda r: (-r['retrieval_score'], r['doc_id'], r['section']))[:k]
