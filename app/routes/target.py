from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

from app.database import get_db, Target, TargetType, SecurityInfo
from app.models import TargetCreate, TargetUpdate, TargetResponse
from app.utils import get_current_time
from app.services.code_resolver import resolve_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/targets", tags=["关注管理"])


@router.post("/", response_model=TargetResponse, summary="新增关注标的")
def create_target(payload: TargetCreate, db: Session = Depends(get_db)):
    """
    新增关注 — 只需传入代码 + 阈值，自动识别名称和类型

    示例:
    - 个股: {"code":"600519","buy_bias_rate":-0.08,"sell_bias_rate":0.15}
    - ETF: {"code":"510300","buy_bias_rate":-0.05,"sell_bias_rate":0.10}
    - 场外: {"code":"012708","buy_growth_rate":-2.0,"sell_growth_rate":3.0}
    """
    existing = db.query(Target).filter(Target.code == payload.code).first()
    if existing:
        raise HTTPException(400, f"标的 {payload.code} 已存在")

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

    logger.info(f"新增关注: {resolved['name']}({resolved['code']}) 类型={resolved['type']}")
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
    批量新增 — 只需传入代码 + 阈值
    全部从本地缓存表查询，毫秒级响应
    """
    results = []
    for payload in payloads:
        existing = db.query(Target).filter(Target.code == payload.code).first()
        if existing:
            logger.info(f"[batch_create] 跳过（已存在）: {payload.code}")
            continue

        resolved = resolve_code(payload.code)
        if not resolved:
            logger.warning(f"[batch_create] 跳过（无法识别代码）: {payload.code}")
            continue

        try:
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
            logger.info(f"[batch_create] 新增成功: {resolved['name']}({resolved['code']}) 类型={resolved['type']}")
        except Exception as e:
            logger.error(f"[batch_create] 新增失败: {payload.code}, 原因: {e}", exc_info=True)
            continue

    db.commit()
    for t in results:
        db.refresh(t)

    logger.info(f"[batch_create] 批量新增完成: 成功 {len(results)}/{len(payloads)} 个")
    return results