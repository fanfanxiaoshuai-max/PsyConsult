"""Record scoped supplemental examinations without overwriting the sealed audit."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
from core.graph.audit import read, write, digest


def prepare():
    base = ROOT / 'knowledge_sources/v3'
    reviews, inventory = read(base / 'reviews.json'), read(base / 'inventory.json')
    sources = read(base / 'remediation/sources.json')
    rows = {}

    def group(ids, source_ids, outcome, conclusion, limit):
        for uid in ids.split():
            if uid not in reviews:
                uid = 'relation:' + uid
            assert reviews[uid]['status'] == 'insufficient_evidence', uid
            assert uid not in rows, uid
            rows[uid] = dict(item_id=uid, original_review_sha256=digest(reviews[uid]),
                source_ids=source_ids.split(), outcome=outcome, conclusion=conclusion,
                scope_limit=limit, original_claim_enabled=False,
                expert_review='pending', checked_at='2026-10-20', reviewer='agent')

    group('property:04f8787e935c61048f6af186:dose_range 13cf4441fe873d04d447d25c',
          'us_sertraline_supplement', 'scoped_replacement_available',
          '美国该普通片标签按适应症、年龄列起始量、调整间隔及上限；不能用150–200mg/d作为所有患者目标量。',
          '仅该美国制剂；不替代中国说明书或个人处方。第2.1节；原来的通用范围不恢复。')
    group('property:539e69734a4c56d9e856cba5:class 0429565bf97541c58895e429',
          'us_ziprasidone_supplement', 'scoped_replacement_available',
          '该美国齐拉西酮胶囊标签将其归为非典型抗精神病药，可作为分类修订的直接补充。',
          '仅药物类别核对；不据此推导其他同类药物的适应症或相互作用。')
    group('a394c640f090f2ffc1b84e43 298012439f6f6539cf7faf6b',
          'us_buspirone_supplement', 'scoped_replacement_available',
          '美国丁螺环酮标签描述与GAD大致对应人群的短期试验；这不能确立统一的二线治疗顺序。',
          '该美国产品INDICATIONS AND USAGE；长期获益和治疗顺序须另有指南依据。')
    group('property:5fb927be024f43b102bdd1d5:use_in_OCD 2e28f05898bd118bf6fe0c3f',
          'pmid_22933237', 'scoped_replacement_available',
          '39名成人难治性OCD的12周随机双盲试验支持研究条件下阿立哌唑增效的候选描述。',
          '只阅读原作者摘要，非全文；成人难治性OCD，不代表一线治疗、儿童适用或当地批准适应症。')
    group('property:73140311e1638f7c044e7308:use_in_OCD 50b832e8432cf6bbcd15eaff',
          'pmid_10920469', 'scoped_replacement_available',
          'SRI治疗后仍难治的成人OCD小样本随机试验显示利培酮增效组改善。',
          '只阅读原作者摘要，非全文；特定难治人群、短期增效，不能生成无条件用药规则。')
    group('property:261ade81e504fe49fcbdad9a:has_high_efficacy_in_OCD property:261ade81e504fe49fcbdad9a:has_high_side_effect_burden entity:ac2d2d73a0b8e07aeb818f00 6488baba98e09c86e5fd32b9',
          'pmid_19698511', 'scoped_replacement_available',
          '一项16周成人OCD对照试验中，氯米帕明因不良反应退出比例高于舍曲林；不能据此标为普遍疗效最强。',
          '只阅读原作者摘要，非全文；仅该比较、样本和终点，不保留两个通用布尔结论。')
    group('entity:3bae0a19c25d4e24aa0a32cc 223a0be87c5d533b3bdcf1aa',
          'us_hydrochlorothiazide_supplement', 'scoped_replacement_available',
          '该氢氯噻嗪标签描述利尿药降低锂肾清除并增加毒性风险，建议一般避免合用。',
          '该美国具体产品的相互作用段；不能用单个制剂证明所有同类制剂的全部特征。')
    group('entity:1015aa49066cebdc78d7a2b2 property:1015aa49066cebdc78d7a2b2:description 5a944495f091b0debadf876b 14d0cde2d112f9e15581a38e',
          'pmid_20092882', 'original_claim_not_established',
          'BALANCE研究中联合方案优于丙戊酸半钠单药；与锂单药比较未能可靠确认或排除额外获益。不能证明数学意义的协同增效。',
          '只阅读原作者摘要，非全文；开放标签、双相I型、特定制剂；不建立协同节点及其两条裸连接。')
    group('entity:d95e4f8e8197f79c6b006f41 3b6dae6ecbf3d2f5c0490c69 entity:4eb6ed4e81573a67ded5332b e1f04fc29ecd57dc7c68529e entity:9df5531c8fc27988b778de4c 0c73d9b5c16a207d6bd6b30c',
          'uk_clozapine_supplement', 'scoped_replacement_available',
          '英国Clozaril第4.3节列明相关禁忌；粒细胞缺乏史须保留毒性/特异质性限定及既往化疗例外，癫痫须限定未控制。',
          '仅英国Clozaril100mg片；严重心脏疾病等限定按该节，不转成中国批准规则。')
    group('8c2f869e59bec5a3085f4389', 'pmid_34787653', 'original_claim_not_established',
          '特定高风险退伍军人试验未观察到锂增效对重复相关事件的总体获益，不能用一个无条件降低风险关系概括全部患者。',
          '只阅读原作者摘要，非全文；该结果也不能反向证明锂在所有双相人群均无保护作用。')
    group('d5e9c9aa828c85ff9deea610', 'pmid_20015461', 'scoped_replacement_available',
          'OCD前瞻性队列观察到自知力差与较低部分缓解率相关；只能记录相关性。',
          '只阅读原作者摘要，非全文；队列有失访及混杂，不等于因果或必然治疗无效。')
    group('607827b2e868431487e1adf6', 'pmid_18725912', 'scoped_replacement_available',
          '美国成人全国调查中OCD与焦虑等类别存在较多共病。',
          '只阅读原作者摘要，非全文；该调查总体及诊断体系，不代表所有地区或每位患者。')
    group('14213b7af71f0485b17b2da0', 'pmid_36350591', 'scoped_replacement_available',
          'TAME试验比较标准化MBSR与艾司西酞普兰，样本包括多种成人焦虑障碍。',
          '只阅读原作者摘要，非全文；不是任意正念方法，也不能直接建立所有GAD患者一线等效规则。')
    group('2c2faf6fabc3a899f8f98956 67e1be0b7e746eb11e094d6d 86306ca579c20302249cb1eb b7f575d9ab91b22981ec98fb',
          'us_sertraline_supplement', 'scoped_replacement_available',
          '该舍曲林标签对其他血清素能药物强调综合征风险及监测；不能把风险警示改写为所有SSRI/SNRI药对绝对禁忌。',
          '该美国舍曲林制剂第5.2和7节；不推断其他药物标签，原绝对禁忌关系不恢复。')
    group('0139db48d946cf7288d83168 072e273070374e9d98266ea3 bb10b74924a846576021a633',
          'us_sertraline_supplement', 'scoped_replacement_available',
          '美国该舍曲林普通片标签第1节列有PTSD、SAD、PD。',
          '限定该美国制剂及标签人群；不能据此标为中国批准适应症。')
    group('29269e451c219d518faa7539', 'pmid_14709947 pmid_10327910', 'scoped_replacement_available',
          '两项社交焦虑/社交恐惧随机试验提供临床研究补充，其中一项明确为氟伏沙明缓释制剂。',
          '只阅读原作者摘要，非全文；区分剂型，不把研究结果写成普通片在中国获批。')
    group('9af5d77d3cc9980df0708ce8', 'pmid_15257068', 'scoped_replacement_available',
          '11人利培酮合用舍曲林研究中，较高舍曲林剂量时两名患者利培酮浓度升高；低剂量组未见显著平均改变。',
          '只阅读原作者摘要，非全文；小样本剂量相关观察，不写成必然倍增或绝无相互作用。')
    group('38ef2afd8538ed94fd34d365 f9c67439fdf6541170c3c2e8',
          'pmid_9627209 pmid_22426846', 'conflicting_evidence',
          '病例报告描述舍曲林合用时拉莫三嗪浓度变化；另一个小样本回顾研究平均差异不显著且效能不足。两类证据并存。',
          '只阅读原作者摘要，非全文；不恢复“无显著相互作用”，也不把病例普遍化。')
    group('0bd98b2694f5db47029e5711 31364b5c7c0d250d37ddae99',
          'pmid_21739267', 'scoped_replacement_available',
          '健康志愿者研究中氟伏沙明降低阿立哌唑清除；这支持氟伏沙明影响阿立哌唑的方向，不能证明反向升高氟伏沙明。',
          '只阅读原作者摘要，非全文；特定基因型、剂量、单次阿立哌唑条件，原反向关系停用。')
    group('9e9980f781076cc26f679d49 07f1c3a531fd0cdebc2fbf92',
          'pmid_18832427', 'original_claim_not_established',
          '所读研究考察阿立哌唑对抗抑郁药浓度的影响，未发现对舍曲林药代有明显影响；不回答舍曲林是否升高阿立哌唑。',
          '只阅读原作者摘要，非全文；保留研究方向，不据反向研究确认原关系或宣布安全。')
    group('6a4eb431584c1ce39a053575', 'uk_fluvoxamine_supplement', 'scoped_replacement_available',
          '英国Faverin普通片第4.1节列有重性抑郁发作与OCD，不能与所有抑郁障碍等同。',
          '英国该产品；不推断中国批准范围、儿童抑郁或缓释制剂范围。')

    # No relevant new primary evidence was found in this bounded supplemental set.
    # Preserve the prior, item-specific search record instead of fabricating one.
    for uid, review in reviews.items():
        if review['status'] != 'insufficient_evidence' or uid in rows:
            continue
        rows[uid] = dict(item_id=uid, original_review_sha256=digest(review),
            source_ids=[], outcome='still_open', conclusion='本轮新增原始资料未解决原断言；沿用原审核中的逐条检索记录与停用结论。',
            scope_limit=review['reason'], prior_search_attempt_ids=review['search_attempt_ids'],
            original_claim_enabled=False, expert_review='pending', checked_at='2026-10-20', reviewer='agent')
    assert len(rows) == 55
    for row in rows.values():
        row['summary'] = inventory[row['item_id']]['summary']
        assert all(sid in sources for sid in row['source_ids'])
    write(base / 'remediation/rechecks.json', dict(version='supplement-01',
        note='补查结果不是旧审核结论的覆盖，也不是临床专家批准；original_claim_enabled始终为false。',
        items=rows))
    return rows


if __name__ == '__main__':
    from collections import Counter
    print(json.dumps(dict(Counter(row['outcome'] for row in prepare().values())), ensure_ascii=False))
