from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import datetime

from app.database import get_db, Target, TargetType
from app.models import TargetCreate, TargetUpdate, TargetResponse
from app.utils import get_current_time

router = APIRouter(prefix="/targets", tags=["关注管理"])


@router.post("/", response_model=TargetResponse, summary="新增关注标的")
def create_target(payload: TargetCreate, db: Session = Depends(get_db)):
    """
    新增关注的个股、场内基金(ETF)、场外基金(OTC)

    示例请求体:
    - 个股: {"code":"600519","name":"贵州茅台","type":"stock","buy_bias_rate":-0.08,"sell_bias_rate":0.15}
    - ETF: {"code":"510300","name":"沪深300ETF","type":"etf","buy_bias_rate":-0.05,"sell_bias_rate":0.10}
    - 场外: {"code":"012708","name":"东方红启恒","type":"otc","buy_growth_rate":-2.0,"sell_growth_rate":3.0}
    """
    # 检查重复
    existing = db.query(Target).filter(Target.code == payload.code).first()
    if existing:
        raise HTTPException(400, f"标的 {payload.code} 已存在")

    target = Target(
        code=payload.code,
        name=payload.name,
        type=TargetType(payload.type.value),
        buy_bias_rate=payload.buy_bias_rate,
        sell_bias_rate=payload.sell_bias_rate,
        buy_growth_rate=payload.buy_growth_rate,
        sell_growth_rate=payload.sell_growth_rate,
        created_at=get_current_time(),
    )
    db.add(target)
    db.commit()
    db.refresh(target)
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
    """一次性添加多个标的"""
    results = []
    for payload in payloads:
        existing = db.query(Target).filter(Target.code == payload.code).first()
        if existing:
            continue  # 跳过已存在的

        target = Target(
            code=payload.code,
            name=payload.name,
            type=TargetType(payload.type.value),
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
    return results