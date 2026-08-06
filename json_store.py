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
    "custom-order": _BASE / "custom-order.json",
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


def update_category(cid: str, name: str, parent_id_form: str | None) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    items = normalize_categories(read_list("categories"))
    idx = next(
        (i for i, x in enumerate(items) if isinstance(x, dict) and x.get("id") == cid),
        None,
    )
    if idx is None:
        return False
    row = dict(items[idx])
    kind = row.get("kind", "parent")
    if kind == "child":
        pid = (parent_id_form or "").strip() or None
        if not pid or pid == cid:
            return False
        if not any(
            isinstance(x, dict) and x.get("id") == pid and x.get("kind") == "parent"
            for x in items
        ):
            return False
        row["name"] = name
        row["kind"] = "child"
        row["parent_id"] = pid
    else:
        row["name"] = name
        row["kind"] = "parent"
        row["parent_id"] = None
    items[idx] = row
    write_list("categories", normalize_categories(items))
    return True


def delete_category_by_id(cid: str) -> bool:
    items = normalize_categories(read_list("categories"))
    row = next((x for x in items if isinstance(x, dict) and x.get("id") == cid), None)
    if row is None:
        return False
    to_remove = {cid}
    if row.get("kind") == "parent":
        for x in items:
            if (
                isinstance(x, dict)
                and x.get("kind") == "child"
                and x.get("parent_id") == cid
            ):
                to_remove.add(x["id"])
    new_items = [
        x for x in items if not (isinstance(x, dict) and x.get("id") in to_remove)
    ]
    if len(new_items) == len(items):
        return False
    write_list("categories", new_items)

    services = read_list("services")
    s_changed = False
    for s in services:
        if not isinstance(s, dict):
            continue
        cats = list(s.get("category_ids") or [])
        nc = [x for x in cats if x not in to_remove]
        if nc != cats:
            s["category_ids"] = nc
            s_changed = True
    if s_changed:
        write_list("services", services)

    plans = read_list("plans")
    p_changed = False
    for p in plans:
        if not isinstance(p, dict):
            continue
        cids = list(p.get("category_ids") or [])
        nc = [x for x in cids if x not in to_remove]
        if nc != cids:
            p["category_ids"] = nc
            p_changed = True
    if p_changed:
        write_list("plans", plans)
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


def update_customer_row(cid: str, name: str, phone: str, address: str) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    items = read_list("customers")
    for i, c in enumerate(items):
        if isinstance(c, dict) and c.get("id") == cid:
            items[i] = {
                "id": cid,
                "name": name,
                "phone": (phone or "").strip(),
                "address": (address or "").strip(),
            }
            write_list("customers", items)
            return True
    return False


def delete_customer_by_id(cid: str) -> bool:
    items = read_list("customers")
    new_items = [
        c for c in items if not (isinstance(c, dict) and c.get("id") == cid)
    ]
    if len(new_items) == len(items):
        return False
    write_list("customers", new_items)
    return True


def find_customer(customers: list, cid: str) -> dict | None:
    for c in customers:
        if isinstance(c, dict) and c.get("id") == cid:
            return c
    return None


def find_order_by_source(source: str, order_id: str) -> dict | None:
    key = "orders" if source == "orders" else "custom-order" if source == "custom-order" else None
    if not key:
        return None
    for row in read_list(key):
        if isinstance(row, dict) and row.get("id") == order_id:
            return row
    return None


def append_order(
    customer_id: str,
    customer_snapshot: dict,
    plan_ids: list[str],
    merged_service_ids: list[str],
    services_detail: list[dict],
    total_amount: int,
    *,
    invoice_type: str = "current",
    selected_plans_snapshot: list[dict] | None = None,
    simple_lines: list[dict] | None = None,
) -> str:
    oid = str(uuid4())
    items = read_list("orders")
    it = (invoice_type or "current").strip()
    if it not in ("current", "simple", "roadmap"):
        it = "current"
    snap = selected_plans_snapshot if isinstance(selected_plans_snapshot, list) else []
    clean_snap: list[dict] = []
    for p in snap:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        clean_snap.append(
            {
                "id": p["id"],
                "name": p.get("name", ""),
                "terms": [x.strip() for x in (p.get("terms") or []) if isinstance(x, str) and x.strip()],
                "extra_note": (p.get("extra_note") or "").strip(),
            }
        )
    row: dict = {
        "id": oid,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "customer_id": customer_id,
        "customer": customer_snapshot,
        "plan_ids": plan_ids,
        "service_ids": merged_service_ids,
        "services_detail": services_detail,
        "total_price": total_amount,
        "invoice_type": it,
        "selected_plans_snapshot": clean_snap,
    }
    if isinstance(simple_lines, list) and simple_lines:
        row["simple_lines"] = simple_lines
    items.append(row)
    write_list("orders", items)
    return oid


