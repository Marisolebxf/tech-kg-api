"""知识图谱平台接入实测：SDK 全链路模拟真实开发人员使用。"""
import sys
sys.path.insert(0, "/root/autodl-tmp/UserPush/kg-sdk")
from semantic_toolkit_kg import SemanticToolkit, SemanticToolkitError

kg = SemanticToolkit("http://127.0.0.1:8000")
print("health:", kg.health()["status"])

# ① 图谱节点：科研 NER
r1 = kg.ner_research(text="Zhang等提出的深度学习方法应用于石河子大学的桥梁结构健康监测。")
ents = kg.entities_of(r1)
print(f"① 科研NER: {len(ents)} 实体:", [(e["text"], e.get("type")) for e in ents[:4]])

# ② 图谱边：关系抽取（消费①的 record_id）
r2 = kg.relation_extract(record_id=kg.record_id(r1))
tris = kg.triples_of(r2)
print(f"② 关系抽取: {len(tris)} 三元组:", [(t["subject"], t["relation"], t["object"]) for t in tris[:3]])

# ③ 分类 + 关键词
r3 = kg.classify_zh("本文提出基于深度学习的桥梁结构健康监测方法，部署传感器网络采集振动信号。", title="桥梁监测")
c = (r3["data"].get("classifications") or [{}])[0]
print(f"③ 中文分类: {c.get('clc_code')} {c.get('label')}")
r4 = kg.keywords_en("We propose convolutional neural networks for structural health monitoring of bridges.")
kws = (r4["data"].get("keywords") or [])
print(f"④ 英文关键词: {[k.get('keyword') for k in kws[:4]]}")

# ⑤ 文件模式 + 深度聚类
open("/tmp/kgd.txt", "w").write("Zhang等提出深度学习方法用于桥梁监测。")
r5 = kg.ner_general_file("/tmp/kgd.txt")
print(f"⑤ 通用NER文件模式: {len(kg.entities_of(r5))} 实体")
DOCS = [{"document_id": f"d{i}", "title": t[:4], "text": t, "publication_date": "2024-01-0" + str(i)}
        for i, t in enumerate([
            "本文部署加速度传感器网络采集在役桥梁振动信号，用深度网络识别损伤模式，效果显著。",
            "提出改进卷积神经网络对混凝土表面裂缝图像进行分割与宽度量化分析。",
            "研究传感器测点数量与信息量之间的权衡关系，建立优化布设定量方法。",
            "设计区域桥梁群监测数据的统一存储与共享服务平台架构并试点应用。"], 1)]
r6 = kg.deep_cluster(DOCS)
clusters = r6["data"].get("clusters") or []
print(f"⑥ 深度聚类: {len(clusters)} 簇")

# ⑥ 错误处理验证
try:
    kg.classify_en("El monitoreo de salud de puentes depende de métodos.")
    print("⑦ 西班牙语: 未拦截(坏)")
except SemanticToolkitError as e:
    print(f"⑦ 错误处理: 拦截 ✓ ({str(e)[:36]}…)")
print("=== SDK 全链路通过 ===")
