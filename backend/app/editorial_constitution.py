from copy import deepcopy

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import EditorialConstitutionVersion


INITIAL_EDITORIAL_CONSTITUTION = {
    "core_principles": [
        "关注情绪的后劲，而不只写事件发生当下",
        "把个人情感放进年龄、阶层、自由、工作和现实挤压等更大背景",
        "允许偏爱未完成、正在失败、尚未被世界驯服的人，并坦白其中的自私和矛盾",
        "用身体接触、气味、拥抱、距离和分别后的空缺表现依恋",
        "第一人称可以不体面、不完全正确，但必须有自我觉察",
        "女性经验是核心视角，同时避免为了流量制造简单男女对立",
        "文化作品只轻度进入文本，像私人联想，不像知识清单",
        "用具体场景承载抽象情绪",
        "情绪可以停在痛苦里，不强行成长、释怀或给出标准答案",
        "文章只保留一到两句真正准确的句子，不把每段都做成金句",
        "语言在精致与粗粝之间移动，允许少量口语、停顿、重复和不规整",
        "结尾偏向动作、场景或未回答的问题，避免总结中心思想",
    ],
    "title_structure_rules": [
        "标题以直接坦白型为主，金句型为辅",
        "正文默认 600 至 900 字",
        "叙事结构必须多样化，不固定为金句开头、讲故事、突然清醒、释怀结尾",
        "每篇至少有一个可视化的具体场景、动作、物件、声音或气味",
        "抽象思考必须由具体经验支撑",
        "作品或理论引用通常不超过一到两个",
        "封面短句不超过 18 个汉字",
    ],
    "ai_tone_prohibitions": [
        "高频使用原来、后来才明白、真正的",
        "机械使用不是而是结构",
        "没有场景支撑的抽象金句",
        "每段长度和句式过度整齐",
        "连续排比堆砌情绪",
        "结尾强行升华为自爱、成长或放下",
        "用心理学名词替代人物经验",
        "只替换同义词的伪原创",
        "引用与正文没有真实关系",
        "所有文章都使用雨、海、路灯等同一组意象",
    ],
    "evaluation_dimensions": [
        "具体性",
        "情绪诚实度",
        "文学质感",
        "普通读者可读性",
        "女性经验的准确度",
        "场景与身体感",
        "结构新鲜度",
        "金句克制度",
        "文化联想自然度",
        "AI 模板化风险",
        "与历史内容重复风险",
        "强行治愈风险",
    ],
}


class EditorialConstitutionError(RuntimeError):
    pass


def current_constitution(db: Session) -> EditorialConstitutionVersion | None:
    return db.scalar(
        select(EditorialConstitutionVersion)
        .order_by(EditorialConstitutionVersion.version.desc())
        .limit(1)
    )


def current_constitution_payload(db: Session) -> tuple[int, dict]:
    current = current_constitution(db)
    if not current:
        return 0, deepcopy(INITIAL_EDITORIAL_CONSTITUTION)
    return current.version, deepcopy(current.sections)


def list_constitution_versions(db: Session) -> list[EditorialConstitutionVersion]:
    return list(
        db.scalars(
            select(EditorialConstitutionVersion)
            .order_by(EditorialConstitutionVersion.version.desc())
        )
    )


def update_constitution(db: Session, sections: dict, change_note: str) -> EditorialConstitutionVersion:
    latest = current_constitution(db)
    version = EditorialConstitutionVersion(
        version=(db.scalar(select(func.max(EditorialConstitutionVersion.version))) or 0) + 1,
        sections=deepcopy(sections),
        change_type="manual_edit",
        source_version=latest.version if latest else 0,
        change_note=change_note,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def rollback_constitution(db: Session, target_version: int) -> EditorialConstitutionVersion:
    target = None
    if target_version != 0:
        target = db.scalar(
            select(EditorialConstitutionVersion)
            .where(EditorialConstitutionVersion.version == target_version)
        )
        if not target:
            raise EditorialConstitutionError("要恢复的编辑宪法版本不存在")
    latest = current_constitution(db)
    if latest and latest.version == target_version:
        raise EditorialConstitutionError("当前已经是这个版本")
    restored = EditorialConstitutionVersion(
        version=(db.scalar(select(func.max(EditorialConstitutionVersion.version))) or 0) + 1,
        sections=deepcopy(target.sections if target else INITIAL_EDITORIAL_CONSTITUTION),
        change_type="rollback",
        source_version=target_version,
        change_note=f"人工确认恢复到 V{target_version}",
    )
    db.add(restored)
    db.commit()
    db.refresh(restored)
    return restored