def append_custom_order(
    customer_id: str,
    customer_snapshot: dict,
    steps: list[dict],
    total_amount: int,
    *,
    invoice_type: str = "current",
    simple_lines: list[dict] | None = None,
    panel_plans: list[dict] | None = None,
) -> str:
    oid = str(uuid4())
    items = read_list("custom-order")
    it = (invoice_type or "current").strip()
    if it not in ("current", "simple", "roadmap", "panel"):
        it = "current"
    row: dict = {
        "id": oid,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "customer_id": customer_id,
        "customer": customer_snapshot,
        "steps": steps if isinstance(steps, list) else [],
        "total_price": total_amount,
        "invoice_type": it,
    }
    if isinstance(simple_lines, list) and simple_lines:
        row["simple_lines"] = simple_lines
    if isinstance(panel_plans, list) and panel_plans:
        row["panel_plans"] = panel_plans
    items.append(row)
    write_list("custom-order", items)
    return oid


def append_service(
    name: str,
    category_ids: list[str],
    price: str = "",
    description: str = "",
    terms: list[str] | None = None,
    extra_note: str = "",
) -> str | None:
    name = (name or "").strip()
    if not name:
        return None
    ids = []
    for x in category_ids or []:
        if isinstance(x, str) and x.strip():
            ids.append(x.strip())
    items = read_list("services")
    clean_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in terms or []:
        if not isinstance(term, str):
            continue
        t = term.strip()
        if not t or t in seen_terms:
            continue
        seen_terms.add(t)
        clean_terms.append(t)
    sid = str(uuid4())
    items.append(
        {
            "id": sid,
            "name": name,
            "category_ids": ids,
            "price": (price or "").strip(),
            "description": (description or "").strip(),
            "terms": clean_terms,
            "extra_note": (extra_note or "").strip(),
        }
    )
    write_list("services", items)
    return sid


def update_service(
    sid: str,
    name: str,
    category_ids: list[str],
    price: str,
    description: str,
    terms: list[str] | None = None,
    extra_note: str = "",
) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    ids = [x.strip() for x in (category_ids or []) if isinstance(x, str) and x.strip()]
    items = read_list("services")
    clean_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in terms or []:
        if not isinstance(term, str):
            continue
        t = term.strip()
        if not t or t in seen_terms:
            continue
        seen_terms.add(t)
        clean_terms.append(t)
    for i, s in enumerate(items):
        if isinstance(s, dict) and s.get("id") == sid:
            items[i] = {
                "id": sid,
                "name": name,
                "category_ids": ids,
                "price": (price or "").strip(),
                "description": (description or "").strip(),
                "terms": clean_terms,
                "extra_note": (extra_note or "").strip(),
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


def append_plan(
    name: str,
    category_ids: list[str],
    service_ids: list[str],
    price: str = "",
    terms: list[str] | None = None,
    extra_note: str = "",
) -> None:
    name = (name or "").strip()
    if not name:
        return
    cids = []
    seen_cids: set[str] = set()
    for x in category_ids or []:
        if not isinstance(x, str) or not x.strip():
            continue
        cid = x.strip()
        if cid in seen_cids:
            continue
        seen_cids.add(cid)
        cids.append(cid)
    sids = []
    seen_sids: set[str] = set()
    for x in service_ids or []:
        if not isinstance(x, str) or not x.strip():
            continue
        sid = x.strip()
        if sid in seen_sids:
            continue
        seen_sids.add(sid)
        sids.append(sid)
    clean_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in terms or []:
        if not isinstance(term, str):
            continue
        t = term.strip()
        if not t or t in seen_terms:
            continue
        seen_terms.add(t)
        clean_terms.append(t)
    items = read_list("plans")
    items.append(
        {
            "id": str(uuid4()),
            "name": name,
            "category_ids": cids,
            "service_ids": sids,
            "price": (price or "").strip(),
            "terms": clean_terms,
            "extra_note": (extra_note or "").strip(),
        }
    )
    write_list("plans", items)
