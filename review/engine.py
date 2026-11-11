"""Deterministic finance and reconciliation tools. All amounts are integer KRW.

NOI uses contractual earned rent in the synthetic full-month fixture; cash
receipts and distributions are separate. Unknown paid expenses stay in cash.
This is a prototype policy, not an accounting/tax certification.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from .validation import (InputError, object_with_fields, identifier, iso_date,
                         records, validate_members, validate_operation, validate_source_links)


def won(value):
    if isinstance(value, bool):
        raise ValueError("금액에 참/거짓을 사용할 수 없습니다")
    if isinstance(value, str) and not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)", value):
        raise ValueError("금액 문자열은 원 단위 정수 또는 올바른 천 단위 구분 형식이어야 합니다")
    try:
        d = Decimal(str(value).replace(",", ""))
    except Exception as exc:
        raise ValueError("금액 형식이 올바르지 않습니다") from exc
    if not d.is_finite() or d != d.to_integral_value() or abs(d) > 9007199254740991:
        raise ValueError("금액은 유한한 원 단위 정수여야 합니다")
    return int(d)


def rounded(value):
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def ratio(value, label):
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError(label + "은 유효한 비율이어야 합니다")
    try:
        d = Decimal(str(value))
    except Exception:
        raise ValueError(label + "은 유효한 비율이어야 합니다") from None
    if not d.is_finite() or not 0 <= d <= 1:
        raise ValueError(label + "은 0~1 사이여야 합니다")
    return d


def fingerprint(payload):
    def normalize(x):
        if isinstance(x, float) and x.is_integer(): return int(x)
        if isinstance(x, dict): return {k:normalize(v) for k,v in x.items()}
        if isinstance(x, list): return [normalize(v) for v in x]
        return x
    return hashlib.sha256(json.dumps(normalize(payload), ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def validate_asset(asset):
    required = {"asset_id", "purchase_price", "loan_balance", "potential_monthly_rent",
                "monthly_opex", "monthly_principal", "monthly_capex", "vacancy_rate",
                "annual_interest_rate", "reserve_rate", "members", "leases", "memo_source_id"}
    object_with_fields(asset, required, "asset")
    identifier(asset["asset_id"], "asset.asset_id")
    identifier(asset["memo_source_id"], "asset.memo_source_id")
    if asset.get("appraisal_source_id"):
        identifier(asset["appraisal_source_id"], "asset.appraisal_source_id")
    purchase, loan = won(asset["purchase_price"]), won(asset["loan_balance"])
    if purchase <= 0 or not 0 <= loan < purchase:
        raise ValueError("매입가와 차입금 설정을 확인하세요")
    for key in ("potential_monthly_rent", "monthly_opex", "monthly_principal", "monthly_capex"):
        if won(asset[key]) < 0:
            raise ValueError(key + "은 음수일 수 없습니다")
    for key in ("vacancy_rate", "annual_interest_rate", "reserve_rate"):
        ratio(asset[key], key)
    validate_members(asset["members"])
    records(asset["leases"], {"unit_id", "rent_due", "end_date", "source_id"}, "unit_id", "asset.leases")
    for i, lease in enumerate(asset["leases"]):
        iso_date(lease["end_date"], f"asset.leases[{i}].end_date")
        identifier(lease["source_id"], f"asset.leases[{i}].source_id")
        if "start_date" in lease:
            start = iso_date(lease["start_date"], f"asset.leases[{i}].start_date")
            if start > date.fromisoformat(lease["end_date"]):
                raise InputError("INVALID_LEASE_INTERVAL", f"asset.leases[{i}]", "계약 시작일이 종료일보다 늦습니다")
        if won(lease["rent_due"]) < 0:
            raise ValueError("계약 임대료는 음수일 수 없습니다")
    return True


def calculate_baseline(asset, overrides=None):
    a = copy.deepcopy(asset)
    allowed = {"vacancy_rate", "potential_monthly_rent", "monthly_opex", "reserve_rate"}
    if overrides:
        if set(overrides) - allowed:
            raise ValueError("허용되지 않은 시나리오 변수입니다")
        a.update(overrides)
    validate_asset(a)
    rent = rounded(Decimal(won(a["potential_monthly_rent"])) * (1-ratio(a["vacancy_rate"], "공실률")))
    opex = won(a["monthly_opex"])
    noi = rent - opex
    interest = rounded(Decimal(won(a["loan_balance"])) * ratio(a["annual_interest_rate"], "연 이자율") / 12)
    before_reserve = noi-interest-won(a["monthly_principal"])-won(a["monthly_capex"])
    reserve = rounded(max(0, before_reserve) * ratio(a["reserve_rate"], "예비비율"))
    distribution = max(0, before_reserve-reserve)
    purchase = won(a["purchase_price"])
    equity = purchase-won(a["loan_balance"])
    return {"effective_rent": rent, "operating_expense": opex, "noi": noi,
            "interest": interest, "principal": won(a["monthly_principal"]),
            "capex": won(a["monthly_capex"]), "cash_before_reserve": before_reserve,
            "reserve": reserve, "distribution_before_personal_tax": distribution,
            "purchase_price": purchase, "equity": equity,
            "noi_yield_pct": float(Decimal(noi)*12/purchase*100),
            "cash_distribution_yield_pct": float(Decimal(distribution)*12/equity*100),
            "assumptions": {k:a[k] for k in sorted(allowed)},
            "synthetic": True, "tax_basis": "개인별 세금 미반영"}


def analyze_investment(asset, as_of="2026-10-24"):
    validate_asset(asset)
    baseline = calculate_baseline(asset)
    alerts = []
    for lease in asset["leases"]:
        days = (date.fromisoformat(lease["end_date"])-date.fromisoformat(as_of)).days
        if 0 <= days <= 90:
            alerts.append({"code":"LEASE_EXPIRY", "severity":"검토", "blocking":False,
                           "message":f'{lease["unit_id"]} 계약이 {days}일 뒤 만료됩니다',
                           "source_ids":[lease["source_id"]]})
    due = sum(won(x["rent_due"]) for x in asset["leases"])
    concentration = max((won(x["rent_due"])/due for x in asset["leases"]), default=0) if due else 0
    if concentration > .4:
        alerts.append({"code":"TENANT_CONCENTRATION", "severity":"검토", "blocking":False,
                       "message":f"최대 임차인 비중 {concentration*100:.1f}%를 확인하세요",
                       "source_ids":[x["source_id"] for x in asset["leases"]]})
    if not asset.get("appraisal_source_id"):
        alerts.append({"code":"APPRAISAL_MISSING", "severity":"확인 필요", "blocking":True,
                       "message":"가격 검토 자료가 없습니다. 매입가 적정성 검토를 완료할 수 없습니다",
                       "source_ids":[asset["memo_source_id"]]})
    return {"asset_id":asset["asset_id"], "as_of":as_of, "baseline":baseline,
            "alerts":alerts, "next_actions":[a["message"] for a in alerts],
            "source_ids":[asset["memo_source_id"]]+[x["source_id"] for x in asset["leases"]],
            "status":"REVIEW_REQUIRED" if any(a["blocking"] for a in alerts) else "ANALYZED"}


def create_snapshot(asset, baseline=None, as_of="2026-09-30"):
    validate_asset(asset)
    iso_date(as_of, "snapshot.as_of")
    payload = {"schema_version":"1.0", "asset_id":asset["asset_id"], "version":1,
               "as_of":as_of, "synthetic":True,
               "baseline":copy.deepcopy(baseline or calculate_baseline(asset)),
               "members":copy.deepcopy(asset["members"]),
               "source_ids":[asset["memo_source_id"]]+[x["source_id"] for x in asset["leases"]]}
    return {"payload":payload, "sha256":fingerprint(payload)}


def verify_snapshot(snapshot, asset_id):
    object_with_fields(snapshot, {"payload", "sha256"}, "snapshot")
    payload = object_with_fields(snapshot["payload"], {"asset_id", "baseline", "members", "as_of"}, "snapshot.payload")
    iso_date(payload["as_of"], "snapshot.payload.as_of")
    if snapshot["payload"]["asset_id"] != asset_id:
        raise ValueError("검토 기준과 운영 자산 ID가 다릅니다")
    if fingerprint(snapshot["payload"]) != snapshot["sha256"]:
        raise ValueError("저장된 검토 기준이 변경되었습니다")
    validate_members(payload["members"], "snapshot.payload.members")
    base = object_with_fields(payload["baseline"], {"effective_rent", "operating_expense", "interest", "principal", "capex", "distribution_before_personal_tax", "assumptions"}, "snapshot.payload.baseline")
    for key in ("effective_rent", "operating_expense", "interest", "principal", "capex", "distribution_before_personal_tax"):
        if won(base[key]) < 0:
            raise ValueError("검토 기준의 금액을 확인하세요")
    object_with_fields(base["assumptions"], {"reserve_rate"}, "snapshot.payload.baseline.assumptions")
    ratio(base["assumptions"]["reserve_rate"], "예비비율")
    return True


def allocate(total, members):
    total = won(total)
    validate_members(members, "allocation.members")
    if total < 0 or sum(x["share_bps"] for x in members) != 10000:
        raise ValueError("배분 총액 또는 비율이 올바르지 않습니다")
    rows = [{"member_id":m["member_id"], "name":m["name"], "share_bps":m["share_bps"],
             "amount":total*m["share_bps"]//10000,
             "remainder":total*m["share_bps"]%10000} for m in members]
    missing = total-sum(r["amount"] for r in rows)
    for r in sorted(rows, key=lambda x:(-x["remainder"], x["member_id"]))[:missing]:
        r["amount"] += 1
    for r in rows:
        r.pop("remainder")
    return rows


def reconcile(asset, operation, snapshot):
    validate_asset(asset)
    verify_snapshot(snapshot, asset["asset_id"])
    validate_operation(asset, operation, won)
    current_shares = {m["member_id"]: m["share_bps"] for m in asset["members"]}
    saved_shares = {m["member_id"]: m["share_bps"] for m in snapshot["payload"]["members"]}
    if current_shares != saved_shares:
        raise InputError("UNDECLARED_MEMBERSHIP_CHANGE", "asset.members", "저장 기준 이후 지분이 변경됐습니다. 수동 검토가 필요합니다")
    period = operation["period"]
    date.fromisoformat(period+"-01")
    if operation["asset_id"] != asset["asset_id"]:
        raise ValueError("운영 자료의 자산 ID가 다릅니다")
    if operation.get("members_changed"):
        raise ValueError("기간 중 지분 변경은 이 시제품에서 자동 처리하지 않습니다")
    bank = operation["bank"]
    if len({x["id"] for x in bank}) != len(bank):
        raise ValueError("은행 거래 ID가 중복됩니다")
    for row in bank:
        if row["asset_id"] != asset["asset_id"] or not row["date"].startswith(period+"-"):
            raise ValueError("다른 자산 또는 정산 기간의 거래가 섞여 있습니다")
        date.fromisoformat(row["date"])
        if won(row["amount"]) < 0 or row["direction"] not in ("in","out"):
            raise ValueError("거래 방향과 금액을 확인하세요")
        if row["kind"] not in ("rent","deposit","opex","unclassified","interest","principal","capex"):
            raise ValueError("알 수 없는 거래 유형입니다")
    issues = []
    def issue(code,message,sources,blocking=False,amount=0):
        issues.append({"code":code,"message":message,"source_ids":sources,
                       "blocking":blocking,"amount":amount})
    rent_due = sum(won(x["rent_due"]) for x in asset["leases"])
    rent_received = sum(won(x["amount"]) for x in bank if x["direction"]=="in" and x["kind"]=="rent")
    unit_ids = {x["unit_id"] for x in asset["leases"]}
    for row in bank:
        if row["kind"]=="rent" and row.get("unit_id") not in unit_ids:
            raise ValueError("계약 목록에 없는 호실의 임대료 입금입니다")
    for lease in asset["leases"]:
        got = sum(won(x["amount"]) for x in bank if x["kind"]=="rent" and x["direction"]=="in" and x.get("unit_id")==lease["unit_id"])
        delta = won(lease["rent_due"])-got
        if delta:
            issue("RENT_DIFFERENCE", f'{lease["unit_id"]} 계약 임대료와 입금액 차이 {delta:,}원',
                  [lease["source_id"],operation["bank_source_id"]], amount=delta)
    receipts = {r["receipt_id"]:r for r in operation["receipts"]}
    seen_receipts = set()
    seen_payments = set()
    verified_opex = 0
    ledger_opex = 0
    for row in operation["expenses"]:
        if row["asset_id"] != asset["asset_id"] or not row["date"].startswith(period+"-"):
            raise ValueError("다른 자산 또는 기간의 비용 원장입니다")
        amount = won(row["amount"])
        if amount < 0:
            raise ValueError("비용은 음수일 수 없습니다")
        ledger_opex += amount
        rid, payment_id = row.get("receipt_id"), row.get("bank_id")
        if (rid and rid in seen_receipts) or payment_id in seen_payments:
            issue("DUPLICATE_EXPENSE", "동일 증빙 또는 은행 거래에 연결된 비용이 중복됩니다",
                  [operation["expense_source_id"],operation["bank_source_id"]], amount=amount)
            continue
        if rid: seen_receipts.add(rid)
        if payment_id: seen_payments.add(payment_id)
        receipt = receipts.get(rid)
        payment = next((x for x in bank if x["id"]==payment_id),None)
        if not receipt:
            issue("MISSING_EVIDENCE", "지급 내역은 있으나 증빙이 없습니다. 현금 유출은 유지하고 확정을 보류합니다",
                  [operation["expense_source_id"],operation["bank_source_id"]],True,amount)
            continue
        if receipt["asset_id"] != asset["asset_id"]:
            issue("WRONG_ASSET_EVIDENCE", "다른 자산의 증빙이 연결되어 있습니다",[receipt["source_id"]],True,amount)
            continue
        if receipt.get("date") and not receipt["date"].startswith(period + "-"):
            issue("WRONG_PERIOD_EVIDENCE", "다른 정산 기간의 증빙입니다", [receipt["source_id"]], True, amount)
            continue
        if not payment or payment["direction"]!="out" or won(payment["amount"])!=amount or won(receipt["amount"])!=amount:
            issue("EVIDENCE_MISMATCH", "비용 원장·증빙·은행 지급액이 일치하지 않습니다",[receipt["source_id"],operation["bank_source_id"]],True,amount)
            continue
        if payment["kind"]!="opex":
            issue("CLASSIFICATION_REQUIRED", "운영비인지 자본적 지출인지 분류 확인이 필요합니다",[receipt["source_id"]],True,amount)
            continue
        verified_opex += amount
    for row in bank:
        if row["direction"]=="out" and row["kind"] in ("opex","unclassified") and row["id"] not in seen_payments:
            issue("UNMATCHED_PAYMENT", "은행 지급액에 대응하는 비용 원장 항목이 없습니다",[operation["bank_source_id"]],True,won(row["amount"]))
    seen_income = set()
    if not operation["income_ledger"] and any(x["direction"] == "in" for x in bank):
        issue("INCOME_LEDGER_MISSING", "입금 내역을 대조할 수입 원장 항목이 없습니다", [operation["income_source_id"]], True)
    for row in operation["income_ledger"]:
        payment=next((x for x in bank if x["id"]==row["bank_id"]),None)
        if row["bank_id"] in seen_income:
            issue("DUPLICATE_INCOME", "수입 원장에 같은 은행 거래가 중복 연결됐습니다", [operation["income_source_id"]], True, won(row["amount"]))
            continue
        seen_income.add(row["bank_id"])
        if not payment or payment["direction"] != "in" or won(payment["amount"]) != won(row["amount"]):
            issue("INCOME_MISMATCH", "수입 원장과 은행 입금의 연결·금액이 일치하지 않습니다", [operation["income_source_id"], operation["bank_source_id"]], True, won(row["amount"]))
            continue
        if payment and payment["kind"]=="deposit" and row["kind"]=="rent":
            issue("DEPOSIT_AS_RENT", "보증금 입금이 임대수익으로 입력되었습니다. 배분 재원에서 제외합니다",
                  [operation["income_source_id"],operation["bank_source_id"]],amount=won(payment["amount"]))
        elif payment["kind"] != row["kind"]:
            issue("INCOME_CLASSIFICATION_MISMATCH", "수입 원장과 은행 입금의 거래 성격이 다릅니다", [operation["income_source_id"], operation["bank_source_id"]], True, won(row["amount"]))
    for payment in bank:
        if payment["direction"] == "in" and payment["id"] not in seen_income:
            issue("UNMATCHED_INCOME", "입금 내역에 대응하는 수입 원장 항목이 없습니다", [operation["bank_source_id"], operation["income_source_id"]], True, won(payment["amount"]))
    paid_opex = sum(won(x["amount"]) for x in bank if x["direction"]=="out" and x["kind"] in ("opex","unclassified"))
    interest = sum(won(x["amount"]) for x in bank if x["direction"]=="out" and x["kind"]=="interest")
    principal = sum(won(x["amount"]) for x in bank if x["direction"]=="out" and x["kind"]=="principal")
    capex = sum(won(x["amount"]) for x in bank if x["direction"]=="out" and x["kind"]=="capex")
    before_reserve = rent_received-paid_opex-interest-principal-capex
    rr=ratio(snapshot["payload"]["baseline"]["assumptions"]["reserve_rate"],"예비비율")
    reserve=rounded(max(0,before_reserve)*rr)
    total=max(0,before_reserve-reserve)
    blocked=any(x["blocking"] for x in issues)
    baseline=snapshot["payload"]["baseline"]
    cash_effects={"rent":rent_received-baseline["effective_rent"],
                  "operating_payments":baseline["operating_expense"]-paid_opex,
                  "interest":baseline["interest"]-interest,
                  "principal":baseline["principal"]-principal,
                  "capex":baseline["capex"]-capex}
    return {"asset_id":asset["asset_id"],"period":period,"synthetic":True,
            "status":"NEEDS_REVIEW" if blocked else "DRAFT_READY",
            "finalized":False,"issues":issues,"snapshot_sha256":snapshot["sha256"],
            "rent_due":rent_due,"rent_received":rent_received,"rent_difference":rent_due-rent_received,
            "verified_operating_expense":verified_opex,"ledger_operating_expense":ledger_opex,
            "verified_items_noi":rent_due-verified_opex,"noi_is_final":not blocked,
            "paid_operating_cash":paid_opex,"cash_before_financing":rent_received-paid_opex,
            "interest":interest,"principal":principal,"capex":capex,
            "cash_before_reserve":before_reserve,"reserve":reserve,
            "distribution_before_personal_tax":total,
            "allocation":allocate(total,snapshot["payload"]["members"]),
            "expected_distribution":baseline["distribution_before_personal_tax"],
            "distribution_delta":total-baseline["distribution_before_personal_tax"],
            "cash_variance_drivers":cash_effects,
            "next_actions":[x["message"] for x in issues if x["blocking"]],
            "source_ids":list(dict.fromkeys([operation["bank_source_id"],operation["expense_source_id"],
                          operation["income_source_id"]]+[r["source_id"] for r in operation["receipts"]]))}


def run_integrated(dataset, asset_id="PF-A", case="combined"):
    object_with_fields(dataset, {"synthetic", "assets", "operations", "documents"}, "dataset")
    if dataset.get("synthetic") is not True:
        raise ValueError("현재 실행 패키지는 가상 시연 자료만 지원합니다. 실제 자료 연결 전 권한·규칙·필드 매핑 검토가 필요합니다")
    records(dataset["assets"], {"asset_id"}, "asset_id", "dataset.assets")
    asset=next((a for a in dataset["assets"] if a["asset_id"]==asset_id),None)
    if not asset: raise ValueError("자산을 찾지 못했습니다")
    if not isinstance(dataset["operations"], dict) or not isinstance(dataset["operations"].get(asset_id), dict) or case not in dataset["operations"][asset_id]:
        raise InputError("CASE_NOT_FOUND", "dataset.operations", "선택한 자산·사례를 찾을 수 없습니다")
    operation=copy.deepcopy(dataset["operations"][asset_id][case])
    investment=analyze_investment(asset)
    snapshot=create_snapshot(asset)
    validate_operation(asset, operation, won)
    validate_source_links(dataset, asset, operation)
    result=reconcile(asset,operation,snapshot)
    trace=[{"tool":"analyze_investment","decision":"수익 가정과 문서 누락을 검토","status":"완료"},
           {"tool":"create_snapshot","decision":"같은 자산 ID의 투자 검토 기준 고정","status":"완료"},
           {"tool":"reconcile","decision":"계약·은행·원장·증빙 대조","status":"완료"}]
    if result["next_actions"]:
        trace.append({"tool":"request_evidence","decision":"미확인 증빙이 있어 최종 확정 대신 확인 목록 생성","status":"확인 필요"})
    trace.append({"tool":"compare_and_report","decision":"예상 대비 차이와 세전 배분안 생성","status":"완료"})
    return {"schema_version":"1.0","mode":"rules","synthetic":True,"investment":investment,
            "snapshot":snapshot,"operation":result,"trace":trace,
            "limitations":["가상 자료를 사용한 규칙 기반 시제품", "개인별 세금·법적 권리·송금 미처리", "최종 정산은 사람의 검토 필요"]}
