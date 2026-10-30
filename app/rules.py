"""Annotation rules from cookbook/操作手册20261030.md."""
MANUAL_VERSION = "20261030"
LAYERS = [
    {"id": "a", "name": "基底下神经丛（SBNP）层", "hint": "可见细长、高反光的神经纤维，呈线状或串珠状，常有弯曲、分叉及相互连接。"},
    {"id": "b", "name": "角膜上皮细胞层", "hint": "可见密集排列的多边形细胞，常呈网格状或铺路石样。"},
    {"id": "c", "name": "角膜基质层", "hint": "可见散在的高反光细胞核，呈点状、长椭圆形或梭形，排列通常较上皮细胞疏松；部分区域可见较粗的基质神经。"},
    {"id": "d", "name": "其他 / 无法辨认 / 非角膜区域", "hint": "包括可辨认但不属于前三类的其他角膜层面，如弹力层或内皮层，也包括因信息不足而无法确定层面，以及可确认不属于角膜组织的区域。"},
]
AREAS = [{"id": "i", "name": "小面积", "detail": "<10%"}, {"id": "j", "name": "中等面积", "detail": "10%–50%"}, {"id": "k", "name": "大面积", "detail": ">50%"}]
Q2 = [
    {"id": "a", "name": "良", "hint": "神经总体对比度良好，大多数神经可被可靠追踪。"},
    {"id": "b", "name": "中", "hint": "神经总体对比度一般，或局部区域存在影响神经追踪的干扰因素，使得部分神经节段模糊或不可见，无法完成可靠追踪。"},
    {"id": "c", "name": "差", "hint": "神经总体对比度较差，或广泛区域存在影响神经追踪的干扰因素，大多数神经模糊或不可见，无法完成可靠追踪。"},
]
Q3 = [
    {"id": "a", "name": "少", "hint": "图像中不存在免疫细胞，或存在极少量免疫细胞（<5 个）。"},
    {"id": "b", "name": "中", "hint": "图像中整体散在分布中量免疫细胞（5–20 个），且不存在局部区域聚集的情况。"},
    {"id": "c", "name": "多", "hint": "图像中整体散在分布大量免疫细胞（>20 个），或局部区域内聚集分布较多免疫细胞（>10 个）。"},
]
Q4 = [
    {"id": "a", "name": "压力线", "hint": "可见较宽的带状、皱褶状或嵴状结构，呈平行、弯曲或交错分布，局部组织可伴受压或变形外观。"},
    {"id": "b", "name": "运动模糊或畸变", "hint": "可见拖影、方向性模糊，或连续结构出现锯齿状变形、拉伸、逐行错位等表现。"},
    {"id": "c", "name": "亮度偏差", "hint": "图像亮度异常，神经与背景的对比减弱，不易辨认。", "multiple": False,
     "options": [{"id": "c1", "name": "偏亮", "hint": "图像明显偏亮、呈灰白色。"}, {"id": "c2", "name": "偏暗", "hint": "图像呈暗灰色。"}, {"id": "c3", "name": "显著偏暗", "hint": "图像接近黑色。"}]},
    {"id": "d", "name": "其他病理生理结构", "hint": "除 SBNP 和免疫细胞以外的，可明确辨认的局部结构。"},
]


def normalize(payload, final=False):
    if not isinstance(payload, dict) or set(payload) - {"q1", "q2", "q3", "q4", "q4_details"}:
        raise ValueError(f"标注字段无效，请使用 {MANUAL_VERSION} 版四题规则")
    q1 = payload.get("q1", {})
    if not isinstance(q1, dict) or any(k not in ("a", "b", "c", "d") or v not in (None, "i", "j", "k") for k, v in q1.items()):
        raise ValueError("Q1 层面或面积代码无效")
    if final and not q1:
        raise ValueError("请至少选择一个层面或区域")
    if final and len(q1) > 1 and any(v is None for v in q1.values()):
        raise ValueError("选择多个层面时，请为每个层面选择面积")
    result = {"q1": {k: v if len(q1) > 1 else None for k, v in sorted(q1.items())}}
    q2, q3, q4 = payload.get("q2"), payload.get("q3"), payload.get("q4")
    details = payload.get("q4_details", {})
    if q2 not in (None, "a", "b", "c", "n"):
        raise ValueError("Q2 请选择良、中或差")
    if q3 not in (None, "a", "b", "c"):
        raise ValueError("Q3 免疫细胞分布请选择少、中或多")
    if q4 is not None and (not isinstance(q4, list) or any(x not in ("a", "b", "c", "d") for x in q4) or len(q4) != len(set(q4))):
        raise ValueError("Q4 其他影响因素选项无效")
    if not isinstance(details, dict) or set(details) - {"c"}:
        raise ValueError("Q4 细分字段无效")
    brightness = details.get("c")
    if brightness not in (None, "c1", "c2", "c3"):
        raise ValueError("亮度偏差须在偏亮、偏暗和显著偏暗中单选")
    if set(q1) != {"a"}:
        # Q4 null means skipped; [] means assessed with no other factors selected.
        return {**result, "q2": "n" if q1 else None, "q3": None, "q4": None if q1 else [], "q4_details": {}}
    if q2 == "n" or (final and q2 is None):
        raise ValueError("纯 SBNP 图像请完成 Q2 分级")
    if final and q3 is None:
        raise ValueError("请完成 Q3 免疫细胞分布分级")
    q4 = q4 or []
    if "c" not in q4 and brightness is not None:
        raise ValueError("亮度细分必须属于已选择的亮度偏差")
    if final and "c" in q4 and brightness is None:
        raise ValueError("请选择亮度偏差：偏亮、偏暗或显著偏暗")
    return {**result, "q2": q2, "q3": q3, "q4": sorted(q4), "q4_details": {"c": brightness} if "c" in q4 else {}}
