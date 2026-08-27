#!/usr/bin/env python3
"""Recompile every active approved style prompt into a direct, reusable runtime brief."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from style_atomic import atomic_write_json
from validate_style_template import validate_data


COMPILER_VERSION = "3.0.0"
EVIDENCE_RECONCILED_KEYS = {
    "mirror-paw-folding-corridor": (
        "Approved Before→After 只支持全图粗网丝印与原构图保持，"
        "撤销旧提示词中缺少可见 After 证据的强折廊和接触负形机关。"
    ),
}
SECTION_NAMES = (
    "任务",
    "保留",
    "变换权限",
    "核心效果",
    "空间结构",
    "内容映射",
    "视觉风格",
    "完成判据",
    "限制",
)
INTERNAL_TERMS = (
    "Approved After", "promptDirective", "复现合同", "复现边界", "来源绑定",
    "边界策略", "图形语言：", "空间语法：", "模板必现", "越权新增", "前文",
)
STYLE_TOKEN_MAP = {
    "transparent-watercolor": "透明水彩",
    "monoline-light-wash": "单线淡彩",
    "paper-relief-dye": "浮雕染色纸艺",
    "two-ink-risograph": "双色孔版印刷",
    "soft-screenprint": "柔和丝网印刷",
    "matte-gouache": "哑光水粉",
    "torn-washi": "手撕和纸",
    "celadon-brick-sand": "青瓷绿、砖红与暖砂色",
    "ultramarine-lemon-coral": "群青、柠檬黄与珊瑚红",
    "periwinkle-lime-softred": "长春花蓝、青柠绿与柔红",
    "tangerine-deepteal-oat": "橘黄、深青与燕麦白",
    "ice-aqua-charcoal-yellow": "冰水青、炭黑与柔黄",
    "cobalt-peach-cream": "钴蓝、淡桃与奶油白",
    "rose-duckegg-cocoa": "玫瑰红、鸭蛋青与可可棕",
    "sky-tomato-butter": "天空蓝、番茄红与奶油黄",
}

# Old packages frequently described a reusable relationship through the literal
# objects visible in the approved Before image.  Rewrite those literals into the
# visual role that a new user image must supply.  Long phrases deliberately come
# before individual nouns so the result remains idiomatic Chinese.
ROLE_REPLACEMENTS = (
    ("保留穿外套的小猴独坐室内的完整停格关系", "保留主主体、承托区域与周围空间形成的完整停格关系"),
    ("红斗篷面积变成一侧重块，脸和帽沿组成另一侧小砝码", "来源中的最大高饱和色面形成一侧重块，主识别区域与邻接轮廓形成另一侧小砝码"),
    ("双手、鞋带和视线关系", "用户图中最清晰的接触部位、细长关联线和方向关系"),
    ("鸡冠轮廓向上展开成三片不同弧度的弹道带；手臂与长颈分别成为弹道的支撑轴和中心轴", "来源中最高的重复轮廓向上展开成三片不同弧度的弹道带；两条最显著的方向轴分别承担支撑轴和中心轴"),
    ("婚纱褶皱", "主主体或其关联物中最显著的连续褶线"),
    ("婚纱", "主主体的主要覆盖形"),
    ("手肘的弯曲", "主主体最清晰的弯折轮廓"),
    ("猫脸两侧轮廓", "主识别区域两侧的外轮廓"),
    ("中央保留简化五官", "中央保留简化识别特征"),
    ("头顶风扇的运动模糊", "主主体上方现有物件或运动轮廓的模糊方向"),
    ("风扇", "上方现有旋转物件或运动轮廓"),
    ("玻璃上的指尖间隙", "一对相向接触部位之间的可见间隙"),
    ("人物居中并保留双手关系", "主主体居中并保留一对关键接触部位的关系"),
    ("完整中心羊脸", "完整主识别区域"),
    ("左右可见羊毛轮廓", "左右可见的柔软外轮廓"),
    ("来源草束", "来源中的细长纹理束"),
    ("完整猫作为中央锚点", "完整主主体作为中央锚点"),
    ("来源地毯主纹与毯子边缘", "来源承托面的主纹与边缘"),
    ("猫和室内物件", "主主体和环境物件"),
    ("完整眯眼头像", "完整主识别区域"),
    ("巨大眼睑弧", "巨大的关键局部弧线"),
    ("原图眼睑和眉毛", "用户图中最清晰的短弧轮廓"),
    ("完整人物位于起点", "完整主主体位于起点"),
    ("手指特写、手臂与衣褶、目标方向的背景区域", "接触部位特写、主体方向轮廓、目标方向的环境区域"),
    ("鸡群沿原图庭院方向", "来源中的重复主体沿原空间方向"),
    ("原图鸡群真实数量", "用户图中重复主体的真实数量"),
    ("完整脸部保持稳定", "完整主识别区域保持稳定"),
    ("眼鼻周围", "主识别特征周围"),
    ("向上的目光方向", "主主体最明确的上扬方向"),
    ("面孔从下沿进入", "主识别区域从下沿进入"),
    ("乐器琴颈", "来源中最长的窄长关联轮廓"),
    ("远景电线、手部、琴身和完整人物", "远景线索、接触局部、关联物主体和完整主主体"),
    ("两只前爪接触点", "一对关键接触部位的接触点"),
    ("环绕脸部", "环绕主识别区域"),
    ("原图爪与脸的位置", "用户图中接触部位与主识别区域的位置"),
    ("来源双手或双爪的接触点", "来源中一对关键接触部位的接触点"),
    ("完整人物位于一侧，前景手势靠近光源；手部真实轮廓投出一块大阴影，阴影内部通过指缝与掌缘负形拼出同一人物的侧脸轮廓", "完整主主体位于一侧，最清晰的前景局部靠近光源；该局部的真实轮廓投出一块大阴影，阴影内部通过轮廓间隙与边缘负形拼出同一主体的识别轮廓"),
    ("来源手势和本人脸部特征", "来源前景局部和主主体识别特征"),
    ("帽檐的阴影", "主主体上方最显著轮廓的阴影"),
    ("头面珠饰", "主识别区域旁的重复小形"),
    ("耳机外环成为回路起点，真实垂线依次经过握笔点、笔记本横线和海报中的弯路，再折回耳罩", "来源中的闭合外环成为回路起点，真实垂线依次经过接触点、承载面横线和环境中的弯路，再折回外环"),
    ("耳机、线缆、手笔、笔记本与海报道路", "外环、垂线、接触点、承载面与环境路径"),
    ("长椅地平线", "来源中的主要水平承托线"),
    ("人物、行李、盒子与树干", "主主体及三类现有关联物或环境锚点"),
    ("完整人物保留为最大珠片", "完整主主体保留为最大珠片"),
    ("人物只留主姿态", "主主体只保留最小识别姿态或轮廓"),
    ("熔岩灯中的真实红色液块", "来源中最醒目的暖色流动形"),
    ("左眼高光、右眼高光和中央金属管", "两个高识别高光与中央窄长结构"),
    ("完整黑猫", "完整主主体"),
    ("市场空间", "来源空间"),
    ("人物块、货物鳞片层、塑料布透明线层、货架硬直层", "主主体块、重复纹理层、透明线层和环境硬直层"),
    ("完整红熊猫", "完整主主体"),
    ("左右镜台与洗手池透视", "来源左右两侧的透视结构"),
    ("镜台、门洞与双爪真实位置", "侧向结构、中央开口与一对接触部位的真实位置"),
    ("来源没有植物时不得制造树枝、树叶或花朵剪影", "只使用用户图中实际存在的轮廓与纹理生成柔影"),
    ("阶梯方向与舞姿轴线", "来源环境的重复层级方向与主主体动作轴线"),
    ("动物为柔块、果实为点阵、水面为水平线", "主主体为柔块、重复小物为点阵、主要环境边界为水平线"),
    ("牛头与身体", "主识别区域与主体其余部分"),
    ("原图头身比例与侧眼方向", "用户图中主识别区域与整体的比例及方向"),
    ("小猫趴在盒边", "主主体依附承托边缘"),
    ("铅笔延长成地面影线，影线只勾出一个更简的第二姿态", "从主主体最低接触点延长一根地面影线，影线只勾出同一主体更简的第二姿态回声"),
    ("手机屏幕的浅蓝光只在袖口回响", "来源中最亮的冷色小色面只在邻近轮廓处回响"),
    ("两人举起的手臂之间", "两个主要方向轮廓之间"),
    ("舞者和单一托举者", "来源中的主主体和单一关联主体"),
    ("红帽变成唯一鲜色锚点", "来源中面积较小且最醒目的高饱和局部变成唯一鲜色锚点"),
    ("人与荒野的距离", "主主体与大面积环境的距离"),
    ("红裙下摆", "主主体下缘最显著的暖色轮廓"),
    ("小生物的绒团轮廓", "主主体最有辨识度的柔软外轮廓"),
    ("地平线、衣缝、车缘与杯口", "主要环境边界、主体内部线、关联物边缘与小型圆弧"),
    ("人物、杯子和车辆", "主主体与现有关联物"),
    ("旱獭仰头张口的完整姿态", "主主体最有辨识度的完整姿态"),
    ("完整脸部作为大轨道中心，汤匙轮廓成为一条窄长内轨，目光方向成为一条宽外轨；两轨在眼睛与匙面高光处相切", "完整主识别区域作为大轨道中心，来源中最显著的窄长关联轮廓成为内轨，主主体的视线或动作方向成为宽外轨；两轨在高识别局部与关联轮廓高光处相切"),
    ("内轨、外轨和切点分别来自汤匙、目光与可见高光，不新增餐具或符号", "内轨、外轨和切点分别来自用户图现有的窄长关联轮廓、方向线索与可见高光"),
    ("搅拌动作只在锅边回响", "来源中最清晰的旋转动作只在相邻关联物边缘回响"),
    ("剑身只向一侧延长", "来源中最长的直线关联轮廓只向一侧延长"),
    ("完整主脸", "完整主识别区域"),
    ("来源泪滴轮廓", "来源中最有辨识度的小型流线轮廓"),
    ("眼神、嘴部、背景色和衣领局部", "两个识别局部、环境色和主体边缘局部"),
    ("吐司外沿展开成四片宽度不等的铰接盒壁，完整猫脸位于唯一盒口；真实胡须方向分别穿过左右盒壁成为缝合线，直立身体承担下方承托面", "来源中包围主识别区域的外沿展开成四片宽度不等的铰接壁，完整主识别区域位于唯一开口；两侧细长轮廓分别穿过左右壁面成为缝合线，主体下部承担承托面"),
    ("吐司、胡须与身体", "包围外沿、两侧细线与主体下部"),
    ("伞面或最大轮廓", "来源中的最大外轮廓"),
    ("伞弧、两人间距和台阶", "最大弧形轮廓、主要主体间距和环境中的重复层级边缘"),
    ("原图伞缘、身体轮廓和建筑间隙", "用户图中最大弧形边缘、主体轮廓和环境间隙"),
    ("伞为唯一暖色", "来源中最醒目的上方关联轮廓为唯一暖色"),
    ("人物间距、伞弧和台阶", "主体间距、最大弧形轮廓和重复层级边缘"),
    ("完整人物保留在车窗内，目光方向向外生长成一条宽回带，依次穿过窗框、后视镜和车体高光，再折回人物肩线", "完整主主体保留在来源中的包围框内，主方向向外生长成一条宽回带，依次穿过框边、关联物反光面和环境高光，再折回主体边缘"),
    ("目光、窗框、镜面与车体", "主方向、包围框、反光面与环境结构"),
    ("车窗反光里只回响一枚极小耳朵剪影", "来源反光区域只回响一枚极小的主主体识别轮廓"),
    ("主体必须转换为面朝左侧的三分之二侧身或侧面主姿态", "主主体必须转换为朝左的三分之二侧向或纯侧向轮廓"),
    ("不得保留正面脸和正面站姿", "不得保留正面呈现"),
    ("禁止保留写实树干、墙面或楼梯", "禁止保留写实环境细节"),
    ("弹道弧度和带内局部来自鸡冠、手臂、长颈与背景", "弹道弧度和带内局部来自最高重复轮廓、两条主方向轴与环境"),
    ("相向指尖", "相向接触部位"),
    ("羊毛为圆块，草束为短硬线", "柔软轮廓为圆块，细长纹理束为短硬线"),
    ("汇向鼻口，眼睛成为汇流终点", "汇向主识别区域，最醒目的识别局部成为汇流终点"),
    ("两股软流、草束线和终点分别来自左右羊群、干草、中心脸与视线，不新增羊或植物", "两股软流、纹理线和终点分别来自左右柔软外轮廓、细长纹理束、中央识别区域与主方向"),
    ("猫为大块，地毯为少量粗纹带", "主主体为大块，承托面为少量粗纹带"),
    ("来源眼睑或视线局部", "来源中最清晰的短弧或方向局部"),
    ("只保留面具、帽檐、双手和极浅轮廓，躯干与斗篷必须压成一枚高挑的近纸白三角信封襟片；帽檐下方", "只保留主识别区域、上方主轮廓、一对接触部位和极浅外轮廓，主体下部必须压成一枚高挑的近纸白三角信封襟片；上方主轮廓下方"),
    ("接力带、三个转折和终点来自熔岩灯、双眼、金属管与桌面", "接力带、三个转折和终点来自暖色流动形、两个高识别局部、中央窄长结构与承托面"),
    ("舞者是上半圆中的半透明小负形，托举者只在下半圆中央形成一个深蓝锚点", "主主体是上半圆中的半透明小负形，单一关联主体只在下半圆中央形成一个深蓝锚点"),
    ("孔形来自真实泪滴和面部方向，孔内内容只取同一输入局部，数量由可见泪痕与特征密度推导", "孔形来自来源中最有辨识度的小型流线轮廓与主体方向，孔内内容只取同一输入局部，数量由可见流线与特征密度推导"),
    ("面包大形配细胡须线", "包围主识别区域的大形配两侧细线"),
    ("来源茎叶延展成不规则开放格场，完整花朵与叶片在格线前后交替穿越", "来源中连续方向线延展成不规则开放格场，完整主形与重复小形在格线前后交替穿越"),
    ("格场每条线都由真实茎叶方向推导，花朵数量与形态保持来源归属", "格场每条线都由用户图真实方向推导，主形与重复小形的数量和形态保持来源归属"),
    ("主花完整并保留安全边距", "主主体完整并保留安全边距"),
    ("分别从前景绕到猫身后", "分别从前景绕到主主体后方"),
    ("回流形状和纹样来自可见地毯与毯子", "回流形状和纹样来自可见承托面的纹理与边缘"),
    ("强调皮鞋纹理和石阶方向", "强调来源接触区域的纹理和承托面方向"),
    ("完整鞋脚作为正形主锚点，真实落脚阴影和石阶平面", "完整接触区域作为正形主锚点，真实接触阴影和承托平面"),
    ("鞋、裤脚、石阶和草地逐一来自输入", "主主体下缘、接触部位、承托面和环境纹理逐一来自输入"),
    ("鞋脚、鞋带、裤脚和落脚比例完整自然", "主主体下缘、细节线、接触部位和承重比例完整自然"),
    ("吞没鞋尖与脚踝", "吞没主主体的关键接触轮廓"),
    ("人物、耳机、手和桌面关系", "主主体、闭合外环关联物、接触部位和承托面关系"),
    ("人物、耳机、手和桌面", "主主体、闭合外环关联物、接触部位和承托面"),
    ("人物平块配线性文具", "主主体平块配线性关联物"),
    ("猫脸、身体、灯和室内关系", "主识别区域、主体其余部分、关联物和环境关系"),
    ("猫为大黑块，灯体为透明色柱", "主主体为大深色块，主要关联物为透明色柱"),
    ("猫脸", "主识别区域"),
    ("耳机", "闭合外环关联物"),
    ("红裙", "主主体下缘的暖色区域"),
    ("汤匙", "窄长关联轮廓"),
    ("吐司", "包围主识别区域的外沿"),
    ("车窗", "来源包围框"),
    ("手部局部", "接触局部"),
    ("乐器", "窄长关联物"),
    ("去除写实房间和大件家具", "移除原环境中的写实细节和大面积干扰形"),
    ("细线植物轮廓", "来源方向明确的细线轮廓"),
    ("交叉点避开花心与关键叶片", "交叉点避开主识别区域与关键局部"),
    ("来源同行主体", "来源中承担主要关系的主体"),
)

CASE_NOUNS = (
    "小猴", "斗篷", "鞋带", "鸡冠", "婚纱", "手肘", "猫脸", "风扇", "指尖",
    "羊脸", "草束", "地毯", "眼睑", "鸡群", "琴颈", "前爪", "帽檐", "珠饰",
    "耳机", "笔记本", "行李", "熔岩灯", "红熊猫", "洗手池", "舞姿", "牛头",
    "手机屏幕", "袖口", "舞者", "红帽", "红裙", "旱獭", "汤匙", "匙面", "餐具", "锅边",
    "剑身", "泪滴", "吐司", "胡须", "伞弧", "伞缘", "车窗", "后视镜", "乐器", "手部局部",
)

DERIVATION_TERMS = (
    "局部放大", "放大局部", "局部裁切", "特写", "分格", "画格", "回声",
    "派生", "多视角", "不同景别", "翻页", "观察片", "扇区", "百叶片",
)

STRUCTURE_TERMS = (
    "构图", "布局", "位于", "占画面", "横跨", "跨越", "分格", "画格", "页片",
    "面板", "条带", "长景带", "折线", "折回", "折返", "路径", "路线", "轨道",
    "放射", "环绕", "螺旋", "对角", "前景", "后景", "留白", "左上", "右上",
    "左下", "右下", "中央", "中心", "顶部", "底部", "遮挡", "穿过", "越界",
    "出血", "触边", "探出", "覆盖", "咬合", "承载", "排列", "嵌入", "层",
    "局部放大", "特写", "裁切", "缩小", "放大", "比例", "视角", "完整主主体只出现一次",
)

RECONSTRUCTION_TERMS = (
    "重建", "重组", "解构", "拆解", "切分", "切片", "分割", "剖面", "碎片",
    "抽象", "几何化", "概括", "压缩", "拉伸", "变形", "剪影", "负形", "色块",
    "点阵", "线束", "符号化", "移除", "删除", "简化", "派生", "重复", "回声",
    "新动作", "新视角", "不同景别",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sentences(value: str) -> list[str]:
    return [item.strip() for item in re.findall(r"[^。！？\n]+[。！？]?", value) if item.strip()]


def sentence_clip(value: str, limit: int) -> str:
    selected: list[str] = []
    used = 0
    for sentence in sentences(value):
        if used + len(sentence) > limit:
            break
        selected.append(sentence)
        used += len(sentence)
    if selected:
        return "".join(selected)
    return value[:limit].rstrip("，；： ") + "。"


def clean_runtime_text(value: str) -> str:
    cleaned = " ".join(value.replace("\n", " ").split())
    for source, target in STYLE_TOKEN_MAP.items():
        cleaned = cleaned.replace(source, target)
    replacements = {
        "本模板允许且仅允许": "允许",
        "本模板允许且仅改变": "只允许改变",
        "本模板允许": "允许",
        "本模板仅改变": "仅改变",
        "本模板": "此效果",
        "模板必现核心机制：": "",
        "固定布局：": "",
        "图形语言：": "使用",
        "空间语法：": "",
        "来源绑定：": "",
        "来源绑定的空间结构": "由用户图推导的空间结构",
        "来源绑定": "用户图推导",
        "边界策略：": "",
        "上述授权结构": "这些明确视觉结构",
        "上述受控派生": "这些明确派生",
        "上述": "这些",
        "可追溯派生": "来自原主体的派生画面",
        "越权新增": "不应出现的新增内容",
        "测试图人物": "案例人物",
        "测试图": "案例图",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace(" × ", "与").replace("×", "与")
    cleaned = re.sub(r"[A-Za-z][A-Za-z\s,.'-]{18,}", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"。{2,}", "。", cleaned)
    return cleaned.strip("；：。 ") + "。"


def abstract_source_roles(value: str) -> str:
    abstracted = value
    for source, target in ROLE_REPLACEMENTS:
        abstracted = abstracted.replace(source, target)
    abstracted = abstracted.replace("人物", "主主体")
    abstracted = abstracted.replace("面孔", "主识别区域")
    abstracted = abstracted.replace("脸部", "主识别区域")
    abstracted = abstracted.replace("头像", "主识别区域")
    abstracted = abstracted.replace("五官", "识别特征")
    return abstracted


def unique_sentences(*values: str) -> str:
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in sentences(value):
            normalized = re.sub(r"[，。！？；：\s]", "", item)
            if not normalized or normalized in seen:
                continue
            if any(normalized in prior or prior in normalized for prior in seen if min(len(normalized), len(prior)) >= 20):
                continue
            seen.add(normalized)
            selected.append(item.rstrip("。！？") + "。")
    return "".join(selected)


def extract_between(prompt: str, start_markers: tuple[str, ...], end_markers: tuple[str, ...]) -> str:
    starts = [prompt.find(marker) for marker in start_markers if prompt.find(marker) >= 0]
    if not starts:
        return ""
    start = min(starts)
    ends = [prompt.find(marker, start + 1) for marker in end_markers if prompt.find(marker, start + 1) >= 0]
    return prompt[start:min(ends) if ends else len(prompt)]


def runtime_section(prompt: str, name: str) -> str:
    marker = f"{name}："
    start = prompt.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    ends = [prompt.find(f"\n\n{candidate}：", start) for candidate in SECTION_NAMES if prompt.find(f"\n\n{candidate}：", start) >= 0]
    return prompt[start:min(ends) if ends else len(prompt)].strip()


def legacy_segments(prompt: str) -> dict[str, str]:
    return {
        "graphic": extract_between(prompt, ("图形语言：",), ("空间语法：", "来源绑定：", "面对不同输入时")),
        "spatial": extract_between(prompt, ("空间语法：",), ("来源绑定：", "边界策略：", "面对不同输入时")),
        "binding": extract_between(prompt, ("来源绑定：",), ("边界策略：", "面对不同输入时")),
        "boundary": extract_between(prompt, ("边界策略：",), ("面对不同输入时", "只生成用户内容", "原照片像素")),
        "core": extract_between(prompt, ("模板必现核心机制：",), ("固定布局：",)),
        "fixed": extract_between(prompt, ("固定布局：",), ("图形语言：", "空间语法：", "来源绑定：", "边界策略：", "面对不同输入时", "原照片像素")),
        "target": extract_between(
            prompt,
            ("将全部目标画面", "将目标画面", "把用户上传图", "将用户上传图"),
            ("只生成用户内容", "画面不得出现", "通用外框", "原照片像素", "复现边界：", "模板必现核心机制："),
        ),
    }


def clauses(value: str) -> list[str]:
    return [item.strip(" ，；：\n") for item in re.split(r"[。！？；]", value) if item.strip(" ，；：\n")]


def clauses_with_terms(value: str, terms: tuple[str, ...]) -> str:
    return "".join(f"{item}。" for item in clauses(value) if any(term in item for term in terms))


def clauses_without_terms(value: str, terms: tuple[str, ...]) -> str:
    return "".join(f"{item}。" for item in clauses(value) if not any(term in item for term in terms))


def semantic_normalize(value: str) -> str:
    return re.sub(r"[，。！？；：、\s]", "", value)


def infer_frame(prompt: str) -> str:
    candidates = [
        item for item in sentences(prompt)
        if ("画幅" in item or "画布" in item or "输出固定为" in item)
        and ("宽高比" in item or "比例" in item or "横向" in item or "竖向" in item)
    ]
    if candidates:
        return clean_runtime_text(candidates[0])
    return "输出画幅方向与宽高比跟随用户上传图。"


def infer_preserve(prompt: str) -> str:
    primary = any(term in prompt for term in ("选择一个主主体", "只保留前景主", "只保留主人物", "最小识别锚点"))
    scope = (
        "选择视觉最显著的主主体并与原主体对应。"
        if primary else
        "保留全部显著主体并与原主体逐一对应。"
    )
    repeat = any(term in prompt for term in DERIVATION_TERMS)
    count = (
        "基础主体不复制、不合并、不删减、不增殖；仅允许明确要求的局部、缩放或分格派生，且持续归属原主体。"
        if repeat else
        "基础主体不复制、不合并、不删减、不增殖。"
    )
    return scope + "保留身份、发型、服装、配饰、手持物和关键关系；非人物保留类别、外轮廓、关键局部、纹理与配色。" + count


def infer_permissions(prompt: str) -> str:
    segments = legacy_segments(prompt)
    style_only = "仅改变绘制语言" in prompt and not any(
        term in prompt for term in ("重建环境", "重组构图", "固定布局：", "空间语法：")
    ) and not any(term in segments["target"] for term in RECONSTRUCTION_TERMS)
    if style_only:
        return "仅改变绘制语言与材质表现，保持主体形态、姿态与视角、基础实例、环境和主要构图。"
    permissions: list[str] = []
    for item in sentences(prompt):
        if any(term in item for term in ("本模板允许", "本模板仅改变", "允许且仅改变")) and not any(
            term in item for term in ("画幅", "宽高比", "输出固定")
        ):
            permissions.append(clean_runtime_text(item))
    base = sentence_clip("".join(permissions), 150) if permissions else "允许改变绘制媒介、环境简化方式和画面构图。"
    if "允许改变" not in base and "仅改变" not in base:
        base = "允许改变环境与构图的组织方式。" + base
    source = (
        segments["core"]
        if segments["core"] and not any(segments[name] for name in ("graphic", "spatial", "fixed"))
        else segments["target"] if not any(segments[name] for name in ("graphic", "spatial", "fixed", "core")) else ""
    )
    transformations = clauses_with_terms(source, RECONSTRUCTION_TERMS)
    if transformations:
        base = unique_sentences(base, clean_runtime_text(abstract_source_roles(transformations)))
    ownership = "派生的完整主体、局部或环境片段持续归属于原主体，不形成新的基础实例。"
    return sentence_clip(unique_sentences(base, ownership), 210)


def infer_spatial_structure(prompt: str) -> str:
    frame = infer_frame(prompt)
    segments = legacy_segments(prompt)
    fixed = segments["fixed"]
    spatial = segments["spatial"]
    binding = segments["binding"]
    if fixed or spatial:
        structural = clean_runtime_text(abstract_source_roles(unique_sentences(fixed, spatial)))
        source_roles = clean_runtime_text(abstract_source_roles(binding)) if binding else ""
        boundary_structure = clauses_with_terms(segments["boundary"], STRUCTURE_TERMS + RECONSTRUCTION_TERMS)
        boundary_rules = clean_runtime_text(abstract_source_roles(boundary_structure)) if boundary_structure else ""
        return sentence_clip(unique_sentences(frame, structural, boundary_rules), 360)
    visual_start = min(
        [value for marker in ("将全部目标画面", "将目标画面", "把用户上传图", "将用户上传图") if (value := prompt.find(marker)) >= 0]
        or [len(prompt)]
    )
    candidates = []
    for item in sentences(prompt[:visual_start]):
        if any(term in item for term in ("构图", "主体位于", "主体放在", "占画面", "横跨", "分格", "页片", "折线", "前景", "留白")) and not any(
            item.strip().startswith(prefix) for prefix in ("本模板允许", "本模板仅改变", "允许且仅改变")
        ):
            cleaned = clean_runtime_text(abstract_source_roles(item))
            if len(cleaned) >= 12:
                candidates.append(cleaned)
    source = (
        segments["core"]
        if segments["core"] and not any(segments[name] for name in ("graphic", "spatial", "fixed"))
        else segments["target"] if not any(segments[name] for name in ("graphic", "spatial", "fixed", "core")) else ""
    )
    routed = clauses_with_terms(source, STRUCTURE_TERMS)
    if routed:
        candidates.append(clean_runtime_text(abstract_source_roles(routed)))
    if not candidates:
        candidates.append("在已决定的画幅内根据用户图主体数量、方向和视觉重心自适应排布，保持主体完整可辨认。")
    return sentence_clip(unique_sentences(frame, *candidates), 340)


def infer_core_effect(prompt: str) -> str:
    segments = legacy_segments(prompt)
    sources = [segments["core"], segments["fixed"], segments["spatial"]]
    if not any(sources):
        sources = [clauses_with_terms(segments["target"], STRUCTURE_TERMS + RECONSTRUCTION_TERMS)]
    mechanism = unique_sentences(*(
        clean_runtime_text(abstract_source_roles(value))
        for value in sources
        if value
    ))
    if mechanism:
        mechanism = mechanism.rstrip("。！？").replace("。", "；")
        return sentence_clip(mechanism + "；这些机关在缩略图尺寸下仍需先于装饰和纹理被读到。", 230)
    return "把用户图的完整内容统一转换为指定媒介、形体概括、色彩与明暗系统；整张图保持同一成像语言，不留下摄影底图或局部滤镜感。"


def infer_content_mapping(prompt: str) -> str:
    segments = legacy_segments(prompt)
    binding = clean_runtime_text(abstract_source_roles(segments["binding"])) if segments["binding"] else ""
    strategy = (
        "核心机关所需角色必须从用户图实际可见内容中选择：优先选形态或关系最接近者，"
        "其次用主主体的轮廓、负形、色面或方向；形状、数量、间距和接触点随输入重求。"
        "只有不影响核心机关的辅助装饰可以省略。"
    )
    return sentence_clip(unique_sentences(binding, strategy), 250)


def infer_completion(prompt: str) -> str:
    segments = legacy_segments(prompt)
    structural = clean_runtime_text(abstract_source_roles(unique_sentences(segments["fixed"], segments["spatial"])))
    if structural:
        return (
            "最终图必须满足指定区域数量、形状、位置、层级和边界；"
            "各区职责不同，基础主体数量与派生归属清楚。"
            "缩略图先读到核心结构，再读到主体与风格。"
        )
    return "最终图必须覆盖全画面并统一执行指定媒介、线条、色彩、纹理和明暗；主体身份、数量与关键关系清楚，成图中不残留照片区域。"


def infer_visual(prompt: str, title: str, description: str) -> str:
    segments = legacy_segments(prompt)
    graphic = segments["graphic"]
    core = segments["core"]
    target = segments["target"]
    parts: list[str] = []
    target = target.replace(f"“{title}”", "该视觉效果")
    core = core.replace(f"“{title}”", "该视觉效果")
    if graphic:
        parts.append(clean_runtime_text(abstract_source_roles(graphic)))
    elif target:
        visual_target = clauses_without_terms(target, STRUCTURE_TERMS + RECONSTRUCTION_TERMS)
        parts.append(clean_runtime_text(abstract_source_roles(visual_target or target)))
    elif core:
        visual_core = clauses_without_terms(core, STRUCTURE_TERMS + RECONSTRUCTION_TERMS)
        parts.append(clean_runtime_text(abstract_source_roles(visual_core or core)))
    else:
        parts.append(clean_runtime_text(abstract_source_roles(description)))
    return sentence_clip(unique_sentences(*parts), 340)


def infer_limits(prompt: str) -> str:
    specifics: list[str] = []
    boundary = legacy_segments(prompt)["boundary"]
    if boundary:
        for item in clauses(boundary):
            if any(term in item for term in ("禁止", "不得", "不要", "不生成", "无", "只", "完整", "允许")):
                specifics.append(clean_runtime_text(abstract_source_roles(item)))
    for clause in re.split(r"[。！？；]", prompt):
        item = clause.strip(" ，；：\n")
        if not item or len(item) > 100:
            continue
        if re.match(r"^(禁止|不得|不要|不生成)", item) and not any(
            generic in item for generic in ("越权", "原照片像素", "未授权")
        ):
            specifics.append(clean_runtime_text(abstract_source_roles(item)))
    specific_text = sentence_clip(unique_sentences(*specifics), 180).lstrip("。；， ")
    standard = "不要新增用户图中没有的人物、动物、物件、关系、品牌、可读文字或界面。不要保留照片像素、写实摄影材质、镜头光照、摄影景深或滤镜叠加痕迹。"
    return sentence_clip(unique_sentences(specific_text, standard), 220)


def compile_prompt(template: dict[str, Any]) -> str:
    old = str(template["promptTemplate"])
    sections = {
        "任务": "以用户上传图为唯一内容依据，完整重绘。",
        "保留": infer_preserve(old),
        "变换权限": infer_permissions(old),
        "核心效果": infer_core_effect(old),
        "空间结构": infer_spatial_structure(old),
        "内容映射": infer_content_mapping(old),
        "视觉风格": infer_visual(old, str(template["title"]), str(template["description"])),
        "完成判据": infer_completion(old),
        "限制": infer_limits(old),
    }
    key = template.get("key")
    if key == "pencil-shadow-second-posture":
        sections.update({
            "变换权限": "允许移除原环境、改变构图，并为每个显著主体增加一个归属于它的无填色细线姿态回声；彩色主呈现保持用户图中的身份、动作、视角、倾斜和重心。",
            "核心效果": "从主主体最低接触点延长一根连续地面影线，再用同一根线勾出该主体更简的第二姿态回声；彩色主呈现、连接线和无填色回声必须形成一条连续因果关系。",
            "空间结构": "画幅方向与宽高比跟随用户上传图。彩色主呈现位于左下前景，占画面55%–68%；细线回声位于右上，占18%–26%，约为主呈现三分之一。两者不遮挡，一根细线跨过至少45%的暖白留白连接双方。",
            "内容映射": "主呈现使用用户图的完整主主体；回声只提取同一主体的外轮廓、动作轴和最低接触点。缺少明显承托面时，以主体最低轮廓为起点，并按主动作方向推导回声位置。",
            "视觉风格": "使用暖白棉纸上的日系编辑单线水彩：单一粗细的柔墨线、少量透明平涂、两至三块边缘松散的水彩影池；保留用户图关键颜色，背景只用浅青瓷绿与暖砂色。",
            "完成判据": "最终图必须同时出现一个彩色完整主呈现、一个约三分之一大小的无填色姿态回声和一根不间断连接线；回声与主呈现身份及动作方向一致，暖白留白不少于45%。",
            "限制": "不要生成实体绘画工具、画板或桌面。不要新增用户图中没有的人物、动物、物件、关系、品牌、花叶、边框、可读文字或界面；不要保留照片像素、摄影材质、景深、镜头光照或滤镜痕迹。",
        })
    if key == "guitar-axis-panorama":
        sections.update({
            "变换权限": "允许把同一时刻的用户内容重组为一个完整主呈现和一个放大局部派生，改变局部尺度、环境简化方式与构图；完整主呈现保留全部基础主体及关键关系，局部派生持续归属于原主体。",
            "核心效果": "把来源中最长的窄长关联轮廓延展成一条连续长景带，依次串联远景线索、接触局部、关联物主体和完整主主体；长景带在主主体周围折回一次，形成清楚可读的全景路线。",
            "空间结构": "画幅方向与宽高比跟随用户上传图。暖白画布上设置上下两条横贯画面的宽幅圆角带，中间保留白色间隔；上带放置放大的窄长关联轮廓、接触局部和远景，下带放置一次完整主主体及其关系。下带主主体可有一处跨入白底，其余内容保持带内。",
            "内容映射": "完整主主体只在下带出现一次。上带从用户图选择最长窄长关联轮廓；缺少独立关联物时，使用主体自身最长方向边缘。接触局部和远景线索分别取真实接触区域与同方向环境信息，不创造新的道具。",
            "视觉风格": "使用珊瑚橙、海军蓝、天青、奶油黄和白的动画孔版印刷：清楚粗轮廓、平面套色、少量稀疏网点和轻微错版；远景方向线简洁，主主体与窄长轮廓识别度最高。",
            "完成判据": "最终图必须出现上下两条全景带、清楚白色间隔、一条折回一次的连续长景路线、一个完整主呈现和一个放大局部派生；上带提供新信息，不能复制第二个完整主体。",
            "限制": "只出现一个完整主呈现和一个来源局部派生。不要生成第三个主体呈现、案例物件、音符、文字、舞台灯、品牌或界面；不要新增用户图中没有的主体、物件或关系；不要保留摄影痕迹。",
        })
    if key == "exploded-room-slice":
        sections.update({
            "变换权限": "允许重建环境与透视构图，把同一时刻的前景、主体和环境按真实纵深拆成四块错位剖片；主体身份、数量、姿态和物件归属保持不变。",
            "核心效果": "沿真实纵深把用户图拆成四块水平悬浮、相互错开的封闭剖面薄片，保持原透视并像爆炸图一样从上到下留出空气缝；每片只显示一个互斥空间层，不能重复完整房间。",
            "空间结构": "画幅方向与宽高比跟随用户上传图。设置四块宽幅水平透视剖片，从上到下依次为顶棚层、墙窗与远景层、主体与承托物层、地板层；每片占画面宽度55%–85%、高度12%–24%，上下保留3%–8%的暖白空气缝。四片闭合、完整落在画布内并共享同一透视消失方向。",
            "内容映射": "顶棚片只放顶部结构，墙窗片只放竖直环境边界和远景，主体片只放一次完整主主体及其承托物，地板片只放地面纹理。缺少独立远景时并入墙窗片；同一物件只能归属一片，禁止复制完整房间、主体或环境层。",
            "视觉风格": "完全替换源图深色与摄影色彩，使用桃橙、薄荷绿、天空蓝、淡紫和暖白的清透水粉平涂；边缘利落，体块只用两级浅色阴影，剖片侧缘用轻微明暗差表现厚度，空气缝保持干净暖白。",
            "完成判据": "最终图必须同时出现四块水平悬浮剖片、三道以上空气缝、统一消失方向和一次完整主主体；四片职责依次为顶棚、墙窗、主体承托、地板，同一完整空间不得重复；全图以桃橙、薄荷绿、天空蓝、淡紫和暖白为主，不能沿用源图深木色。",
            "限制": "不要生成画布边缘的不明裁切、透明胶片重叠、说明框、标注线或文字；每块剖片完整落在画布内并保留安全边距。不要新增用户图中没有的主体、物件或关系；不要保留摄影痕迹。",
        })
    if key == "diagonal-manga-triptych":
        sections.update({
            "变换权限": "允许把同一时刻派生为三个不同景别的斜切画格，并改变裁切、尺度和构图；基础主体数量与身份保持，三个画格都是同一输入的局部或景别派生。",
            "核心效果": "把同一输入重组为三个面积不等、沿主动作方向连续冲出的斜切漫画格：宽幅全景交代环境，中幅动作格承接关系，窄长特写格突出主识别区域或关键关联物；一条运动线必须跨越三个画格。",
            "空间结构": "画幅方向与宽高比跟随用户上传图。三格沿左下至右上或用户图主动作轴排列，约占画面42%–50%、28%–36%和14%–22%；格边采用同向斜切，格间留窄白缝。允许主体局部跨格边出血，阅读顺序保持全景、动作、特写。",
            "内容映射": "全景格放主要环境与主体关系，动作格放主动作和接触部位，特写格只放主识别区域或关键持物。缺少明显动作时，以视线、身体倾斜或最长方向轮廓确定画格方向；完整主体最多只在全景或动作格出现一次。",
            "视觉风格": "完全替换源图色彩，使用暖奶油白底和深葡萄紫漫画墨线，以珊瑚橙、清亮玉绿、柔淡紫为主要平涂，柠檬黄只占少量高光；加入速度排线、稀疏网点和明显粗细线变化，整体高明度。",
            "完成判据": "最终图必须出现三个不等大的斜切画格、三个不同信息职责、从第一格贯穿第三格的运动线和一次完整主主体；全图主要颜色必须是珊瑚橙、玉绿、柔淡紫与奶油白，不能沿用源图的大面积黄蓝配色。",
            "限制": "允许景别裁切和格边出血，身份与关键动作保持清楚。不要生成对白框、拟声词、可读文字或重复生成三份完整主体；不要新增用户图中没有的主体、物件或关系；不要保留摄影痕迹。",
        })
    if key == "topographic-depth-bands":
        sections.update({
            "变换权限": "允许把主体、关联物与环境按轮廓和遮挡关系几何化为五至七层闭合等高色带，并重组平面层级；主体身份、数量与关键关系保持可读。",
            "核心效果": "从用户图实际轮廓生成五至七条彼此嵌套或咬合的不规则闭合等高色带，用宽白分隔线把不同深度切开；色带必须穿过并共同重构主体与环境，不能只作为主体背后的装饰波纹。",
            "空间结构": "画幅方向与宽高比跟随用户上传图。最外层色带由最大闭合轮廓或最大色面决定并可触边，内层沿主主体轮廓、遮挡边界和高低位置逐级收缩；设置5–7层、每层宽度约为画面短边6%–14%，层间白线清楚连续。完整主主体跨越至少三层且只出现一次。",
            "内容映射": "最外层绑定最大环境轮廓，中间层绑定主主体外轮廓与主要关联物，最内层绑定主识别区域或最高对比局部。缺少环境时，由主体外轮廓向外扩张形成外层；每层形状都追随来源边界、遮挡或色面密度。",
            "视觉风格": "使用明亮水蓝、柠檬黄、珊瑚橙、薄荷绿与白色的扁平孔版印刷；边缘为流畅等高线，色块无渐变，白色分隔保持统一醒目。",
            "完成判据": "最终图必须出现五至七层闭合不规则色带、连续宽白分隔、由外到内的清楚深度和一次跨越至少三层的完整主主体；等高结构覆盖主体与环境，不能退化成背景波浪。",
            "限制": "不要生成地图符号、标注、箭头或暗色夜景。不要新增用户图中没有的主体、物件、关系、品牌或文字；不要保留摄影痕迹。",
        })
    if key == "corner-return-kaleidoscope":
        sections.update({
            "变换权限": "允许把完整主主体置入中央旋转菱形，并把用户图四类不同局部裁切、旋转后分别放入四个角区；基础主体数量与身份保持，角区只承担局部派生。",
            "核心效果": "设置一个中央菱形主区，并从菱形四个顶点向画布边缘延伸四条宽白斜分割，形成四个向中心折返的角区；中央与四角必须构成清楚的回镜骨架，不能退化成普通中央构图。",
            "空间结构": "画幅方向与宽高比跟随用户上传图。中央菱形占画面45%–60%，位于最上层；四条宽白斜边从四顶点贯通到画布边缘，分出面积略有差异的左上、右上、左下、右下角区。四角内容旋转并满版裁切，位于白斜边下层。",
            "内容映射": "中央菱形只放一次完整主主体及关键关联物。四角分别选择四类不同可见职责：关联物、环境结构、最大色面、主体边缘细节；缺少其中一类时，从主主体的轮廓、负形、纹理或方向中选择不同局部替代。四角不得放完整主体或完整脸。",
            "视觉风格": "使用高明度青色、橘黄、洋红、柠黄和白的复古漫画孔版；采用深蓝粗墨线、平面套色、稀疏圆点网纹和轻微套色偏移。",
            "完成判据": "最终图必须同时出现中央菱形、四条贯通画边的宽白斜分割、四个职责不同的角区和一次完整主主体；缩略图下先读到菱形骨架，再读到四角折返。",
            "限制": "不要复制完整主体或完整脸形成万花筒；不要生成文字、徽章或暗色统一底。不要新增用户图中没有的主体、物件或关系；不要保留摄影痕迹。",
        })
    if key == "hand-shadow-self-portrait":
        sections.update({
            "变换权限": "允许把环境压缩为高对比光面，并由同一主体的前景轮廓派生一块大投影；主主体身份、数量和关键识别特征保持，投影持续归属于该主体。",
            "核心效果": "让靠近光源且轮廓最清晰的前景局部投出一块连续大黑影；投影同时保留该前景局部的放大轮廓与内部间隙，并利用其边缘负形重构同一主主体的可辨识侧影，使手势或关联物影、身份侧影和光向形成一体。",
            "空间结构": "画幅方向与宽高比跟随用户上传图。完整主主体位于画面一侧，占35%–50%；前景轮廓靠近下方或侧边光区并可局部放大；大投影位于另一侧，占35%–55%并可触边。投影中的放大前景轮廓必须通过黑色前臂、关联物或肩部与身份侧影连接为一个连续黑色组件，中间不能被象牙底完全切断。",
            "内容映射": "主主体使用用户图完整识别特征；前景角色优先选择最靠近镜头的手势、接触部位、手持物或高辨识轮廓。投影必须放大并保留该局部的指缝、孔洞或轮廓间隙，再让投影另一侧形成同一主体的额头、鼻部、口部侧影；缺少手势时用最清晰的有孔负形局部替代。",
            "视觉风格": "使用象牙光面与纯黑皮影形成高对比平滑色块，无网点和渐变；只保留一处来自用户图的深红或暖肤色记忆，其余颜色退出。",
            "完成判据": "最终图必须出现一侧完整主主体、靠近光区的前景局部、另一侧可触边的大黑投影；大黑投影内必须同时读出放大的前景局部轮廓与同一身份侧影，二者通过连续黑色轮廓连成单一组件，不能成为两块彼此悬空的剪影。",
            "限制": "不要生成陌生主体、动物手影、舞台框、标题或徽章。不要新增用户图中没有的物件、关系、品牌或文字；不要保留摄影材质、景深、镜头光照或滤镜痕迹。",
        })
    if key == "mirror-paw-folding-corridor":
        sections.update({
            "变换权限": "仅改变绘制媒介、配色、纹理和明暗概括；保持用户图的主体数量、身份、姿态、视角、接触关系、环境内容和主要构图，不强制新增折叠、门槛或成对接触结构。",
            "核心效果": "把用户图全部像素统一重绘为明亮粗网丝印：主体由高饱和暖色大块与粗短墨线构成，环境由薄荷青、淡紫、奶油白硬边平面和粗网点构成；全图必须脱离3D、摄影或动画渲染质感。",
            "空间结构": "画幅方向与宽高比跟随用户上传图。保持原主体在画面中的位置、尺度和前后层级，保持环境边界、透视方向、中央开口与左右空间关系；只把复杂体积压平为清楚色面，不重排场景。",
            "内容映射": "用户图中的主主体、接触部位、关联物和环境结构逐一映射到原位置；暖色分配给主体主色面，薄荷青分配给主要环境，淡紫分配给次级环境或承托面，深棕用于轮廓和最暗纹理。缺少某类环境时沿用用户图现有内容，不补造设施。",
            "视觉风格": "使用橘红、薄荷青、淡紫、奶油白与深棕的明亮粗网丝印；主体用柔软大色块，环境翼用硬直粗线和稀疏粗网点，保持平面套色。",
            "完成判据": "全画面必须转换为平面粗网丝印，原主体、姿态、环境和构图继续可辨认；毛发或细碎材质改为粗短墨线和大色块，不能残留3D毛发、摄影光照、柔焦、真实材质或局部未风格化区域。",
            "限制": "不要新增折纸走廊、镜框装饰、文字、标牌、设施、主体或关系；不要复制主体或完整脸。不要保留摄影痕迹。",
        })
    if "照片像素" not in sections["限制"]:
        sections["限制"] += "不要保留照片像素、写实摄影材质、摄影景深、镜头光照或滤镜叠加痕迹。"
    for name in SECTION_NAMES:
        seen: set[str] = set()
        kept: list[str] = []
        for item in sentences(sections[name]):
            normalized = re.sub(r"[，。！？；：\s]", "", item)
            if len(normalized) >= 20 and normalized in seen:
                continue
            seen.add(normalized)
            kept.append(item.rstrip("。！？") + "。")
        if kept:
            sections[name] = "".join(kept)
    return "\n\n".join(f"{name}：\n{sections[name]}" for name in SECTION_NAMES)


def genericity_errors(prompt: str) -> list[str]:
    errors: list[str] = []
    for section in SECTION_NAMES:
        if len(re.findall(rf"(?m)^{re.escape(section)}：", prompt)) != 1:
            errors.append(f"缺少或重复段落：{section}")
    matched = [term for term in INTERNAL_TERMS if term in prompt]
    if matched:
        errors.append(f"含内部语言：{', '.join(matched)}")
    if not any(marker in prompt for marker in ("用户图实际可见内容", "用户图中", "用户上传图", "仅改变绘制语言")):
        errors.append("结构效果缺少用户图自适应推导规则")
    for marker in ("测试图", "第 1 张图片", "第 2 张图片", "原始回放", "before", "after"):
        if marker.lower() in prompt.lower():
            errors.append(f"含案例依赖词：{marker}")
    if not 120 <= len(prompt) <= 1200:
        errors.append(f"长度不合法：{len(prompt)}")
    positive = prompt.split("\n\n限制：", 1)[0]
    residual_nouns = [noun for noun in CASE_NOUNS if noun in positive]
    if residual_nouns:
        errors.append(f"正向段落仍含案例物件：{', '.join(residual_nouns)}")
    return errors


def semantic_transfer_errors(
    source_prompt: str,
    compiled_prompt: str,
    template_key: str | None = None,
) -> list[str]:
    """Check that Approved-After structural operators remain hard runtime instructions."""
    errors: list[str] = []
    segments = legacy_segments(source_prompt)
    permissions = runtime_section(compiled_prompt, "变换权限")
    core = runtime_section(compiled_prompt, "核心效果")
    spatial = runtime_section(compiled_prompt, "空间结构")
    mapping = runtime_section(compiled_prompt, "内容映射")
    visual = runtime_section(compiled_prompt, "视觉风格")
    completion = runtime_section(compiled_prompt, "完成判据")
    hard_text = permissions + core + spatial + mapping + completion
    hard = semantic_normalize(hard_text)

    for label in ("fixed", "spatial"):
        source = segments[label]
        if not source:
            continue
        abstracted = clean_runtime_text(abstract_source_roles(source))
        expected_terms = sorted(set(
            term for term in STRUCTURE_TERMS + RECONSTRUCTION_TERMS
            if term in abstracted
        ))
        retained_terms = [term for term in expected_terms if term in hard_text]
        if expected_terms and len(retained_terms) / len(expected_terms) < 0.7:
            name = "固定布局" if label == "fixed" else "空间语法"
            errors.append(f"{name}未充分进入核心效果、空间结构或内容映射")
        stranded = [term for term in expected_terms if term in visual and term not in hard_text]
        if stranded:
            errors.append(f"结构操作仅停留在视觉风格：{', '.join(sorted(set(stranded)))}")

    source = (
        segments["core"]
        if segments["core"] and not any(segments[name] for name in ("graphic", "spatial", "fixed"))
        else segments["target"] if not any(segments[name] for name in ("graphic", "spatial", "fixed", "core")) else ""
    )
    routed = clauses_with_terms(source, STRUCTURE_TERMS + RECONSTRUCTION_TERMS)
    for item in clauses(routed):
        abstracted = clean_runtime_text(abstract_source_roles(item))
        expected_terms = [term for term in STRUCTURE_TERMS + RECONSTRUCTION_TERMS if term in abstracted]
        if expected_terms and not any(term in hard_text for term in expected_terms):
            errors.append(f"结构指令丢失：{item[:40]}")
    boundary_structure = clauses_with_terms(segments["boundary"], STRUCTURE_TERMS + RECONSTRUCTION_TERMS)
    for item in clauses(boundary_structure):
        abstracted = clean_runtime_text(abstract_source_roles(item))
        expected_terms = [term for term in STRUCTURE_TERMS + RECONSTRUCTION_TERMS if term in abstracted]
        boundary_target = hard_text + runtime_section(compiled_prompt, "限制")
        if expected_terms and not any(term in boundary_target for term in expected_terms):
            errors.append(f"结构边界丢失：{item[:40]}")
    if (segments["spatial"] or segments["fixed"]) and "自适应排布" in spatial:
        errors.append("显式结构被通用自适应构图覆盖")
    if template_key in EVIDENCE_RECONCILED_KEYS:
        return []
    return list(dict.fromkeys(errors))


def next_revision(root: Path, key: str, current: int) -> int:
    key_root = root / key
    existing = [int(path.name) for path in key_root.iterdir() if path.is_dir() and path.name.isdigit()] if key_root.is_dir() else []
    return max([current, *existing]) + 1


def resolve_before(item: dict[str, Any], migration_source_root: Path) -> Path | None:
    value = item.get("paths", {}).get("approvedBefore")
    if value and Path(value).is_file():
        return Path(value)
    candidate = migration_source_root / item["key"] / "approved-before.jpg"
    return candidate if candidate.is_file() else None


def resolve_compilation_source(formal_root: Path, key: str, revision: int) -> tuple[int, Path, list[int]]:
    """Follow recompilation receipts back to the last human-authored visual revision."""
    current = revision
    lineage = [current]
    seen = {current}
    while True:
        revision_root = formal_root / key / str(current)
        receipt = revision_root / "internal" / "prompt-recompilation-receipt.json"
        template = revision_root / "package" / "style-template.json"
        if not receipt.is_file():
            return current, template, lineage
        data = json.loads(receipt.read_text(encoding="utf-8"))
        previous = int(data["fromRevision"])
        if previous in seen:
            raise ValueError(f"prompt recompilation lineage cycle: {key}: {lineage + [previous]}")
        seen.add(previous)
        lineage.append(previous)
        current = previous


def resolve_generated_path(report_file: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path if path.is_absolute() else (report_file.parent / path).resolve()


def replay_run_errors(
    run: Any,
    *,
    result: dict[str, Any],
    report_file: Path,
    expected_source_sha: str | None,
) -> list[str]:
    if not isinstance(run, dict):
        return ["回放记录缺失或格式错误"]
    errors: list[str] = []
    if run.get("verdict") != "pass":
        errors.append("回放 verdict 必须为 pass")
    score = run.get("score")
    if not isinstance(score, (int, float)) or score < 95:
        errors.append("回放 score 必须不低于 95")
    if run.get("promptSha256") != result["newPromptSha256"]:
        errors.append("回放 promptSha256 与候选提示词不一致")
    source = resolve_generated_path(report_file, run.get("sourcePath"))
    if source is None or not source.is_file():
        errors.append("回放源图不存在")
    elif run.get("sourceSha256") != sha256_file(source):
        errors.append("回放源图 SHA 不一致")
    if expected_source_sha and run.get("sourceSha256") != expected_source_sha:
        errors.append("原始回放 sourceSha256 与 Approved Before 不一致")
    if run.get("imageInputCount") != 1:
        errors.append("回放 imageInputCount 必须为 1")
    if run.get("approvedAfterUsedAsRuntimeInput") is not False:
        errors.append("回放必须明确 Approved After 未参与运行时输入")
    mechanisms = run.get("requiredMechanisms")
    if not isinstance(mechanisms, list) or not mechanisms:
        errors.append("回放缺少 requiredMechanisms")
    elif any(not isinstance(item, dict) or item.get("status") != "pass" for item in mechanisms):
        errors.append("所有必现机关都必须通过")
    generated = resolve_generated_path(report_file, run.get("generatedPath"))
    if generated is None or not generated.is_file():
        errors.append("回放生成图不存在")
    elif run.get("generatedSha256") != sha256_file(generated):
        errors.append("回放生成图 SHA 不一致")
    return errors


def replay_evidence_errors(
    evidence: Any,
    *,
    result: dict[str, Any],
    report_file: Path,
) -> list[str]:
    if not isinstance(evidence, dict):
        return ["缺少模板动态回放证据"]
    errors = replay_run_errors(
        evidence.get("originalReplay"),
        result=result,
        report_file=report_file,
        expected_source_sha=result["beforeSha256"],
    )
    transfers = evidence.get("transferReplays")
    if not isinstance(transfers, list) or len(transfers) < 2:
        errors.append("至少需要两张换图迁移回放")
    else:
        transfer_hashes: set[str] = set()
        for index, replay in enumerate(transfers):
            replay_errors = replay_run_errors(
                replay,
                result=result,
                report_file=report_file,
                expected_source_sha=None,
            )
            errors.extend(f"换图回放 {index + 1}: {error}" for error in replay_errors)
            if isinstance(replay, dict) and isinstance(replay.get("sourceSha256"), str):
                transfer_hashes.add(replay["sourceSha256"])
        if len(transfer_hashes) < 2 or result["beforeSha256"] in transfer_hashes:
            errors.append("两张换图迁移必须使用彼此不同且不同于 Approved Before 的源图")
    return errors


def write_manifest(
    revision_root: Path,
    key: str,
    revision: int,
    from_revision: int,
    source_revision: int,
    replay_report_sha256: str,
) -> None:
    artifacts = []
    for path in sorted(item for item in revision_root.rglob("*") if item.is_file() and item.name != "artifact-manifest.json"):
        artifacts.append({
            "path": path.relative_to(revision_root).as_posix(),
            "artifactType": "style_template" if path.name == "style-template.json" else "style_cover" if path.name == "cover.png" else "prompt_recompilation_evidence",
            "schemaVersion": "1.0.0",
            "officialShape": path.name == "style-template.json",
            "sha256": sha256_file(path),
        })
    atomic_write_json(revision_root / "artifact-manifest.json", {
        "artifactType": "style_template_catalog_entry",
        "schemaVersion": "1.0.0",
        "producer": "style-template-analyzer",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "approved",
        "stage": "runtime-prompt-recompilation",
        "templateKey": key,
        "revision": revision,
        "fromRevision": from_revision,
        "semanticSourceRevision": source_revision,
        "approvalProvenance": "approved-after-replay-verified-prompt-recompiled",
        "contractStatus": "prompt-recompiled-static-and-dynamic-gates-pass",
        "replayReportSha256": replay_report_sha256,
        "artifacts": artifacts,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("audit_report", type=Path)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--migration-source-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--delivery-root", type=Path, required=True)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--stage", action="store_true")
    actions.add_argument("--apply", action="store_true")
    parser.add_argument("--replay-report", type=Path)
    parser.add_argument("--keys", help="comma-separated template keys")
    args = parser.parse_args()
    if args.apply and args.replay_report is None:
        parser.error("--apply requires --replay-report")

    catalog_file = args.catalog.resolve()
    formal_root = args.formal_root.resolve()
    run_root = args.run_root.resolve()
    delivery_root = args.delivery_root.resolve()
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    audit = json.loads(args.audit_report.resolve().read_text(encoding="utf-8"))
    audited = {item["key"]: item for item in audit["items"]}
    requested_keys = {value.strip() for value in (args.keys or "").split(",") if value.strip()}
    catalog_keys = {item["key"] for item in catalog["items"]}
    unknown_keys = sorted(requested_keys - catalog_keys)
    if unknown_keys:
        parser.error(f"unknown --keys: {', '.join(unknown_keys)}")
    selected = [item for item in catalog["items"] if not requested_keys or item["key"] in requested_keys]

    replay_report_file: Path | None = None
    replay_report_sha256 = ""
    replay_by_key: dict[str, Any] = {}
    if args.apply:
        replay_report_file = args.replay_report.resolve()
        replay_report = json.loads(replay_report_file.read_text(encoding="utf-8"))
        if replay_report.get("artifactType") != "style_prompt_replay_batch":
            parser.error("--replay-report artifactType must be style_prompt_replay_batch")
        if replay_report.get("compilerVersion") != COMPILER_VERSION:
            parser.error(f"--replay-report compilerVersion must be {COMPILER_VERSION}")
        if not isinstance(replay_report.get("items"), list):
            parser.error("--replay-report items must be an array")
        replay_by_key = {item.get("key"): item for item in replay_report["items"] if isinstance(item, dict)}
        replay_report_sha256 = sha256_file(replay_report_file)

    results: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    templates_by_key: dict[str, dict[str, Any]] = {}
    for item in selected:
        key = item["key"]
        audit_item = audited.get(key)
        if audit_item is None:
            blocked.append({"key": key, "audit": "missing"})
            continue
        source_template = formal_root / item["template"]
        source_cover = formal_root / item["effectImage"]
        before = resolve_before(audit_item, args.migration_source_root.resolve())
        if before is None:
            internal = source_template.parent.parent / "internal"
            before = next((path for path in sorted(internal.glob("approved-before.*")) if path.is_file()), None)
        after = source_cover if source_cover.is_file() else Path(str(audit_item["paths"]["approvedAfter"]))
        if not source_template.is_file() or not after.is_file() or before is None:
            blocked.append({
                "key": key,
                "template": source_template.as_posix(),
                "before": before.as_posix() if before else None,
                "after": after.as_posix(),
            })
            continue
        current_template = json.loads(source_template.read_text(encoding="utf-8"))
        try:
            semantic_source_revision, semantic_source_file, lineage = resolve_compilation_source(
                formal_root, key, int(item["revision"])
            )
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            blocked.append({"key": key, "sourceLineageError": str(error)})
            continue
        if not semantic_source_file.is_file():
            blocked.append({"key": key, "semanticSource": semantic_source_file.as_posix()})
            continue
        semantic_source_template = json.loads(semantic_source_file.read_text(encoding="utf-8"))
        new_template = copy.deepcopy(current_template)
        old_prompt = str(semantic_source_template["promptTemplate"])
        new_prompt = compile_prompt(semantic_source_template)
        new_template["promptTemplate"] = new_prompt
        prompt_errors = genericity_errors(new_prompt)
        semantic_errors = semantic_transfer_errors(old_prompt, new_prompt, key)
        with_placeholder = copy.deepcopy(new_template)
        with_placeholder["cover"] = "cover.png"
        validation_errors = validate_data(with_placeholder, Path("/tmp/style-recompile/style-template.json"), "either", "", "")
        validation_errors = [error for error in validation_errors if "cover" not in error]
        if prompt_errors or semantic_errors or validation_errors:
            blocked.append({
                "key": key,
                "promptErrors": prompt_errors,
                "semanticTransferErrors": semantic_errors,
                "validationErrors": validation_errors,
            })
            continue
        result = {
            "key": key,
            "fromRevision": int(item["revision"]),
            "semanticSourceRevision": semantic_source_revision,
            "semanticSourceLineage": lineage,
            "semanticSourceTemplate": semantic_source_file.as_posix(),
            "revision": next_revision(formal_root, key, int(item["revision"])),
            "oldPromptSha256": sha256_text(old_prompt),
            "newPromptSha256": sha256_text(new_prompt),
            "before": before.as_posix(),
            "beforeSha256": sha256_file(before),
            "after": after.as_posix(),
            "afterSha256": sha256_file(after),
            "oldLength": len(old_prompt),
            "newLength": len(new_prompt),
            "genericityGate": "pass",
            "semanticTransferGate": "pass",
        }
        if key in EVIDENCE_RECONCILED_KEYS:
            result["evidenceReconciliation"] = EVIDENCE_RECONCILED_KEYS[key]
        if args.apply:
            assert replay_report_file is not None
            dynamic_errors = replay_evidence_errors(
                replay_by_key.get(key), result=result, report_file=replay_report_file
            )
            if dynamic_errors:
                blocked.append({"key": key, "dynamicReplayErrors": dynamic_errors})
                continue
            result["dynamicReplayGate"] = "pass"
        templates_by_key[key] = new_template
        results.append(result)

    summary = {
        "catalogTotal": len(catalog["items"]),
        "selected": len(selected),
        "compiled": len(results),
        "blocked": len(blocked),
        "stage": args.stage,
        "apply": args.apply,
        "compilerVersion": COMPILER_VERSION,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if blocked:
        print(json.dumps(blocked[:20], ensure_ascii=False, indent=2))
        return 1
    if not args.stage and not args.apply:
        return 0

    run_root.mkdir(parents=True, exist_ok=True)
    if args.stage:
        candidates_root = run_root / "candidates"
        for result in results:
            key = result["key"]
            candidate_root = candidates_root / key
            runtime_input = candidate_root / "runtime-input"
            evaluation = candidate_root / "evaluation-reference"
            runtime_input.mkdir(parents=True, exist_ok=True)
            evaluation.mkdir(parents=True, exist_ok=True)
            atomic_write_json(candidate_root / "style-template.json", templates_by_key[key])
            (runtime_input / "prompt.txt").write_text(
                templates_by_key[key]["promptTemplate"] + "\n", encoding="utf-8"
            )
            before = Path(result["before"])
            after = Path(result["after"])
            shutil.copy2(before, runtime_input / f"source{before.suffix.lower()}")
            shutil.copy2(after, evaluation / f"approved-after{after.suffix.lower()}")
            atomic_write_json(candidate_root / "candidate-receipt.json", {
                "artifactType": "style_prompt_replay_candidate",
                "schemaVersion": "1.0.0",
                "producer": "style-template-analyzer",
                "compilerVersion": COMPILER_VERSION,
                "status": "awaiting-dynamic-replay",
                **result,
                "runtimeInputs": [
                    f"runtime-input/source{before.suffix.lower()}",
                    "runtime-input/prompt.txt",
                ],
                "approvedAfterUsedAsRuntimeInput": False,
                "evaluationReference": f"evaluation-reference/approved-after{after.suffix.lower()}",
            })
            result["candidateRoot"] = candidate_root.as_posix()
        atomic_write_json(run_root / "migration-report.json", {
            "artifactType": "style_prompt_recompilation_batch",
            "schemaVersion": "2.0.0",
            "producer": "style-template-analyzer",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "status": "awaiting-dynamic-replay",
            **summary,
            "items": results,
        })
        return 0

    assert replay_report_file is not None
    for result in results:
        key = result["key"]
        revision = result["revision"]
        before = Path(result["before"])
        after = Path(result["after"])
        revision_root = formal_root / key / str(revision)
        package = revision_root / "package"
        internal = revision_root / "internal"
        package.mkdir(parents=True, exist_ok=True)
        internal.mkdir(parents=True, exist_ok=True)
        shutil.copy2(after, package / "cover.png")
        atomic_write_json(package / "style-template.json", templates_by_key[key])
        shutil.copy2(before, internal / f"approved-before{before.suffix.lower()}")
        atomic_write_json(internal / "prompt-recompilation-receipt.json", {
            "artifactType": "style_prompt_recompilation_receipt",
            "schemaVersion": "2.0.0",
            "producer": "style-template-analyzer",
            "compilerVersion": COMPILER_VERSION,
            "templateKey": key,
            "fromRevision": result["fromRevision"],
            "semanticSourceRevision": result["semanticSourceRevision"],
            "semanticSourceLineage": result["semanticSourceLineage"],
            "revision": revision,
            "authorityMode": "approved-before-after-pair",
            "oldPromptSha256": result["oldPromptSha256"],
            "newPromptSha256": result["newPromptSha256"],
            "sourceSha256": result["beforeSha256"],
            "approvedAfterSha256": result["afterSha256"],
            "runtimeInputs": ["user-uploaded-source", "promptTemplate"],
            "approvedAfterUsedAsRuntimeInput": False,
            "genericityGate": {
                "status": "pass",
                "rules": [
                    "nine-direct-runtime-sections",
                    "source-derived-structure",
                    "core-role-replacement-required",
                    "no-case-image-reference",
                    "no-internal-contract-language",
                    "structural-operator-semantic-transfer",
                ],
            },
            "replayStatus": "original-and-transfer-replays-pass",
            "replayReportSha256": replay_report_sha256,
            "replayEvidence": replay_by_key[key],
        })
        shutil.copy2(replay_report_file, internal / "prompt-replay-report.json")
        write_manifest(
            revision_root, key, revision, result["fromRevision"],
            result["semanticSourceRevision"], replay_report_sha256,
        )
        result["templateSha256"] = sha256_file(package / "style-template.json")
        result["formalTemplate"] = (package / "style-template.json").as_posix()
        result["formalRevisionRoot"] = revision_root.as_posix()
        if str(templates_by_key[key].get("cover", "")).startswith("https://"):
            delivery_root.mkdir(parents=True, exist_ok=True)
            atomic_write_json(delivery_root / f"{key}.json", templates_by_key[key])
            result["deliveryStatus"] = "ready-for-import"
            result["deliveryFile"] = (delivery_root / f"{key}.json").as_posix()
        else:
            awaiting = delivery_root.parent / "awaiting-finalization" / key
            awaiting.mkdir(parents=True, exist_ok=True)
            atomic_write_json(awaiting / "style-template.json", templates_by_key[key])
            shutil.copy2(after, awaiting / "cover.png")
            result["deliveryStatus"] = "awaiting-oss-finalization"
            result["deliveryFile"] = (awaiting / "style-template.json").as_posix()

    atomic_write_json(run_root / "migration-report.json", {
        "artifactType": "style_prompt_recompilation_batch",
        "schemaVersion": "2.0.0",
        "producer": "style-template-analyzer",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "status": "published-after-dynamic-replay",
        "replayReportSha256": replay_report_sha256,
        **summary,
        "items": results,
    })
    ready_results = [item for item in results if item["deliveryStatus"] == "ready-for-import"]
    awaiting_results = [item for item in results if item["deliveryStatus"] == "awaiting-oss-finalization"]
    delivery_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(delivery_root / "artifact-manifest.json", {
        "artifactType": "style_template_delivery_batch",
        "schemaVersion": "2.0.0",
        "producer": "style-template-analyzer",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "approvedTemplateCount": len(results),
        "readyForImportCount": len(ready_results),
        "awaitingFinalizationCount": len(awaiting_results),
        "compilerVersion": COMPILER_VERSION,
        "replayReportSha256": replay_report_sha256,
        "files": [
            {"path": f"{item['key']}.json", "sha256": sha256_file(delivery_root / f"{item['key']}.json")}
            for item in ready_results
        ],
        "awaitingFinalization": [
            {"key": item["key"], "path": item["deliveryFile"]}
            for item in awaiting_results
        ],
    })

    updated = copy.deepcopy(catalog)
    updated["generatedAt"] = datetime.now(timezone.utc).isoformat()
    by_key = {item["key"]: item for item in results}
    for item in updated["items"]:
        result = by_key.get(item["key"])
        if result is None:
            continue
        revision = result["revision"]
        item.update({
            "id": f"{item['key']}-r{revision}",
            "revision": revision,
            "approvalProvenance": "approved-after-replay-verified-prompt-recompiled",
            "template": f"{item['key']}/{revision}/package/style-template.json",
            "effectImage": f"{item['key']}/{revision}/package/cover.png",
            "templateSha256": result["templateSha256"],
            "effectSha256": result["afterSha256"],
            "approvedBefore": f"{item['key']}/{revision}/internal/approved-before{Path(result['before']).suffix.lower()}",
            "approvedBeforeSha256": result["beforeSha256"],
            "approvalEvidence": f"{item['key']}/{revision}/internal/prompt-recompilation-receipt.json",
            "sourcePackage": f"{item['key']}/{revision}/package",
        })
    provenance_counts: dict[str, int] = {}
    for item in updated["items"]:
        provenance = str(item.get("approvalProvenance", "unknown"))
        provenance_counts[provenance] = provenance_counts.get(provenance, 0) + 1
    updated["approvalProvenanceCounts"] = provenance_counts
    backup_root = run_root / "catalog-backup"
    backup_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(catalog_file, backup_root / catalog_file.name)
    atomic_write_json(catalog_file, updated)
    sibling = catalog_file.with_name("已通过模板清单.json")
    if sibling.is_file():
        shutil.copy2(sibling, backup_root / sibling.name)
        atomic_write_json(sibling, updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
