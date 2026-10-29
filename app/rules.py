"""Annotation rules from cookbook/操作手册20261029.md (three-question revision)."""
MANUAL_VERSION = "20261029-r5"
LAYERS = [
    {"id": "a", "name": "基底下神经丛（SBNP）层", "hint": "高反光、细长的线状或串珠状神经，可有弯曲、分叉及连接。同一区域出现 SBNP 与相邻层面重叠时，只计为 SBNP。"},
    {"id": "b", "name": "角膜上皮细胞层", "hint": "密集排列的多边形细胞，呈网格状或铺路石样；与 SBNP 重叠的区域不重复计入。"},
    {"id": "c", "name": "角膜基质层", "hint": "散在高反光点状、长圆形或梭形细胞核，可见较粗的基质神经；与 SBNP 重叠的区域不重复计入。"},
    {"id": "d", "name": "其他 / 无法辨认 / 非角膜区域", "hint": "其他角膜层面（如弹力层、内皮层）、信息不足而无法确定层面的区域，或非角膜组织。"},
]
AREAS = [{"id": "i", "name": "少量", "detail": "<10%"}, {"id": "j", "name": "中量", "detail": "10%–50%"}, {"id": "k", "name": "大量", "detail": ">50%"}]
Q2 = [
    {"id": "a", "name": "良", "hint": "神经总体对比度良好，大多数神经可被可靠追踪。"},
    {"id": "b", "name": "中", "hint": "神经总体对比度一般，或局部区域存在影响神经追踪的干扰因素，使得部分神经节段模糊或不可见，无法完成可靠追踪，尤其是图像边缘及角落区域。"},
    {"id": "c", "name": "差", "hint": "神经总体对比度较差，或广泛区域存在影响神经追踪的干扰因素，大多数神经模糊或不可见，无法完成可靠追踪。"},
]
Q3 = [
    {"id": "a", "name": "压力线", "hint": "较宽的带状、折皱样或嵴状结构，局部组织可呈受压或变形外观。"},
    {"id": "b", "name": "运动模糊", "hint": "拖影、模糊、锯齿样变形、拉伸或逐行错位。"},
    {"id": "c", "name": "过亮", "hint": "局部成片泛白，神经或细胞的边界及细节被高亮区域淹没。"},
    {"id": "d", "name": "过暗", "hint": "局部明显变暗，神经或细胞与背景灰度差减小，细节难以辨认。"},
    {"id": "e", "name": "层面重叠", "hint": "SBNP 与上皮细胞或基质细胞重叠出现。", "multiple": True,
     "options": [{"id": "e1", "name": "上皮细胞"}, {"id": "e2", "name": "基质细胞"}]},
    {"id": "f", "name": "免疫细胞", "hint": "亮度较高的圆形、椭圆形或树突状小体。", "multiple": False,
     "options": [{"id": "f1", "name": "少量散在分布", "detail": "<5个"}, {"id": "f2", "name": "中量分布", "detail": "5–20个"}, {"id": "f3", "name": "大量密集分布", "detail": ">20个"}]},
    {"id": "g", "name": "其他病理生理结构", "hint": "除 SBNP 和免疫细胞以外的局部结构，通常为高亮。"},
    {"id": "n", "name": "不适用 · 未见上述干扰", "hint": "未见上述明显退化或伪影，与其他选项互斥。"},
]


def normalize(payload, final=False):
    if not isinstance(payload, dict) or set(payload) - {"q1", "q2", "q3", "q3_details"}:
        raise ValueError(f"标注字段无效，请使用 {MANUAL_VERSION} 版三题规则")
    q1 = payload.get("q1", {})
    if not isinstance(q1, dict) or any(k not in ("a", "b", "c", "d") or v not in (None, "i", "j", "k") for k, v in q1.items()):
        raise ValueError("Q1 层面或面积代码无效")
    if final and not q1:
        raise ValueError("请至少选择一个层面或区域")
    if final and len(q1) > 1 and any(v is None for v in q1.values()):
        raise ValueError("选择多个层面时，请为每个层面选择面积")
    result = {"q1": {k: v if len(q1) > 1 else None for k, v in sorted(q1.items())}}
    q2, q3, details = payload.get("q2"), payload.get("q3"), payload.get("q3_details", {})
    if q2 not in (None, "a", "b", "c", "n"):
        raise ValueError("Q2 请选择良、中或差")
    if q3 is not None and (not isinstance(q3, list) or any(x not in ("a", "b", "c", "d", "e", "f", "g", "n") for x in q3) or len(q3) != len(set(q3))):
        raise ValueError("Q3 干扰因素选项无效")
    if not isinstance(details, dict) or set(details) - {"e", "f"}:
        raise ValueError("Q3 细分字段无效")
    overlap, immune = details.get("e", []), details.get("f")
    if not isinstance(overlap, list) or any(x not in ("e1", "e2") for x in overlap) or len(overlap) != len(set(overlap)):
        raise ValueError("层面重叠请选择上皮细胞或基质细胞，可同时选择")
    if immune not in (None, "f1", "f2", "f3"):
        raise ValueError("免疫细胞数量须在 <5 个、5–20 个和 >20 个中单选")
    if set(q1) != {"a"}:
        # Skipped differs from Q3 n (assessed and no interference found).
        return {**result, "q2": "n" if q1 else None, "q3": None if q1 else [], "q3_details": {}}
    if q2 == "n" or (final and q2 is None):
        raise ValueError("纯 SBNP 图像请完成 Q2 分级")
    q3 = q3 or []
    if "n" in q3 and len(q3) > 1:
        raise ValueError("Q3 的不适用不能与干扰因素同时选择")
    if final and not q3:
        raise ValueError("请完成 Q3；未见上述干扰请选择不适用")
    if ("e" not in q3 and overlap) or ("f" not in q3 and immune is not None):
        raise ValueError("Q3 细分选项必须属于已选择的干扰因素")
    if final and "e" in q3 and not overlap:
        raise ValueError("请区分重叠的上皮细胞或基质细胞")
    if final and "f" in q3 and immune is None:
        raise ValueError("请选择免疫细胞数量：<5 个、5–20 个或 >20 个")
    clean_details = {}
    if "e" in q3:
        clean_details["e"] = sorted(overlap)
    if "f" in q3:
        clean_details["f"] = immune
    return {**result, "q2": q2, "q3": sorted(q3), "q3_details": clean_details}
