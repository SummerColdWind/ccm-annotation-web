"""Label codes match cookbook/操作手册20261027.md exactly."""
MANUAL_VERSION = "20261027"
LAYERS = [
    {"id": "a", "name": "基底下神经丛（SBNP）层", "hint": "细长、线状或串珠状神经，可有弯曲、分叉及连接。"},
    {"id": "b", "name": "角膜上皮细胞层", "hint": "密集多边形细胞，呈网格状或铺路石样。"},
    {"id": "c", "name": "角膜基质层", "hint": "散在高反光点状、长圆形或梭形细胞核。"},
    {"id": "d", "name": "其他 / 无法辨认 / 非角膜区域", "hint": "其他角膜层面、信息不足或非角膜组织区域。"},
]
AREAS = [{"id": "i", "name": "少量", "detail": "<10%"}, {"id": "j", "name": "中量", "detail": "10%–50%"}, {"id": "k", "name": "大量", "detail": ">50%"}]
Q2 = [
    {"id": "a", "name": "优", "hint": "边界及细节清楚，中心线及分支连接明确，可可靠追踪。"},
    {"id": "b", "name": "良", "hint": "轻度模糊、低对比或局部细节损失，绝大多数路径仍可靠。"},
    {"id": "c", "name": "中", "hint": "部分节段、边界或连接不确定，部分追踪需要推测。"},
    {"id": "d", "name": "差", "hint": "多处或主要神经路径无法可靠判断。"},
]
Q3 = [
    {"id": "a", "name": "不存在", "hint": "不存在上述除 SBNP 之外的生理或病理结构。"},
    {"id": "b", "name": "分离良好", "hint": "存在结构，与神经容易区分，无重叠或接触。"},
    {"id": "c", "name": "局部混淆", "hint": "接触、重叠或形态相似，使少量（≤3处）追踪不确定。"},
    {"id": "d", "name": "广泛混淆", "hint": "广泛重叠或混杂，使多处（>3处）追踪难以辨认。"},
]
Q4 = [
    {"id": "a", "name": "压力条纹 / 嵴 / 压痕", "hint": "宽带状、折皱或嵴状结构，可能伴组织受压或变形。"},
    {"id": "b", "name": "运动模糊", "hint": "含眼动锯齿、拉伸、逐行错位或拖影。"},
    {"id": "c", "name": "局部过亮 / 过曝", "hint": "成片泛白，高亮区域淹没组织边界及细节。"},
    {"id": "d", "name": "局部过暗 / 曝光不足", "hint": "局部明显变暗，细纤维或组织边界难以辨认。"},
    {"id": "e", "name": "其他采集伪影", "hint": "上述类别以外的非解剖性图案。"},
    {"id": "n", "name": "不适用 · 未见明显伪影", "hint": "未见上述明显退化或伪影，与其他选项互斥。"},
]


def normalize(payload, final=False):
    if not isinstance(payload, dict) or set(payload) - {"q1", "q2", "q3", "q4"}:
        raise ValueError("标注字段无效")
    q1 = payload.get("q1", {})
    if not isinstance(q1, dict) or any(k not in "abcd" or len(k) != 1 or v not in (None, "i", "j", "k") for k, v in q1.items()):
        raise ValueError("Q1 层面或面积代码无效")
    if final and (not q1 or any(v is None for v in q1.values())):
        raise ValueError("请至少选择一个层面，并为每个层面选择面积")
    result = {"q1": dict(sorted(q1.items()))}
    applicable = set(q1) == {"a"}
    for name in ("q2", "q3"):
        value = payload.get(name)
        if value not in (None, "a", "b", "c", "d", "n"):
            raise ValueError(f"{name.upper()} 选项无效")
        if applicable and (value == "n" or (final and value is None)):
            raise ValueError(f"仅含 SBNP 时，请完成 {name.upper()} 分级")
        result[name] = value if applicable else ("n" if q1 else None)
    q4 = payload.get("q4", [])
    if not isinstance(q4, list) or any(x not in ("a", "b", "c", "d", "e", "n") for x in q4) or len(q4) != len(set(q4)):
        raise ValueError("Q4 选项无效")
    if "n" in q4 and len(q4) > 1:
        raise ValueError("Q4 的不适用不能与伪影同时选择")
    if final and not q4:
        raise ValueError("请完成 Q4；没有伪影请选择不适用")
    result["q4"] = sorted(q4)
    return result
