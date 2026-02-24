from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

from app.database import get_db, Target, TargetType
from app.models import TargetCreate, TargetUpdate, TargetResponse
from app.utils import get_current_time
from app.services.code_resolver import resolve_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/targets", tags=["关注管理"])


@router.post("/", response_model=TargetResponse, summary="新增关注标的")
def create_target(payload: TargetCreate, db: Session = Depends(get_db)):
    """
    新增关注的个股、场内基金(ETF)、场外基金(OTC)
    只需传入代码和阈值，系统自动识别名称和类型

    示例请求体:
    - 个股: {"code":"600519","buy_bias_rate":-0.08,"sell_bias_rate":0.15}
    - ETF: {"code":"510300","buy_bias_rate":-0.05,"sell_bias_rate":0.10}
    - 场外: {"code":"012708","buy_growth_rate":-2.0,"sell_growth_rate":3.0}
    """
    # 检查重复
    existing = db.query(Target).filter(Target.code == payload.code).first()
    if existing:
        raise HTTPException(400, f"标的 {payload.code} 已存在")

    # 自动识别代码
    resolved = resolve_code(payload.code)
    if not resolved:
        raise HTTPException(404, f"无法识别代码 {payload.code}，请确认代码是否正确")

    target = Target(
        code=resolved["code"],
        name=resolved["name"],
        type=TargetType(resolved["type"]),
        buy_bias_rate=payload.buy_bias_rate,
        sell_bias_rate=payload.sell_bias_rate,
        buy_growth_rate=payload.buy_growth_rate,
        sell_growth_rate=payload.sell_growth_rate,
        created_at=get_current_time(),
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    logger.info(
        f"新增关注: {resolved['name']}({resolved['code']}) "
        f"类型={resolved['type']}"
    )
    return target


@router.get("/", response_model=List[TargetResponse], summary="获取所有关注标的")
def list_targets(db: Session = Depends(get_db)):
    return db.query(Target).all()


@router.get("/{code}", response_model=TargetResponse, summary="查询单个标的")
def get_target(code: str, db: Session = Depends(get_db)):
    target = db.query(Target).filter(Target.code == code).first()
    if not target:
        raise HTTPException(404, f"标的 {code} 不存在")
    return target


@router.put("/{code}", response_model=TargetResponse, summary="修改标的阈值")
def update_target(code: str, payload: TargetUpdate, db: Session = Depends(get_db)):
    target = db.query(Target).filter(Target.code == code).first()
    if not target:
        raise HTTPException(404, f"标的 {code} 不存在")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(target, key, value)

    db.commit()
    db.refresh(target)
    return target


@router.delete("/{code}", summary="删除关注标的")
def delete_target(code: str, db: Session = Depends(get_db)):
    target = db.query(Target).filter(Target.code == code).first()
    if not target:
        raise HTTPException(404, f"标的 {code} 不存在")

    db.delete(target)
    db.commit()
    return {"message": f"已删除 {code}"}


@router.post("/batch", response_model=List[TargetResponse], summary="批量新增关注")
def batch_create_targets(
    payloads: List[TargetCreate],
    db: Session = Depends(get_db),
):
    """
    一次性添加多个标的
    已存在的自动跳过，无法识别的记录警告并跳过
    """
    results = []
    for payload in payloads:
        # 跳过已存在
        existing = db.query(Target).filter(Target.code == payload.code).first()
        if existing:
            logger.info(f"批量新增跳过（已存在）: {payload.code}")
            continue

        # 自动识别
        resolved = resolve_code(payload.code)
        if not resolved:
            logger.warning(f"批量新增跳过（无法识别）: {payload.code}")
            continue

        target = Target(
            code=resolved["code"],
            name=resolved["name"],
            type=TargetType(resolved["type"]),
            buy_bias_rate=payload.buy_bias_rate,
            sell_bias_rate=payload.sell_bias_rate,
            buy_growth_rate=payload.buy_growth_rate,
            sell_growth_rate=payload.sell_growth_rate,
            created_at=get_current_time(),
        )
        db.add(target)
        results.append(target)

    db.commit()
    for t in results:
        db.refresh(t)

    logger.info(f"批量新增完成: 成功 {len(results)} 个")
    return results