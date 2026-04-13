import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

_BASE = Path(__file__).resolve().parent / "Database"

_FILES = {
    "categories": _BASE / "categories.json",
    "services": _BASE / "services.json",
    "plans": _BASE / "plans.json",
    "customers": _BASE / "customers.json",
    "orders": _BASE / "orders.json",
}


def _path(key: str) -> Path:
    return _FILES[key]


def _ensure(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("[]", encoding="utf-8")


def read_list(key: str) -> list:
    path = _path(key)
    _ensure(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def write_list(key: str, items: list) -> None:
    path = _path(key)
    _ensure(path)
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_categories(items: list) -> list:
    out = []
    for c in items:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        name = (c.get("name") or "").strip()
        if not cid or not name:
            continue
        kind = c.get("kind")
        parent_id = c.get("parent_id")
        if kind not in ("parent", "child"):
            kind = "parent"
            parent_id = None
        if kind == "child" and not parent_id:
            kind = "parent"
            parent_id = None
        row = {**c, "name": name, "kind": kind, "parent_id": parent_id}
        out.append(row)
    return out


def append_category(name: str, kind: str, parent_id: str | None) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    if kind not in ("parent", "child"):
        kind = "parent"
    items = normalize_categories(read_list("categories"))
    if kind == "child":
        if not parent_id:
            return False
        if not any(
            x["id"] == parent_id and x["kind"] == "parent" for x in items
        ):
            return False
        items.append(
            {
                "id": str(uuid4()),
                "name": name,
                "kind": "child",
                "parent_id": parent_id,
            }
        )
    else:
        items.append(
            {
                "id": str(uuid4()),
                "name": name,
                "kind": "parent",
                "parent_id": None,
            }
        )
    write_list("categories", items)
    return True


def parse_price_amount(value: str) -> int:
    if not value:
        return 0
    t = str(value)
    for i, d in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        t = t.replace(d, str(i))
    digits = re.sub(r"\D", "", t)
    return int(digits) if digits else 0


def append_customer(name: str, phone: str, address: str) -> str | None:
    name = (name or "").strip()
    if not name:
        return None
    cid = str(uuid4())
    items = read_list("customers")
    items.append(
        {
            "id": cid,
            "name": name,
            "phone": (phone or "").strip(),
            "address": (address or "").strip(),
        }
    )
    write_list("customers", items)
    return cid


def find_customer(customers: list, cid: str) -> dict | None:
    for c in customers:
        if isinstance(c, dict) and c.get("id") == cid:
            return c
    return None


def append_order(
    customer_id: str,
    customer_snapshot: dict,
    plan_ids: list[str],
    merged_service_ids: list[str],
    services_detail: list[dict],
    total_amount: int,
) -> str:
    oid = str(uuid4())
    items = read_list("orders")
    items.append(
        {
            "id": oid,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "customer_id": customer_id,
            "customer": customer_snapshot,
            "plan_ids": plan_ids,
            "service_ids": merged_service_ids,
            "services_detail": services_detail,
            "total_price": total_amount,
        }
    )
    write_list("orders", items)
    return oid


def append_service(
    name: str,
    category_ids: list[str],
    price: str = "",
    description: str = "",
) -> None:
    name = (name or "").strip()
    if not name:
        return
    ids = []
    for x in category_ids or []:
        if isinstance(x, str) and x.strip():
            ids.append(x.strip())
    items = read_list("services")
    items.append(
        {
            "id": str(uuid4()),
            "name": name,
            "category_ids": ids,
            "price": (price or "").strip(),
            "description": (description or "").strip(),
        }
    )
    write_list("services", items)


def update_service(
    sid: str,
    name: str,
    category_ids: list[str],
    price: str,
    description: str,
) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    ids = [x.strip() for x in (category_ids or []) if isinstance(x, str) and x.strip()]
    items = read_list("services")
    for i, s in enumerate(items):
        if isinstance(s, dict) and s.get("id") == sid:
            items[i] = {
                "id": sid,
                "name": name,
                "category_ids": ids,
                "price": (price or "").strip(),
                "description": (description or "").strip(),
            }
            write_list("services", items)
            return True
    return False


def delete_service_by_id(sid: str) -> bool:
    items = read_list("services")
    new_items = [
        s for s in items if not (isinstance(s, dict) and s.get("id") == sid)
    ]
    if len(new_items) == len(items):
        return False
    write_list("services", new_items)
    plans = read_list("plans")
    changed = False
    for p in plans:
        if not isinstance(p, dict):
            continue
        psids = list(p.get("service_ids") or [])
        if sid in psids:
            p["service_ids"] = [x for x in psids if x != sid]
            changed = True
    if changed:
        write_list("plans", plans)
    return True


def append_plan(name: str, category_ids: list[str], service_ids: list[str]) -> None:
    name = (name or "").strip()
    if not name:
        return
    cids = [x.strip() for x in (category_ids or []) if isinstance(x, str) and x.strip()]
    sids = [x.strip() for x in (service_ids or []) if isinstance(x, str) and x.strip()]
    items = read_list("plans")
    items.append(
        {
            "id": str(uuid4()),
            "name": name,
            "category_ids": cids,
            "service_ids": sids,
        }
    )
    write_list("plans", items)
