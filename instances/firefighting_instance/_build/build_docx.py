# -*- coding: utf-8 -*-
"""Build the Word case-study document for the UAV firefighting instance suite.

Reads  : _build/stats.json, _build/solve_results.json (or solve_smoke.json)
Writes : 无人机森林灭火任务规划算例说明.docx  (workspace root)
"""
import json
import math
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(r"C:\kares_main\instances\firefighting_instance")
BUILD = ROOT / "_build"
FIG = BUILD / "figures"
OUT = ROOT / "无人机森林灭火任务规划算例说明.docx"

EX = ROOT / "example"
UAV_DIR = Path(r"C:\kares_main\instances\uav")

SONG = "宋体"
HEI = "黑体"
TNR = "Times New Roman"

stats = json.loads((BUILD / "stats.json").read_text(encoding="utf-8"))
inst1 = stats["instance_001"]
fps = inst1["fire_points"]
uavs = inst1["uavs"]
agg = stats["aggregate"]
batches = stats["batches"]

res_path = BUILD / "solve_results.json"
results = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else []
smoke = json.loads((BUILD / "solve_smoke.json").read_text(encoding="utf-8"))[0]
example = next((r for r in results if r["instance_id"] == 1 and r["seed"] == 42), smoke)

d1 = json.loads((EX / "firefighting_instance_001.json").read_text(encoding="utf-8"))
tasks1 = d1["tasks"]
tmap = {t["id"]: t for t in tasks1}
fire_map = {p["id"]: p for p in d1["fire_points"]}


# ----------------------------------------------------------------- helpers
def set_font(run, ascii_font=SONG, ea_font=SONG, size=12, bold=False, italic=False,
             color=None):
    run.font.name = ascii_font
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), ascii_font)
    rFonts.set(qn("w:hAnsi"), ascii_font)
    rFonts.set(qn("w:eastAsia"), ea_font)


def para(doc, text="", size=12, bold=False, italic=False, align=None, indent=True,
         space_before=0, space_after=6, line=1.5, ea=SONG, ascii_font=TNR, color=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    if align is not None:
        p.alignment = align
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if indent:
        pf.first_line_indent = Pt(size * 2)
    if text:
        set_font(p.add_run(text), ascii_font=ascii_font, ea_font=ea, size=size,
                 bold=bold, italic=italic, color=color)
    return p


def rich(doc, chunks, size=12, indent=True, align=None, space_after=6, line=1.5):
    """chunks: list of (text, dict(bold=,italic=,ea=,ascii=,color=))"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if indent:
        pf.first_line_indent = Pt(size * 2)
    if align is not None:
        p.alignment = align
    for text, opt in chunks:
        set_font(p.add_run(text), ascii_font=opt.get("ascii", TNR), ea_font=opt.get("ea", SONG),
                 size=opt.get("size", size), bold=opt.get("bold", False),
                 italic=opt.get("italic", False), color=opt.get("color"))
    return p


def heading(doc, text, level=1):
    sizes = {1: 15, 2: 13, 3: 12}
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(16 if level == 1 else 12)
    pf.space_after = Pt(8 if level == 1 else 6)
    pf.line_spacing = 1.4
    pf.keep_with_next = True
    set_font(p.add_run(text), ascii_font=TNR, ea_font=HEI, size=sizes[level],
             bold=(level >= 2), color=None)
    return p


def caption(doc, text, size=10.5):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(3)
    pf.space_after = Pt(10)
    pf.line_spacing = 1.2
    set_font(p.add_run(text), ascii_font=TNR, ea_font=SONG, size=size, bold=False)
    return p


def add_figure(doc, filename, cap, width_cm=14.5):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(str(FIG / filename), width=Cm(width_cm))
    caption(doc, cap)


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def add_table(doc, headers, rows, widths=None, font_size=9.5, header_fill="DCE6F1",
              align_center=True):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    hdr = t.rows[0]
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.line_spacing = 1.05
        set_font(p.add_run(str(h)), ascii_font=TNR, ea_font=HEI, size=font_size, bold=True)
        shade(cell, header_fill)
    repeat_header(hdr)
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            if align_center:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.line_spacing = 1.05
            set_font(p.add_run(str(v)), ascii_font=TNR, ea_font=SONG, size=font_size)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    return t


def add_field(doc, instr, hint=""):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if hint:
        set_font(p.add_run(hint), size=10.5, italic=True, ea=SONG)
    r = p.add_run()
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = instr
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t")
    t.text = "（请在此处右键选择“更新域”生成目录）"
    fld3 = OxmlElement("w:fldChar")
    fld3.set(qn("w:fldCharType"), "end")
    r._r.append(fld1)
    r._r.append(it)
    r._r.append(fld2)
    r._r.append(t)
    r._r.append(fld3)
    set_font(r, size=10.5, ea_font=SONG)
    return p


def add_page_number_footer(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(p.add_run("第 "), size=9, ea_font=SONG)
    r = p.add_run()
    fld1 = OxmlElement("w:fldChar"); fld1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = "PAGE"
    fld2 = OxmlElement("w:fldChar"); fld2.set(qn("w:fldCharType"), "end")
    r._r.append(fld1); r._r.append(it); r._r.append(fld2)
    set_font(r, size=9, ea_font=SONG)
    set_font(p.add_run(" 页"), size=9, ea_font=SONG)


# ---------------------------------------------------- derived solution metrics
def metrics_from_log(entry):
    log = entry["execution_log"]
    reward = 0.0
    for fid in {e["fire_id"] for e in log if e["type"] == 3}:
        fp = fire_map[fid]
        reward += 3 * fp["value0"] * fp["hp"]
    delay = 0.0
    for e in log:
        if e["type"] == 2:
            we = tmap[e["task_id"]]["window_end"]
            if we is not None and e["start_time"] > we:
                delay += (e["start_time"] - we) * 10
    fly_cost = reward - delay - entry["net_reward"]
    return reward, delay, fly_cost


_inst_cache = {}


def inst_maps(iid):
    if iid not in _inst_cache:
        d = json.loads((EX / f"firefighting_instance_{iid:03d}.json").read_text(encoding='utf-8'))
        _inst_cache[iid] = ({t['id']: t for t in d['tasks']},
                            {p['id']: p for p in d['fire_points']})
    return _inst_cache[iid]


def run_km_delay(entry):
    """Total flight distance (km) and delay cost of one solver run."""
    tmap_i, fmap_i = inst_maps(entry['instance_id'])
    reward = delay = 0.0
    for e in entry['execution_log']:
        if e['type'] == 3:
            fp = fmap_i[e['fire_id']]
            reward += 3 * fp['value0'] * fp['hp']
        elif e['type'] == 2:
            we = tmap_i[e['task_id']]['window_end']
            if we is not None and e['start_time'] > we:
                delay += (e['start_time'] - we) * 10
    return (reward - delay - entry['net_reward']) / 3.0, delay


reward1, delay1, flycost1 = metrics_from_log(example)
total_km = flycost1 / 3.0

# per-UAV replay of the decoded solution
state = {u["id"]: {"pos": tuple(u["pos"][:2]), "ammo": u["ammo"], "dist": 0.0,
                   "tasks": [], "refills": 0} for u in uavs}
prev_pos = {}
for e in example["execution_log"]:
    task = tmap[e["task_id"]]
    st = state[e["uav"]]
    prev = tuple(st["pos"])
    refill = False
    if e["type"] == 2 and st["ammo"] < task["hp"]:
        d = math.dist(prev, (25, 25)) + math.dist((25, 25), tuple(task["pos"][:2]))
        st["refills"] += 1
        refill = True
    else:
        d = math.dist(prev, tuple(task["pos"][:2]))
    prev_pos[e["task_id"]] = prev
    st["dist"] += d
    st["pos"] = tuple(task["pos"][:2])
    ammo_before = st["ammo"]
    if e["type"] == 2:
        st["ammo"] = 3 if refill else st["ammo"]
        st["ammo"] -= task["hp"]
    st["tasks"].append({"task_id": e["task_id"], "type": e["type"], "fire": e["fire_id"],
                        "start": e["start_time"], "dist": d, "refill": refill,
                        "prev": prev, "ammo_before": ammo_before, "ammo_after": st["ammo"]})
replay_total = sum(s["dist"] for s in state.values())
assert abs(replay_total - total_km) < 0.5, (replay_total, total_km)

# per-fire chain table
chain = []
for fp in sorted(d1["fire_points"], key=lambda p: p["id"]):
    fid = fp["id"]
    ent = {e["type"]: e for e in example["execution_log"] if e["fire_id"] == fid}
    we = fp["window_end"]
    fire_e = ent.get(2)
    late = max(0.0, fire_e["start_time"] - we) if fire_e else None
    chain.append({
        "id": fid, "x": fp["pos"][0], "y": fp["pos"][1], "value": fp["value0"], "hp": fp["hp"],
        "ws": fp["window_start"], "we": we,
        "recon": ent.get(1), "fire": fire_e, "rein": ent.get(3),
        "late": late,
    })

uav_rows = []
for u in uavs:
    st = state[u["id"]]
    uav_rows.append([u["id"], "侦察机" if u["type"] == "scout" else "灭火机",
                     len(st["tasks"]), st["refills"], f"{st['dist']:.1f}",
                     f"{st['dist'] / u['max_range'] * 100:.1f}%", st["ammo"]])

# worked fire point 10 (task 28 = recon, 29 = fire, 30 = reinspection)
wf = next(c for c in chain if c["id"] == 10)

# ---------------------------------------------------------------- document
doc = Document()
sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.left_margin = Cm(2.8)
sec.right_margin = Cm(2.6)
sec.top_margin = Cm(2.5)
sec.bottom_margin = Cm(2.5)
add_page_number_footer(sec)

style = doc.styles["Normal"]
style.font.name = TNR
style.font.size = Pt(12)
style.element.rPr.rFonts.set(qn("w:eastAsia"), SONG)

# ---- title block
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(24)
p.paragraph_format.space_after = Pt(4)
set_font(p.add_run("无人机森林灭火任务规划算例构成说明"), ascii_font=TNR, ea_font=HEI,
         size=20, bold=True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(2)
set_font(p.add_run("——4 架侦察机 + 12 架灭火机、25 个火点、75 项任务的动态任务规划算例"),
         ascii_font=TNR, ea_font=HEI, size=12)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(18)
set_font(p.add_run("算例说明材料（配合课程汇报讲解）"), ascii_font=TNR, ea_font=SONG, size=11)

# ---- abstract
rich(doc, [("摘　要：", {"bold": True, "ea": HEI}),
           ("本文说明作者所设计的森林灭火无人机编队任务规划算例。算例以“一处森林区域多点起火、"
            "地面指挥中心调度异构无人机编队实施灭火”为背景，由 16 架无人机（4 架侦察机、12 架灭火机）、"
            "25 个火点和 75 项任务构成；每个火点需要依次完成侦察、灭火、复检三段任务，三段任务全部完成"
            "才结算该火点的保护价值奖励。算例采用双层编码（任务顺序 + 无人机分配，长度 150），"
            f"目标函数由奖励、飞行成本、延误成本与约束违反罚值四部分组成。算例集共 {agg['n_instances']} 个"
            f"独立实例（{agg['total_fire_points']} 个火点、{agg['total_tasks']} 项任务），"
            "全部实例均已通过结构一致性校验，并在 6 个代表性实例上验证了可解性与区分度。"
            "本文依次介绍算例的场景构成、规模与参数设置、"
            "数据文件组织、算例集的统计特征、典型实例（实例 001）的三段任务链推演与一次完整求解结果，"
            "并给出目标函数、约束代价与评价指标的定义，最后汇报基于基线遗传算法的多实例求解结果。",
            {})], size=11, indent=True, space_after=10)
rich(doc, [("关键词：", {"bold": True, "ea": HEI}),
           ("无人机编队；森林灭火；任务规划；时间窗；算例设计；遗传算法", {})], size=11,
     space_after=14)

add_field(doc, r'TOC \o "1-3" \h \z \u')
para(doc, "")

# =============================================================== 1
heading(doc, "1　算例总体设计", 1)
heading(doc, "1.1　场景设定", 2)
para(doc, "本算例面向森林火灾的早期处置：某一森林区域内多点同时起火，地面指挥中心需要在有限时间内"
          "调度一支异构无人机编队，对全部火点实施“先侦察、后灭火、再复检”的处置流程。"
          "考虑到森林区域地形复杂、火势蔓延方向不确定，算例不假设已知完整火场信息，"
          "而是要求每一处火点先由侦察机确认火情，再由灭火机实施灭火，最后由侦察机复检确认余火扑灭。"
          "只有三段任务全部成功完成，该火点才被判定为彻底扑灭，并结算其保护价值奖励。")
para(doc, "这一设定使算例同时包含三类彼此耦合的决策：任务执行顺序（哪一处火点先处理）、"
          "任务与无人机的匹配（谁去做）、以及资源补给时机（灭火机弹药不足时何时返回基地补给）。"
          "其中灭火任务还受到时间窗约束——火点在其时间窗内处理的效果最好，过早抵达需要等待，"
          "过晚抵达仍然允许执行，但会产生线性延误成本。")

heading(doc, "1.2　算例构成要素", 2)
para(doc, "算例由“环境—编队—任务—约束—目标”五个层面构成，各层面的要素与取值见表 1。")
add_table(doc,
          ["层面", "构成要素", "取值 / 说明"],
          [["环境", "任务区域", "x∈[20,100] km，y∈[10,90] km，z=0（火点高度忽略）"],
           ["", "基地位置", "[25, 25, 10] km，承担弹药补给功能"],
           ["", "火点数量", "25 个，每处火点有独立的位置、保护价值与火势等级"],
           ["编队", "无人机总数", "16 架：4 架侦察机（UAV1–4）+ 12 架灭火机（UAV5–16）"],
           ["", "巡航速度", "0.5 km/s（全编队相同）"],
           ["", "最大航程", "侦察机 1000 km，灭火机 800 km"],
           ["", "弹药", "侦察机为 0；灭火机初始 6（UAV5–6）或 5（UAV7–16），补给后重置为 3"],
           ["任务", "任务分解", "每处火点 3 项任务：侦察（类型 1）→ 灭火（类型 2）→ 复检（类型 3）"],
           ["", "任务总数", "25 × 3 = 75 项，任务 ID 为 (j−1)×3+1、+2、+3"],
           ["", "任务时长", "执行时长为 0，时间消耗仅来自飞行与补给"],
           ["约束", "顺序依赖", "灭火须在侦察之后，复检须在灭火之后"],
           ["", "机型匹配", "侦察/复检只能由侦察机执行，灭火只能由灭火机执行"],
           ["", "弹药与航程", "灭火消耗弹药等于火势等级 HP_j；累计航程不得超过最大航程"],
           ["", "时间窗", "仅灭火任务有 [window_start, window_end]，早到等待、迟到大罚"],
           ["目标", "优化目标", "最大化净收益：奖励 − 飞行成本 − 延误成本 − 违反约束罚值"]],
          widths=[1.6, 3.0, 11.0], font_size=9)
caption(doc, "表 1　算例构成要素一览")

heading(doc, "1.3　算例的组织方式", 2)
para(doc, "本算例的说明材料沿用任务规划类文献常见的“场景假设与参数设置 → 数据构成 → 典型算例推演 → "
          "求解结果分析”组织方式：先交代场景与全部参数取值，使算例可被完整复现；"
          "再给出算例集的数据结构、字段含义与统计特征；随后选取一个代表性实例，把三段任务链的时间、"
          "距离与代价逐项推算出来；最后给出求解算法在多实例上的结果，说明算例对算法具有区分度。"
          "与战场时间敏感目标类算例相比，本算例的不同之处在于：对象是森林火点而非战场目标，"
          "任务链是“侦察—灭火—复检”而非“侦察—打击—评估”，并且引入了弹药补给这一资源再填充环节，"
          "使航程约束与弹药约束相互耦合。")

add_figure(doc, "fig6_chain.png",
           "图 1　火点三段任务链、状态转移与弹药补给回路", width_cm=14.5)

# =============================================================== 2
heading(doc, "2　算例规模与参数设置", 1)
heading(doc, "2.1　规划规模", 2)
para(doc, "算例的规划规模如表 2 所示。任务顺序是一个 75 元素的排列，无人机分配是 75 个取值于 1~16 的"
          "整数（且受机型匹配约束），因此单个实例的可行解空间规模达到 75! × 4⁵⁰ × 12²⁵ 量级，"
          "属于典型的 NP 难组合优化问题，无法用精确方法在可接受时间内求解，"
          "需要采用遗传算法、禁忌搜索等元启发式方法。")
add_table(doc,
          ["项目", "取值", "说明"],
          [["无人机总数", "16", "4 架侦察机 + 12 架灭火机"],
           ["火点数", "25", "每处火点包含位置、保护价值、火势、时间窗"],
           ["任务总数", "75", "25 × 3，三段任务共用火点坐标"],
           ["染色体长度", "150", "前 75 位任务顺序，后 75 位无人机分配"],
           ["决策变量", "任务顺序 + 无人机分配", "顺序为 1~75 的全排列；分配须满足机型匹配"],
           ["单实例可行解规模", "约 75! × 4^50 × 12^25", "不含弹药与航程可行性过滤"],
           ["算例集规模", f"{agg['n_instances']} 个实例", f"共 {agg['total_fire_points']} 个火点、"
                                                          f"{agg['total_tasks']} 项任务"]],
          widths=[3.2, 4.4, 8.0], font_size=9)
caption(doc, "表 2　算例规划规模")

heading(doc, "2.2　无人机编队构成", 2)
para(doc, "编队由 16 架异构无人机构成，初始位置沿 (1,1) 至 (31,31) 的对角线方向依次排开，"
          "形成从基地前沿向任务区域纵深展开的部署态势。前 4 架为侦察机，不携带弹药，"
          "负责全部侦察与复检任务；后 12 架为灭火机，其中 UAV5、UAV6 初始挂载 6 枚灭火弹，"
          "其余灭火机初始挂载 5 枚。侦察机航程为 1000 km，明显大于灭火机的 800 km，"
          "以匹配侦察机需要往返多个火点、承担两段任务链的作业特点。编队参数见表 3。")
add_table(doc,
          ["编号", "机型", "初始位置 / km", "巡航速度 / (km·s⁻¹)", "最大航程 / km",
           "初始弹药", "任务职责"],
          [[u["id"], "侦察机" if u["type"] == "scout" else "灭火机",
            f"({u['pos'][0]:.0f}, {u['pos'][1]:.0f}, {u['pos'][2]:.0f})",
            f"{u['speed']:.1f}", u["max_range"], u["ammo"],
            "侦察、复检" if u["type"] == "scout" else "灭火（不足时补给）"]
           for u in uavs],
          widths=[1.1, 1.5, 3.2, 2.4, 1.9, 1.4, 3.5], font_size=8.5)
caption(doc, "表 3　无人机编队构成（以实例 001 为例，全部实例取值相同）")

heading(doc, "2.3　火点属性与时间窗", 2)
para(doc, "火点在任务区域 x∈[20,100] km、y∈[10,90] km 内随机生成。每个火点携带三个属性："
          "保护价值 V_j 表示火点周边森林、设施与人员等被保护对象的总价值；火势等级 HP_j 表示灭火该火点"
          "所需消耗的灭火弹数量，同时决定奖励的高低；灭火时间窗 [window_start, window_end] 表示"
          "最适宜实施灭火的时间区间。属性生成规则见表 4。")
add_table(doc,
          ["属性", "符号", "生成规则（设计值）", "实测取值范围（1250 个火点）"],
          [["位置", "(x_j, y_j)", "x∈[20,100] km，y∈[10,90] km，z=0",
            "x∈[20.13, 99.96]，y∈[10.09, 89.75]"],
           ["保护价值", "V_j", "U(50, 100)，均匀分布",
            f"[{agg['value_min']:.2f}, {agg['value_max']:.2f}]，均值 {agg['value_mean_of_means']:.2f}"],
           ["火势等级", "HP_j", "{1, 2, 3} 等概率",
            f"1: {agg['hp_counts_total']['1']} 个（36.5%），2: {agg['hp_counts_total']['2']} 个（33.0%），"
            f"3: {agg['hp_counts_total']['3']} 个（30.5%）"],
           ["时间窗起点", "window_start", "U(0, 500) s",
            f"[{agg['ws_min']:.2f}, {agg['ws_max']:.2f}] s"],
           ["时间窗长度", "window_end−window_start", "U(100, 200) s（设计值，见 4.3 节）",
            f"[{agg['width_min']:.2f}, {agg['width_max']:.2f}] s，均值 {agg['width_mean']:.2f} s"],
           ["时间窗终点", "window_end", "起点 + 窗长",
            f"[{agg['we_min']:.2f}, {agg['we_max']:.2f}] s"]],
          widths=[2.0, 2.6, 4.6, 6.4], font_size=8.5)
caption(doc, "表 4　火点属性与时间窗生成规则")

heading(doc, "2.4　任务分解与编号规则", 2)
para(doc, "算例把火点处置流程离散为三项任务，任务与火点之间通过统一编号规则关联：火点 j 的三项任务"
          "编号分别为 (j−1)×3+1（侦察）、(j−1)×3+2（灭火）与 (j−1)×3+3（复检）。"
          "例如火点 1 对应任务 1~3，火点 10 对应任务 28~30，火点 25 对应任务 73~75。"
          "三项任务共用火点坐标，但机型要求、弹药消耗与时间窗属性不同，详见表 5。")
add_table(doc,
          ["任务类型", "名称", "执行机型", "弹药消耗", "时间窗", "任务 ID 规则"],
          [["类型 1", "侦察", "侦察机（UAV1–4）", "0", "无", "(j−1)×3+1"],
           ["类型 2", "灭火", "灭火机（UAV5–16）", "HP_j ∈ {1,2,3}", "有，早到等待、迟到计罚",
            "(j−1)×3+2"],
           ["类型 3", "复检", "侦察机（UAV1–4）", "0", "无", "(j−1)×3+3"]],
          widths=[1.8, 1.6, 3.6, 2.6, 3.6, 2.4], font_size=9)
caption(doc, "表 5　三段任务定义与编号规则")

heading(doc, "2.5　全局常数设置", 2)
para(doc, "为避免不同实例之间参数漂移，全部实例共用一套常数，见表 6。这些常数同时出现在问题定义文件"
          "与基线求解程序中，是算例复现与结果比对的基准。")
add_table(doc,
          ["常数", "取值", "作用"],
          [["巡航速度 v", "0.5 km/s", "飞行时间 = 飞行距离 / v"],
           ["飞行成本系数", "3 /km", "飞行成本 = 全部无人机累计航程 × 3"],
           ["延误罚系数", "10 /单位时间", "延误成本 = max(0, 开始时刻 − window_end) × 10"],
           ["补给耗时", "5.0 s", "灭火机在基地补充弹药的时间"],
           ["补给后弹药", "3", "补给后弹药重置为 3 枚"],
           ["基地坐标", "[25, 25, 10] km", "补给点，也是绕行距离的计算端点"],
           ["单火点满额奖励", "3·V_j·HP_j", "三段任务全部成功时结算"],
           ["约束违反罚值", "违规权重和 × 1000", "分级权重见 6.2 节"]],
          widths=[3.6, 3.6, 8.4], font_size=9)
caption(doc, "表 6　全局常数设置")

# =============================================================== 3
heading(doc, "3　算例的数据构成与文件组织", 1)
heading(doc, "3.1　实例文件结构", 2)
para(doc, "每个实例保存为一个 JSON 文件，命名为 firefighting_instance_XXX.json（XXX 为三位实例编号）。"
          "文件内部由四段组成：instance_id 为实例编号；uavs 为编队列表；fire_points 为火点列表；"
          "tasks 为任务列表。三段列表之间通过编号规则与坐标保持一致：tasks 中每一项都带有 fire_id "
          "指回所属火点，type 指明任务类型，type 2 的任务携带火势与时间窗，type 1、type 3 的时间窗为 null。"
          "算例集文件统一存放于问题目录的 instances/uav/ 下，本工作区 example/ 中保存了一份与之逐字节一致的"
          "副本（50 个文件的 SHA-256 比对结果见 3.3 节），便于在不改动原始数据的前提下试验与复核。")
rich(doc, [("以实例 001 为例，文件的开头与结尾结构如下（节选）：", {})], size=11)
code = (
    '{\n'
    '  "instance_id": 1,\n'
    '  "uavs": [\n'
    '    {"id": 1, "type": "scout", "pos": [7, 7, 10], "speed": 0.5,\n'
    '     "max_range": 1000, "ammo": 0},\n'
    '    "… 共 16 架，UAV5 起为 fighter …"\n'
    '  ],\n'
    '  "fire_points": [\n'
    '    {"id": 1, "pos": [39.8613, 74.9183, 0], "value0": 86.3789,\n'
    '     "hp": 2, "window_start": 47.1675, "window_end": 354.8178},\n'
    '    "… 共 25 个火点 …"\n'
    '  ],\n'
    '  "tasks": [\n'
    '    {"id": 1, "fire_id": 1, "type": 1, "pos": [39.8613, 74.9183, 0],\n'
    '     "hp": 0, "window_start": null, "window_end": null, "duration": 0.0},\n'
    '    {"id": 2, "fire_id": 1, "type": 2, "pos": [39.8613, 74.9183, 0],\n'
    '     "hp": 2, "window_start": 47.1675, "window_end": 354.8178, "duration": 0.0},\n'
    '    "… 共 75 项任务 …"\n'
    '  ]\n'
    '}'
)
cp = doc.add_paragraph()
cp.paragraph_format.left_indent = Pt(24)
cp.paragraph_format.space_after = Pt(10)
cp.paragraph_format.line_spacing = 1.15
set_font(cp.add_run(code), ascii_font="Consolas", ea_font=SONG, size=9)
caption(doc, "代码 1　实例文件的 JSON 结构（以实例 001 为例，节选）")

heading(doc, "3.2　字段说明", 2)
add_table(doc,
          ["所在段落", "字段", "类型", "含义与取值范围"],
          [["—", "instance_id", "整数", "实例编号，1~50"],
           ["uavs", "id / type", "整数 / 字符串", "无人机编号 1~16；机型 scout 或 fighter"],
           ["uavs", "pos", "浮点数组", "初始位置 [x, y, z]，单位 km，z 取 10"],
           ["uavs", "speed / max_range", "浮点数", "巡航速度 0.5 km/s；最大航程 1000（scout）或 800（fighter）"],
           ["uavs", "ammo", "整数", "初始弹药：scout 为 0；fighter 为 6（UAV5–6）或 5（UAV7–16）"],
           ["fire_points", "pos / value0", "浮点数组 / 浮点数", "火点坐标；保护价值 V_j ∈ [50,100]"],
           ["fire_points", "hp", "整数", "火势等级 HP_j ∈ {1,2,3}，等于灭火任务弹药消耗"],
           ["fire_points", "window_start / window_end", "浮点数", "灭火时间窗起止时刻，单位 s"],
           ["tasks", "id / fire_id / type", "整数", "任务编号 1~75；所属火点；任务类型 1/2/3"],
           ["tasks", "hp", "整数", "灭火任务为 HP_j，侦察与复检任务为 0"],
           ["tasks", "window_start / window_end", "浮点数或 null", "仅 type 2 有效；type 1、3 为 null"],
           ["tasks", "duration", "浮点数", "任务执行时长，算例中恒为 0"]],
          widths=[2.6, 3.4, 2.4, 7.2], font_size=8.5)
caption(doc, "表 7　实例文件字段说明")

heading(doc, "3.3　数据一致性与可解性校验", 2)
para(doc, "在生成算例集后，对全部实例执行了结构校验，校验项与结果见表 8。"
          "校验保证了算例可以被求解程序无条件加载，且不会因数据缺陷产生虚假的不可行解。")
add_table(doc,
          ["校验项", "判据", "结果"],
          [["规模一致", "每个实例均为 16 架无人机、25 个火点、75 项任务",
            "50/50 通过" if (agg["all_16_uavs"] and agg["all_25_fire"] and agg["all_75_tasks"]) else "存在异常"],
           ["机型结构一致", "每个实例均为 4 架侦察机 + 12 架灭火机", "50/50 通过"],
           ["任务编号连续", "任务 ID 恰为 1~75 且不重复", "50/50 通过"],
           ["任务类型配比", "类型 1/2/3 各 25 项", "50/50 通过"],
           ["火点属性合法", "V_j ∈ [50,100]、HP_j ∈ {1,2,3}、窗长 ≥ 100 s",
            "1250/1250 通过"],
           ["火点-任务字段一致", "type 2 任务的 hp 与 window 等于所属火点数值", "50/50 通过"],
           ["副本一致性", "工作区 example/ 与 instances/uav/ 的 50 个实例 SHA-256 逐一相同",
            f"{agg['hash_checked']}/50 通过"]],
          widths=[3.0, 8.0, 3.0], font_size=9)
caption(doc, "表 8　算例集数据一致性校验结果")

# =============================================================== 4
heading(doc, "4　算例集构成与统计特征", 1)
heading(doc, "4.1　算例集组成", 2)
para(doc, f"算例集共 {agg['n_instances']} 个独立实例，编号 001~050，对应 "
          f"{agg['total_fire_points']} 个火点与 {agg['total_tasks']} 项任务，"
          f"累计火势总量为 {agg['total_hp']}。各实例的编队与规模完全相同，差异仅体现在火点位置、"
          "保护价值、火势等级与灭火时间窗的随机取值上，因此实例之间具有可比性："
          "在相同算法与相同计算预算下，适应度的差异来自火点分布与时间窗松紧，而非问题结构的变化。")
para(doc, "算例集按生成批次分为两组：实例 001–030 与实例 031–050。两组在时间窗参数上存在系统性差异，"
          "这为考察算法在“宽窗”与“紧窗”两种时间耦合强度下的表现提供了天然对照，详见 4.3 节。")

heading(doc, "4.2　参数统计特征", 2)
para(doc, "对全部 1250 个火点的属性进行统计，结果见表 9。保护价值近似均匀分布，均值 "
          f"{agg['value_mean_of_means']:.2f}；火势等级 1、2、3 的比例为 "
          f"{agg['hp_counts_total']['1']}:{agg['hp_counts_total']['2']}:{agg['hp_counts_total']['3']}"
          "（36.5% : 33.0% : 30.5%），与等概率设定基本吻合；火点坐标覆盖整个任务区域，"
          "在 x、y 方向均无明显空洞。各参数的分布形态见图 2。")
add_table(doc,
          ["统计量", "保护价值 V_j", "火势 HP_j", "时间窗起点 / s", "时间窗长度 / s"],
          [["最小值", f"{agg['value_min']:.2f}", "1", f"{agg['ws_min']:.2f}", f"{agg['width_min']:.2f}"],
           ["最大值", f"{agg['value_max']:.2f}", "3", f"{agg['ws_max']:.2f}", f"{agg['width_max']:.2f}"],
           ["均值", f"{agg['value_mean_of_means']:.2f}", "1.94", "215.06", f"{agg['width_mean']:.2f}"],
           ["说明", "近似均匀分布", "等概率分布", "覆盖 0~500 s", "两批数据分布不同"]],
          widths=[2.4, 3.4, 2.6, 3.6, 3.6], font_size=9)
caption(doc, "表 9　算例集火点参数统计（1250 个火点）")
add_figure(doc, "fig2_params.png", "图 2　算例集火点参数统计特征", width_cm=15.0)

heading(doc, "4.3　两批实例的时间窗差异", 2)
para(doc, "统计发现，两批实例的时间窗参数服从不同的取值范围，见表 10。实例 031–050 的时间窗完全符合"
          "设计值（窗长 U(100,200) s、起点 ≤ 500 s）；实例 001–030 采用了放宽的时间窗参数"
          "（起点 ≤ 400 s、窗长 ≤ 350 s），时间窗平均长度由 149.5 s 增加到 231.8 s。"
          "这一差异使实例 001–030 的时间窗重叠程度更高、等待时间更长，"
          "而实例 031–050 的时间窗更紧、火点之间对同一时间区间的竞争更激烈。")
add_table(doc,
          ["分组", "实例数", "时间窗起点范围 / s", "时间窗长度范围 / s", "窗长均值 / s",
           "窗长 > 200 s 的实例"],
          [["实例 001–030", batches["batch_A_001_030"]["count"],
            f"0.09~399.93", f"100.40~349.67",
            f"{batches['batch_A_001_030']['width_mean']:.2f}",
            f"{batches['batch_A_001_030']['n_instances_with_width_gt_200']}"],
           ["实例 031–050", batches["batch_B_031_050"]["count"],
            f"1.78~498.07", f"100.11~199.95",
            f"{batches['batch_B_031_050']['width_mean']:.2f}",
            f"{batches['batch_B_031_050']['n_instances_with_width_gt_200']}"]],
          widths=[2.6, 1.4, 3.2, 3.2, 2.2, 2.6], font_size=9)
caption(doc, "表 10　两批实例的时间窗参数对比")
para(doc, "需要说明的是，问题定义文件中给出的窗长设计值为 U(100,200) s，"
          "而实际数据中实例 001–030 的窗长上限达到 349.67 s。"
          "在以数据为准的原则下，本材料按实测范围描述算例；若后续统一按设计值重新生成实例，"
          "两批实例的难度差异将随之消失。")

heading(doc, "4.4　算例的难度特征", 2)
para(doc, "算例的难度主要来自三个方面。其一是解空间规模巨大：任务顺序为 75 的全排列，"
          "无人机分配还须满足机型匹配，随机搜索几乎不可能命中高质量解。"
          "其二是约束彼此耦合：弹药消耗与火势等级绑定，弹药不足触发基地往返，"
          "往返距离又占用航程额度，一处火点的补给决策会改变后续所有火点的可执行性。"
          "其三是时间维度的耦合：25 个灭火时间窗在 10~620 s 内相互重叠（实例 001 的窗口结构见图 4），"
          "同一架灭火机在同一时刻只能服务一个火点，早到需等待、迟到要计罚，"
          "使得“先处理哪个火点”与“由谁处理”必须联合决策。")

# =============================================================== 5
heading(doc, "5　典型算例：实例 001 的构成与推演", 1)
heading(doc, "5.1　实例总览", 2)
para(doc, "选取实例 001 作为典型算例。该实例的 25 个火点集中分布在区域中部与东北部，"
          "x 大致在 40~100 km、y 大致在 25~81 km 之间；编队自西南角沿对角线展开，"
          "基地 [25,25] 位于编队与火点群之间，是灭火机往返补给的中转点，空间布局见图 3。"
          "该实例火点满额奖励合计为 "
          f"{inst1['reward_all_fires']:.2f}，即在所有火点三段任务全部完成且不计飞行与延误成本时，"
          "奖励上限约为 1.23 × 10⁴。")
add_figure(doc, "fig1_layout.png",
           "图 3　实例 001 的空间布局（圆点大小表示火势 HP、颜色表示保护价值 V）", width_cm=14.5)

heading(doc, "5.2　火点数据明细", 2)
para(doc, "实例 001 的 25 个火点数据见表 11，包含坐标、保护价值、火势等级、灭火时间窗与该火点的"
          "满额奖励 3·V_j·HP_j。表中火势以 HP=3 的火点最难处置（单次灭火消耗 3 枚弹药，"
          "灭火机初始弹药最少为 5 枚，因此处置两处 HP=3 的火点即可能触发补给）；"
          "保护价值最高的火点为火点 24（95.32）与火点 18（95.21），其奖励权重相应最高。")
add_table(doc,
          ["火点", "坐标 (x, y) / km", "保护价值 V_j", "火势 HP_j", "时间窗 / s",
           "满额奖励 3V_jHP_j"],
          [[f["id"], f"({f['x']:.2f}, {f['y']:.2f})", f"{f['value']:.2f}", f["hp"],
            f"[{f['ws']:.2f}, {f['we']:.2f}]", f"{f['reward']:.2f}"] for f in fps],
          widths=[1.0, 3.2, 2.4, 1.8, 4.4, 2.6], font_size=8)
caption(doc, "表 11　实例 001 火点数据明细")
add_figure(doc, "fig3_windows.png",
           "图 4　实例 001 各火点灭火时间窗（按起点排序，颜色表示火势等级）", width_cm=14.5)

heading(doc, "5.3　三段任务链的推演", 2)
para(doc, "以火点 10 为例说明任务链的推演过程。火点 10 位于 (96.77, 51.61) km，保护价值 94.79，"
          "火势等级 2，灭火时间窗为 [235.60, 344.23] s，三段任务全部完成可结算奖励 "
          f"{3*94.7917*2:.2f}。该火点的三项任务分别由下述无人机执行，各段任务的到达时刻、"
          "飞行距离与等待时间均由算例的平面几何关系与速度常数推算得到。")
_fp10 = next(p for p in d1["fire_points"] if p["id"] == 10)
WF_POS = tuple(_fp10["pos"][:2])
WF_WS, WF_WE = _fp10["window_start"], _fp10["window_end"]
wf_ent = {t: next(e for e in example["execution_log"] if e["fire_id"] == 10 and e["type"] == t)
          for t in (1, 2, 3)}


def seq_rec(uav_id, task_id):
    seq = state[uav_id]["tasks"]
    i = next(k for k, s in enumerate(seq) if s["task_id"] == task_id)
    return seq[i], (seq[i - 1]["start"] if i > 0 else 0.0)


wf_rec, wf_prev_time, wf_calc, wf_rows = {}, {}, {}, []
for t in (1, 2, 3):
    wf_rec[t], wf_prev_time[t] = seq_rec(wf_ent[t]["uav"], wf_ent[t]["task_id"])

for t, name in [(1, "侦察"), (2, "灭火"), (3, "复检")]:
    e, rec = wf_ent[t], wf_rec[t]
    ft = rec["dist"] / 0.5 + (5.0 if rec["refill"] else 0.0)
    arrive = wf_prev_time[t] + ft
    start = max(arrive, WF_WS) if t == 2 else arrive
    assert abs(start - e["start_time"]) < 1e-6, (t, start, e["start_time"])
    wf_calc[t] = {"ft": ft, "arrive": arrive, "start": start, "prev_time": wf_prev_time[t]}
    wf_rows.append([f"类型 {t}", name, f"UAV{e['uav']}",
                    f"({rec['prev'][0]:.2f}, {rec['prev'][1]:.2f})"
                    + (" → 基地" if rec["refill"] else ""),
                    f"{rec['dist']:.2f}", f"{ft:.2f}", f"{start:.2f}",
                    "—" if t != 2 else ("是" if start <= WF_WE else "否")])
add_table(doc,
          ["任务", "名称", "执行机", "前置位置 / km", "飞行距离 / km", "飞行时间 / s",
           "开始时刻 / s", "窗内开始"],
          wf_rows, widths=[1.3, 1.1, 1.4, 3.3, 2.1, 2.1, 2.1, 1.6], font_size=8.5)
caption(doc, "表 12　实例 001 中火点 10 的三段任务链推演")

e1, r1, c1 = wf_ent[1], wf_rec[1], wf_calc[1]
para(doc, "（1）侦察段。执行侦察任务的 UAV%d 从 (%.2f, %.2f) km 处出发（当时时刻 %.2f s）；"
          "到火点 10 的平面距离为 d = √[(96.77 − %.2f)² + (51.61 − %.2f)²] "
          "= %.2f km，按 0.5 km/s 巡航，飞行时间 Δt = %.2f / 0.5 = %.2f s，"
          "抵达时刻为 %.2f + %.2f = %.2f s。侦察任务没有时间窗，抵达即开始，"
          "故侦察开始时刻为 %.2f s。"
          % (e1["uav"], r1["prev"][0], r1["prev"][1], c1["prev_time"], r1["prev"][0],
             r1["prev"][1], r1["dist"], r1["dist"], r1["dist"] / 0.5, c1["prev_time"],
             c1["ft"], c1["arrive"], c1["start"]))

e2, r2, c2 = wf_ent[2], wf_rec[2], wf_calc[2]
if r2["refill"]:
    seg2 = ("该机出发前剩余弹药为 %d 枚，不足以完成火势等级 2 的灭火，"
            "因此必须先返回基地 [25,25] 补给（补给耗时 5.0 s，弹药重置为 3）；"
            "“当前位置→基地→火点”的飞行距离合计 %.2f km，飞行与补给合计 %.2f s，"
            "抵达时刻为 %.2f + %.2f = %.2f s。"
            % (r2["ammo_before"], r2["dist"], c2["ft"], c2["prev_time"], c2["ft"], c2["arrive"]))
else:
    seg2 = ("该机出发前剩余弹药为 %d 枚，足以完成火势等级 2 的灭火，"
            "因此直接飞往火点 10：飞行距离 %.2f km，飞行时间 %.2f s，"
            "抵达时刻为 %.2f + %.2f = %.2f s。"
            % (r2["ammo_before"], r2["dist"], c2["ft"], c2["prev_time"], c2["ft"], c2["arrive"]))
if c2["arrive"] < WF_WS:
    seg2 += ("由于抵达时刻 %.2f s 早于时间窗起点 %.2f s，按规则需等待至窗起点开始，"
             "故灭火开始时刻取 max(%.2f, %.2f) = %.2f s，处于时间窗内，不产生延误成本。"
             % (c2["arrive"], WF_WS, c2["arrive"], WF_WS, c2["start"]))
elif c2["start"] <= WF_WE:
    seg2 += ("抵达时刻 %.2f s 已落在时间窗 [%.2f, %.2f] s 内，开始时刻即为 %.2f s，"
             "不产生延误成本。" % (c2["arrive"], WF_WS, WF_WE, c2["start"]))
else:
    seg2 += ("抵达时刻 %.2f s 已晚于时间窗终点 %.2f s，按软约束规则任务仍然执行，"
             "但产生延误成本 (%.2f − %.2f) × 10 = %.2f。"
             % (c2["arrive"], WF_WE, c2["start"], WF_WE, (c2["start"] - WF_WE) * 10))
para(doc, "（2）灭火段。灭火任务由 UAV%d 执行。%s" % (e2["uav"], seg2))

e3, r3, c3 = wf_ent[3], wf_rec[3], wf_calc[3]
para(doc, "（3）复检段。复检任务由 UAV%d 执行，该机从 (%.2f, %.2f) km 处出发（当时时刻 %.2f s），"
          "飞往火点 10 的距离为 %.2f km，飞行时间 %.2f s，于 %.2f s 开始复检。"
          "复检完成即火点 10 的状态置为 3，结算奖励 3 × 94.79 × 2 = %.2f。"
          "三段任务依次由侦察机、灭火机、侦察机执行，既满足“侦察→灭火→复检”的顺序约束，"
          "也满足机型匹配约束。"
          % (e3["uav"], r3["prev"][0], r3["prev"][1], c3["prev_time"], r3["dist"], c3["ft"],
             c3["start"], 3 * 94.7917 * 2))

heading(doc, "5.4　一次完整求解的结果", 2)
para(doc, "采用基线遗传算法对实例 001 进行一次独立求解（随机种子 42，种群 600，最大代数 150，"
          f"早停耐心 80 代，共完成 {example['generations_completed']} 代、"
          f"{example['evaluations']} 次适应度评价，耗时 {example['seconds']:.1f} s），"
          "得到的最优解完成了全部 25 个火点的三段任务，无任何约束违反。"
          "解的性能指标见表 13，求解过程与任务时序见图 5、图 6。")
add_table(doc,
          ["指标", "数值", "说明"],
          [["适应度 F", f"{example['fitness']:.2f}", "奖励 − 飞行成本 − 延误成本 − 违反罚值"],
           ["奖励 R", f"{reward1:.2f}", "25 个火点全部结算，等于满额奖励合计"],
           ["飞行成本 C_fly", f"{flycost1:.2f}", f"折合总航程 {total_km:.2f} km（含补给往返）"],
           ["延误成本 C_delay", f"{delay1:.2f}", "灭火任务开始时刻超出时间窗终点的线性罚值"],
           ["约束违反罚值 P", f"{example['constraint_violation'] * 1000:.2f}",
            f"违反权重和 {example['constraint_violation']:.2f} × 1000"],
           ["完成火点数", f"{example['completed_fires']} / 25", "三段任务全部成功的火点"],
           ["已执行任务数", f"{example['executed_tasks']} / 75", "被解码器实际执行的任务"],
           ["Makespan", f"{example['makespan']:.2f} s", "最后一架无人机完成任务的时刻"]],
          widths=[3.4, 3.4, 8.8], font_size=9)
caption(doc, "表 13　实例 001 一次完整求解的性能指标")
add_figure(doc, "fig4_schedule.png",
           "图 5　实例 001 最优解的任务时序（左：各无人机任务时刻；右：各火点三段任务链）",
           width_cm=15.2)
add_figure(doc, "fig5_convergence.png", "图 6　基线遗传算法在实例 001 上的收敛曲线",
           width_cm=14.5)

heading(doc, "5.5　各无人机的任务负载与航程占用", 2)
para(doc, "对该最优解中各无人机的任务序列进行航程复算，可以得到表 14。"
          "4 架侦察机承担了 50 项侦察与复检任务，灭火机承担了 25 项灭火任务。"
          "全部无人机的累计航程均未超过各自的航程上限，与违反权重为 0 的结果一致；"
          "侦察机的航程占用率明显高于灭火机，说明在“三段任务链”结构中，"
          "侦察机是任务数量的主要承担者，而灭火机的负载受弹药与时间窗双重约束，"
          "单机任务数较少但单次机动距离更长。")
add_table(doc,
          ["无人机", "机型", "执行任务数", "补给次数", "累计航程 / km",
           "航程占用率", "结束剩余弹药"],
          uav_rows, widths=[1.6, 1.6, 2.2, 1.8, 2.6, 2.2, 2.6], font_size=8.5)
caption(doc, "表 14　实例 001 最优解中各无人机的负载与航程占用")

# =============================================================== 6
heading(doc, "6　算例的目标函数、约束与评价指标", 1)
heading(doc, "6.1　目标函数", 2)
para(doc, "算例以最大化净收益为目标，适应度函数由四项线性叠加构成：")
rich(doc, [("F = R − C_fly − C_delay − P", {"bold": True, "ea": TNR, "size": 12})],
     indent=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)
add_table(doc,
          ["分项", "计算公式", "说明"],
          [["奖励 R", "Σ 3·V_j·HP_j", "仅当火点 j 的三段任务全部成功时结算，部分完成不计奖励"],
           ["飞行成本 C_fly", "Σ 全部无人机累计航程 × 3", "含初始位置至首任务、火点间转移与补给往返"],
           ["延误成本 C_delay", "Σ max(0, start_j − window_end_j) × 10",
            "仅灭火任务；早到等待不计罚，迟到按超出时长线性计罚"],
           ["违反罚值 P", "违规权重和 × 1000", "顺序、机型、弹药与航程约束的分级罚值，见表 15"]],
          widths=[2.6, 5.4, 7.6], font_size=9)
caption(doc, "表 15　目标函数分项构成")

heading(doc, "6.2　约束体系与违反代价", 2)
para(doc, "算例采用“违反即罚”的软约束处理方式：解码时按染色体顺序逐项处理任务，"
          "不满足约束的任务被跳过并累计违规权重，权重之和乘以 1000 后从适应度中扣除。"
          "各约束的权重设置见表 16，其中机型匹配的权重最高（10），"
          "因为机型错配意味着资源根本无法执行该任务，属于结构性错误。")
add_table(doc,
          ["编号", "约束", "判定条件", "违规权重", "等效罚值"],
          [["C1", "顺序依赖", "灭火要求火点状态为 1；复检要求火点状态为 2", "+1", "1000"],
           ["C2", "机型匹配", "侦察/复检须由侦察机执行；灭火须由灭火机执行", "+10", "10000"],
           ["C3", "弹药与航程（补给）", "弹药不足时须能完成基地往返，否则跳过该任务", "+1 / +0.5",
            "1000 / 500"],
           ["C4", "直飞航程超限", "当前位置直飞距离 + 累计航程 > 最大航程", "+0.1", "100"]],
          widths=[1.3, 3.2, 6.6, 2.2, 2.3], font_size=9)
caption(doc, "表 16　约束体系与违反代价（以基线解码程序为准）")
para(doc, "说明：问题说明文件中对硬约束采用“每次违反 +1000”的简化表述，"
          "而实际解码程序中违规量按表 16 分级累计，最终统一乘以 1000 换算为罚值。"
          "二者在“违规必然导致该任务失败并被跳过”这一点上一致；"
          "本材料以程序实现为准，以免出现算例与求解结果口径不一致的情况。")
para(doc, "还需说明本算例关于“先后关系”的建模约定。顺序约束是在任务排列层面检查的："
          "解码器按染色体的任务顺序逐项处理，处理某火点的灭火任务时要求该火点已经处理过侦察任务；"
          "而每架无人机的作业时间是各自从 0 s 开始独立推进的。因此调度结果中，"
          "同一火点的三段任务可能出现“后序任务的开始时刻早于前序任务”的现象"
          "（例如某火点的侦察任务由一架已经排满任务的侦察机在 431.8 s 才开始，"
          "而灭火任务由另一架灭火机在 161.4 s 就已执行）。"
          "可见本算例的顺序约束属于“处理顺序约束”，而非“时间先后约束”。"
          "若需要严格的时间先后语义，可在解码时补充“侦察开始时刻 ≤ 灭火开始时刻 ≤ 复检开始时刻”"
          "的检查并计入违反代价；这一点建议在与其他算法对比时保持口径一致。")

heading(doc, "6.3　评价指标", 2)
para(doc, "为便于多算法、多实例的比较，算例约定以下评价指标。")
add_table(doc,
          ["指标", "符号", "含义", "方向"],
          [["适应度", "F", "净收益扣除违反罚值后的综合目标值", "越大越好"],
           ["净收益", "F + P", "奖励扣除飞行与延误成本后的收益", "越大越好"],
           ["灭火完成数", "N_done", "三段任务全部成功的火点数（0~25）", "越大越好"],
           ["工期", "T_makespan", "最后一架无人机完成任务的时刻", "作为参考"],
           ["违反权重和", "W_v", "全部被跳过任务的违规权重之和", "越小越好，0 为可行解"],
           ["最优解命中率", "K", "多次独立运行中获得最优解的次数", "越大越好"],
           ["求解耗时", "t_cpu", "单次独立运行的墙钟时间", "工程意义下越小越好"]],
          widths=[2.6, 2.0, 8.0, 3.0], font_size=9)
caption(doc, "表 17　算例评价指标")

# =============================================================== 7
heading(doc, "7　多算例求解结果", 1)
heading(doc, "7.1　实验设置", 2)
para(doc, "为验证算例的可解性与区分度，采用基线求解程序对 6 个代表性实例（批次 A 的 001、010、020，"
          "批次 B 的 031、040、050）各进行 3 次独立求解，随机种子分别取 1、2、3；"
          "对实例 001 额外使用种子 42 做了一次详细推演（即第 5.4 节的解）。"
          "算法参数为：种群规模 600、最大代数 150、早停耐心 80 代、锦标赛选择规模 3、"
          "精英保留比例 5%、交叉概率 0.8、变异概率 0.2。运行环境为 Python 3.14，"
          "单次求解耗时约 50~90 s。")
add_table(doc,
          ["项目", "设置"],
          [["算法", "双层编码单目标遗传算法（基线）"],
           ["编码", "任务顺序（1~75 全排列）+ 无人机分配（1~16），长度 150"],
           ["种群 / 代数", "600 / 150（早停耐心 80 代）"],
           ["选择 / 精英", "锦标赛（规模 3）/ 精英保留 5%"],
           ["交叉", "顺序部分类 OX 交叉 + 分配部分均匀交叉，概率 0.8"],
           ["变异", "顺序部分 swap/insert/inversion 三选一 + 分配部分重指派 1~3 位，概率 0.2"],
           ["独立运行次数", "每实例 3 次（实例 001 共 4 次），固定随机种子"]],
          widths=[3.2, 12.0], font_size=9)
caption(doc, "表 18　求解实验设置")

heading(doc, "7.2　结果统计", 2)
by_inst = {}
for r in results:
    by_inst.setdefault(r["instance_id"], []).append(r)
rows = []
for iid in sorted(by_inst):
    rs = by_inst[iid]
    fits = [r["fitness"] for r in rs]
    fires = [r["completed_fires"] for r in rs]
    cvs = [r["constraint_violation"] for r in rs]
    mks = [r["makespan"] for r in rs]
    fires_s = f"{min(fires)}" if min(fires) == max(fires) else f"{min(fires)}~{max(fires)}"
    cvs_s = f"{min(cvs):g}" if min(cvs) == max(cvs) else f"{min(cvs):g}~{max(cvs):g}"
    rows.append([iid, len(rs), f"{min(fits):.2f}", f"{sum(fits)/len(fits):.2f}", f"{max(fits):.2f}",
                 fires_s, cvs_s, f"{min(mks):.0f}~{max(mks):.0f}",
                 f"{sum(r['seconds'] for r in rs)/len(rs):.0f}"])
add_table(doc,
          ["实例", "运行次数", "J_min", "J_mean", "J_max", "完成火点", "违反权重和",
           "Makespan / s", "平均耗时 / s"],
          rows, widths=[1.0, 1.4, 1.8, 1.9, 1.8, 1.6, 1.7, 1.9, 1.8], font_size=8.5)
caption(doc, "表 19　6 个实例上基线遗传算法的求解结果（每实例 3 次独立运行，实例 001 为 4 次）")

allf = [r["fitness"] for r in results]
allfires = [r["completed_fires"] for r in results]
allcv = [r["constraint_violation"] for r in results]
n_full = sum(1 for r in results if r["completed_fires"] == 25)
n_feas = sum(1 for r in results if r["constraint_violation"] == 0)
para(doc, f"全部 {len(results)} 次独立运行的结果为：适应度最小 {min(allf):.2f}、最大 {max(allf):.2f}；"
          f"完成火点数为 {min(allfires)}~{max(allfires)} 个（满分 25 个），其中 {n_full} 次完成了全部 25 个火点；"
          f"约束违反权重和为 {min(allcv):g}~{max(allcv):g}，其中 {n_feas} 次为零违规。"
          "由此可以得出两点结论。一是算例可解：存在完成全部火点、零违规且适应度较高的解"
          f"（如实例 001 种子 42 的解，适应度 {example['fitness']:.2f}），"
          "说明算例不存在结构性不可行；二是算例具有区分度：同一实例在不同随机种子下的适应度差异"
          "可达数千，部分运行只完成了 23~24 个火点并出现约束违反，"
          "说明该问题的搜索空间崎岖、局部最优较多，能够有效区分算法的搜索与修复能力。")

heading(doc, "7.3　结果分析", 2)
para(doc, "把每次运行的适应度分解为奖励、飞行成本、延误成本与违反罚值四项后，可以看到算例的"
          "三个特征。第一，适应度差异主要由违规罚值和奖励完整性决定，而不是飞行成本的细微差别。"
          "以实例 001 的 4 次运行为例：种子 1 的解漏灭了 2 个火点，奖励少结算 "
          f"{12288.83 - 11822.52:.2f}，同时累计违反权重 4.0（折合罚值 4000.00），适应度仅为 2229.71；"
          f"种子 42 的解完成了全部 25 个火点且零违规，适应度为 6537.93；"
          f"两者相差 {6537.93 - 2229.71:.2f}，其中罚值贡献 4000.00、奖励贡献 "
          f"{12288.83 - 11822.52:.2f}，而飞行成本反而相差很小。"
          "这符合算例“违反即跳过、跳过即失去整条任务链奖励”的设计逻辑，"
          "也说明算例对解的可行性修复能力十分敏感。")
km_list = [run_km_delay(r)[0] for r in results]
delay_a = [run_km_delay(r)[1] for r in results if r["instance_id"] in (1, 10, 20)]
delay_b = [run_km_delay(r)[1] for r in results if r["instance_id"] in (31, 40, 50)]
para(doc, "第二，飞行成本在各次运行之间高度稳定，说明算例的航程维度已接近地理下界。"
          f"全部 {len(results)} 次运行的累计航程集中在 {min(km_list):.0f}~{max(km_list):.0f} km 区间"
          f"（平均约 {sum(km_list)/len(km_list):.0f} km），对应的飞行成本约 "
          f"{3*min(km_list):.0f}~{3*max(km_list):.0f}，各次运行之间的差别不足两成。"
          "相比之下，延误成本只在时间窗更紧的批次 B 中出现：批次 A（001、010、020）的 "
          f"{len(delay_a)} 次运行延误成本全部为 0，而批次 B（031、040、050）有 "
          f"{sum(1 for d in delay_b if d > 0)} 次运行出现延误，最大延误成本达 {max(delay_b):.2f}。"
          "这与 4.3 节的时间窗差异一致：窗长越短，灭火机越容易错过窗终点，"
          "时间维度对解的质量的制约越明显。")
para(doc, "第三，算例内部存在明显的难度分层，适合作为算法对比的试验床。"
          "实例 010 的 3 次运行适应度在 4474.36~4511.12 之间，波动仅约 37；"
          "而实例 001 的 4 次运行跨度达 4308.22。"
          "基线遗传算法采用的是通用算子（OX 交叉 + swap/insert/inversion 变异），"
          "并未针对弹药补给与时间窗耦合做专门设计，在火点分布与时间窗耦合较强的实例上"
          "更容易漏灭火点；后续若引入面向任务链的修复算子、以价值密度为导向的初始化或局部搜索，"
          "应能在相同算例上获得更稳定的高适应度解，这正是算例的价值所在。")

heading(doc, "7.4　算例的可复现性", 2)
para(doc, "算例的复现条件已经固化：实例文件采用固定编号并以 SHA-256 校验副本一致性；"
          "求解程序的常数（速度、成本系数、罚系数、补给时长、基地坐标）均取自第 2.5 节；"
          "实验记录包含实例编号、随机种子、评价次数与耗时。"
          "按表 18 的设置即可复现本节的统计结果；"
          "若需扩展算例规模，只需按第 3 章的字段格式生成新的实例文件，"
          "并同步更新问题定义中的规模参数即可。")

# =============================================================== 8
heading(doc, "8　小结", 1)
para(doc, f"本算例以森林灭火为背景，构建了包含 16 架异构无人机、25 个火点、75 项任务的动态任务规划"
          f"问题，并生成了 {agg['n_instances']} 个结构一致、可复现的独立实例。"
          "算例的特点是：三段任务链引入了顺序依赖与机型匹配的结构性约束；"
          "弹药补给把资源约束与航程约束耦合在一起；灭火时间窗把决策推进到时间维度。"
          f"全部实例已通过结构校验；在 6 个代表性实例上的 {len(results)} 次独立求解中，"
          f"{n_full} 次完成了全部 25 个火点、{n_feas} 次实现了零违规，"
          "表明算例可解、结果可解释，且对算法的完整性保持与可行性修复能力具有区分度，"
          "可用于任务分配与路径规划算法性能的对比评价。")

# =============================================================== appendix
doc.add_page_break()
heading(doc, "附录　实例 001 火点三段任务执行明细", 1)
para(doc, "下表给出第 5.4 节最优解中 25 个火点的三段任务执行情况，"
          "包括各段任务的执行无人机与开始时刻，以及灭火任务是否落在时间窗内。"
          "表中的时刻是各无人机独立时间轴上的调度时刻；受 6.2 节所述建模约定影响，"
          "部分火点的后序任务时刻会早于前序任务时刻，这是“处理顺序约束”的正常结果。")
add_table(doc,
          ["火点", "侦察（UAV/时刻 s）", "灭火（UAV/时刻 s）", "复检（UAV/时刻 s）",
           "灭火时间窗 / s", "延误 / s"],
          [[c["id"],
            f"UAV{c['recon']['uav']} / {c['recon']['start_time']:.1f}",
            f"UAV{c['fire']['uav']} / {c['fire']['start_time']:.1f}",
            f"UAV{c['rein']['uav']} / {c['rein']['start_time']:.1f}",
            f"[{c['ws']:.1f}, {c['we']:.1f}]",
            f"{c['late']:.1f}"] for c in chain],
          widths=[1.0, 3.1, 3.1, 3.1, 3.5, 1.4], font_size=8.5)
caption(doc, "表 A1　实例 001 最优解中各火点的三段任务执行明细")

para(doc, "（全文完）", align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, size=10.5)

doc.save(OUT)
print("saved:", OUT)
print("figures:", sorted(p.name for p in FIG.glob("*.png")))
print("sections:", len(doc.paragraphs), "paragraphs,", len(doc.tables), "tables")
