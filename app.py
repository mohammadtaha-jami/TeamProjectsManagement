from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for

from json_store import (
    append_category,
    append_customer,
    append_order,
    append_plan,
    append_service,
    delete_category_by_id,
    delete_customer_by_id,
    delete_service_by_id,
    find_customer,
    normalize_categories,
    parse_price_amount,
    read_list,
    update_category,
    update_customer_row,
    update_service,
)
from receipt_pdf import create_receipt_pdf


def build_category_groups(categories: list) -> list:
    parents = [c for c in categories if c.get("kind") == "parent"]
    groups = []
    for p in parents:
        children = [
            c
            for c in categories
            if c.get("kind") == "child" and c.get("parent_id") == p["id"]
        ]
        groups.append({"parent": p, "children": children})
    return groups


def build_order_category_groups(services: list, categories: list) -> list:
    """هر دستهٔ اصلی + زیردسته‌ها؛ خدمات زیر همان زیردسته‌ای که به آن وصل‌اند لیست می‌شود."""
    cats = normalize_categories(categories)
    out: list[dict] = []
    for group in build_category_groups(cats):
        parent = group["parent"]
        children = group["children"]
        pid = parent.get("id")
        if not isinstance(pid, str) or not pid.strip():
            continue
        child_id_set = {
            c["id"] for c in children if isinstance(c, dict) and isinstance(c.get("id"), str)
        }
        by_child: dict[str, list] = {
            c["id"]: [] for c in children if isinstance(c, dict) and isinstance(c.get("id"), str)
        }
        parent_only: list = []
        for s in services:
            if not isinstance(s, dict):
                continue
            raw = s.get("category_ids") or []
            cids = [x.strip() for x in raw if isinstance(x, str) and x.strip()]
            cset = set(cids)
            matched_children = [cid for cid in cids if cid in child_id_set]
            if matched_children:
                for cid in matched_children:
                    if cid in by_child:
                        by_child[cid].append(s)
            elif pid in cset:
                parent_only.append(s)
        child_sections = []
        for ch in children:
            if not isinstance(ch, dict):
                continue
            cid = ch.get("id")
            if not isinstance(cid, str):
                continue
            child_sections.append({"child": ch, "services": by_child.get(cid, [])})
        out.append(
            {
                "parent": parent,
                "child_sections": child_sections,
                "parent_only_services": parent_only,
            }
        )
    return out


def build_checkout_catalog(services: list, plans: list) -> dict:
    """دادهٔ خلاصه برای صفحهٔ سفارش: جمع قیمت و پیش‌فاکتور در سمت کاربر."""
    srv_rows = []
    for s in services:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        sid = s["id"]
        if not isinstance(sid, str) or not sid.strip():
            continue
        srv_rows.append(
            {
                "id": sid.strip(),
                "name": s.get("name", ""),
                "price": s.get("price", ""),
                "amount": parse_price_amount(s.get("price", "")),
            }
        )
    plan_rows = []
    for p in plans:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = p["id"]
        if not isinstance(pid, str) or not pid.strip():
            continue
        sids = [x.strip() for x in (p.get("service_ids") or []) if isinstance(x, str) and x.strip()]
        plan_rows.append(
            {
                "id": pid.strip(),
                "name": p.get("name", ""),
                "service_ids": sids,
            }
        )
    return {"services": srv_rows, "plans": plan_rows}


def category_name_map(categories: list) -> dict:
    return {c["id"]: c.get("name", "") for c in categories}


def service_name_map(services: list) -> dict:
    return {s["id"]: s.get("name", "") for s in services}


def build_category_relation_maps(categories: list) -> tuple[dict[str, str], dict[str, list[str]]]:
    kind_map: dict[str, str] = {}
    children_by_parent: dict[str, list[str]] = {}
    for c in categories:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not cid.strip():
            continue
        kind = c.get("kind")
        kind_map[cid] = kind if kind in ("parent", "child") else "parent"
        if kind_map[cid] == "child":
            parent_id = c.get("parent_id")
            if isinstance(parent_id, str) and parent_id.strip():
                children_by_parent.setdefault(parent_id, []).append(cid)
    return kind_map, children_by_parent


def expand_plan_category_ids(
    selected_category_ids: list[str], kind_map: dict[str, str], children_by_parent: dict[str, list[str]]
) -> set[str]:
    expanded: set[str] = set()
    for cid in selected_category_ids:
        if cid not in kind_map:
            continue
        expanded.add(cid)
        if kind_map.get(cid) == "parent":
            for child_id in children_by_parent.get(cid, []):
                expanded.add(child_id)
    return expanded


def resolve_plan_services(
    services: list, selected_category_ids: list[str], direct_service_ids: list[str], categories: list
) -> list[str]:
    kind_map, children_by_parent = build_category_relation_maps(categories)
    expanded_categories = expand_plan_category_ids(selected_category_ids, kind_map, children_by_parent)
    merged: list[str] = []
    seen: set[str] = set()
    for sid in direct_service_ids:
        if not isinstance(sid, str) or not sid.strip():
            continue
        clean = sid.strip()
        if clean in seen:
            continue
        seen.add(clean)
        merged.append(clean)
    for svc in services:
        if not isinstance(svc, dict):
            continue
        sid = svc.get("id")
        if not isinstance(sid, str) or not sid.strip():
            continue
        clean_sid = sid.strip()
        if clean_sid in seen:
            continue
        svc_categories = {
            x.strip() for x in (svc.get("category_ids") or []) if isinstance(x, str) and x.strip()
        }
        if svc_categories & expanded_categories:
            seen.add(clean_sid)
            merged.append(clean_sid)
    return merged


def build_plan_service_sources(
    plans: list, services: list, categories: list
) -> dict[str, dict[str, list[str]]]:
    cat_map = category_name_map(categories)
    kind_map, children_by_parent = build_category_relation_maps(categories)
    services_by_id = {
        s["id"]: s for s in services if isinstance(s, dict) and isinstance(s.get("id"), str) and s.get("id")
    }
    out: dict[str, dict[str, list[str]]] = {}
    for pl in plans:
        if not isinstance(pl, dict):
            continue
        pid = pl.get("id")
        if not isinstance(pid, str) or not pid.strip():
            continue
        selected = [x for x in (pl.get("category_ids") or []) if isinstance(x, str) and x.strip()]
        expanded = expand_plan_category_ids(selected, kind_map, children_by_parent)
        service_sources: dict[str, list[str]] = {}
        for sid in (pl.get("service_ids") or []):
            if not isinstance(sid, str) or not sid.strip():
                continue
            svc = services_by_id.get(sid)
            if not svc:
                continue
            svc_categories = {
                x.strip() for x in (svc.get("category_ids") or []) if isinstance(x, str) and x.strip()
            }
            source_labels = [
                cat_map.get(cid, cid)
                for cid in svc_categories
                if cid in expanded and cat_map.get(cid, cid)
            ]
            service_sources[sid] = sorted(set(source_labels))
        out[pid] = service_sources
    return out


def build_order_catalog(services: list, plans: list, customers: list, cat_map: dict) -> dict:
    catalog_services = []
    for s in services:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        cids = s.get("category_ids", []) or []
        labels = [cat_map.get(cid, "") for cid in cids if cat_map.get(cid)]
        catalog_services.append(
            {
                "id": s["id"],
                "name": s.get("name", ""),
                "price": s.get("price", ""),
                "description": s.get("description", ""),
                "amount": parse_price_amount(s.get("price", "")),
                "categories": labels,
                "category_ids": [x for x in cids if isinstance(x, str)],
            }
        )
    catalog_plans = []
    for p in plans:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        sids = [x for x in (p.get("service_ids") or []) if isinstance(x, str) and x.strip()]
        catalog_plans.append(
            {"id": p["id"], "name": p.get("name", ""), "service_ids": sids}
        )
    catalog_customers = []
    for c in customers:
        if isinstance(c, dict) and c.get("id"):
            catalog_customers.append(
                {
                    "id": c["id"],
                    "name": c.get("name", ""),
                    "phone": c.get("phone", ""),
                    "address": c.get("address", ""),
                }
            )
    return {
        "services": catalog_services,
        "plans": catalog_plans,
        "customers": catalog_customers,
    }


def create_app():
    app = Flask(__name__)

    def admin_context() -> dict:
        categories = normalize_categories(read_list("categories"))
        services = read_list("services")
        plans = read_list("plans")
        customers = read_list("customers")
        cat_map = category_name_map(categories)
        srv_map = service_name_map(services)
        order_catalog = build_order_catalog(services, plans, customers, cat_map)
        plan_service_sources = build_plan_service_sources(plans, services, categories)
        return {
            "categories": categories,
            "category_groups": build_category_groups(categories),
            "category_name_map": cat_map,
            "services": services,
            "plans": plans,
            "customers": customers,
            "service_name_map": srv_map,
            "order_catalog": order_catalog,
            "plan_service_sources": plan_service_sources,
        }

    @app.route("/")
    def index():
        categories = normalize_categories(read_list("categories"))
        services = read_list("services")
        plans = read_list("plans")
        order_category_groups = build_order_category_groups(services, categories)
        checkout_catalog = build_checkout_catalog(services, plans)
        service_by_id = {
            s["id"]: s
            for s in services
            if isinstance(s, dict) and isinstance(s.get("id"), str) and s.get("id")
        }
        return render_template(
            "order.html",
            order_category_groups=order_category_groups,
            plans=plans,
            checkout_catalog=checkout_catalog,
            service_by_id=service_by_id,
        )

    @app.route("/modir")
    def modir():
        return render_template("index.html", **admin_context())

    @app.get("/tailwind.js")
    def serve_tailwind_bundle():
        return send_from_directory(app.root_path, "tailwind.js")

    @app.get("/assets/<path:filename>")
    def serve_assets(filename: str):
        return send_from_directory(Path(app.root_path) / "assets", filename)

    @app.post("/add/category")
    def add_category():
        name = request.form.get("name", "")
        kind = request.form.get("kind", "parent")
        if kind not in ("parent", "child"):
            kind = "parent"
        parent_id = (request.form.get("parent_id") or None) if kind == "child" else None
        append_category(name, kind, parent_id)
        return redirect(url_for("modir"))

    @app.post("/category/<cid>/edit")
    def category_edit(cid):
        update_category(
            cid,
            request.form.get("name", ""),
            request.form.get("parent_id") or None,
        )
        return redirect(url_for("modir"))

    @app.post("/category/<cid>/delete")
    def category_delete(cid):
        delete_category_by_id(cid)
        return redirect(url_for("modir"))

    @app.post("/add/service")
    def add_service():
        append_service(
            request.form.get("name", ""),
            request.form.getlist("category_ids"),
            request.form.get("price", ""),
            request.form.get("description", ""),
        )
        return redirect(url_for("modir"))

    @app.post("/service/<sid>/edit")
    def edit_service(sid):
        update_service(
            sid,
            request.form.get("name", ""),
            request.form.getlist("category_ids"),
            request.form.get("price", ""),
            request.form.get("description", ""),
        )
        return redirect(url_for("modir"))

    @app.post("/service/<sid>/delete")
    def remove_service(sid):
        delete_service_by_id(sid)
        return redirect(url_for("modir"))

    @app.post("/add/plan")
    def add_plan():
        categories = normalize_categories(read_list("categories"))
        services = read_list("services")
        selected_categories = request.form.getlist("category_ids")
        direct_services = request.form.getlist("service_ids")
        merged_services = resolve_plan_services(
            services=services,
            selected_category_ids=selected_categories,
            direct_service_ids=direct_services,
            categories=categories,
        )
        append_plan(
            request.form.get("name", ""),
            selected_categories,
            merged_services,
        )
        return redirect(url_for("modir"))

    @app.post("/add/customer")
    def add_customer():
        append_customer(
            request.form.get("name", ""),
            request.form.get("phone", ""),
            request.form.get("address", ""),
        )
        return redirect(url_for("modir"))

    @app.post("/customer/<cid>/edit")
    def customer_edit(cid):
        update_customer_row(
            cid,
            request.form.get("name", ""),
            request.form.get("phone", ""),
            request.form.get("address", ""),
        )
        return redirect(url_for("modir"))

    @app.post("/customer/<cid>/delete")
    def customer_delete(cid):
        delete_customer_by_id(cid)
        return redirect(url_for("modir"))

    @app.post("/orders")
    def create_order():
        data = request.get_json(silent=True) or {}
        raw_sids = data.get("service_ids") or []
        raw_pids = data.get("plan_ids") or []
        service_ids_in = [x.strip() for x in raw_sids if isinstance(x, str) and x.strip()]
        plan_ids_in = [x.strip() for x in raw_pids if isinstance(x, str) and x.strip()]

        services_all = read_list("services")
        plans_all = read_list("plans")
        srv_by_id = {
            s["id"]: s
            for s in services_all
            if isinstance(s, dict) and s.get("id")
        }

        merged: set[str] = set()
        for sid in service_ids_in:
            if sid in srv_by_id:
                merged.add(sid)
        valid_plan_ids: list[str] = []
        for pid in plan_ids_in:
            pl = next(
                (p for p in plans_all if isinstance(p, dict) and p.get("id") == pid),
                None,
            )
            if not pl:
                continue
            valid_plan_ids.append(pid)
            for sid in pl.get("service_ids", []) or []:
                if isinstance(sid, str) and sid.strip() and sid.strip() in srv_by_id:
                    merged.add(sid.strip())

        if not merged:
            return jsonify({"ok": False, "error": "no_services"}), 400

        merged_list = list(merged)
        details: list[dict] = []
        total = 0
        for sid in merged_list:
            s = srv_by_id[sid]
            total += parse_price_amount(s.get("price", ""))
            details.append(
                {
                    "id": sid,
                    "name": s.get("name", ""),
                    "price": s.get("price", ""),
                    "description": s.get("description", ""),
                }
            )

        mode = (data.get("customer_mode") or "new").strip()
        cust_in = data.get("customer") or {}

        if mode == "existing":
            cid = (data.get("customer_id") or "").strip()
            if not cid:
                return jsonify({"ok": False, "error": "customer"}), 400
            customers = read_list("customers")
            c = find_customer(customers, cid)
            if not c:
                return jsonify({"ok": False, "error": "customer_not_found"}), 400
            snapshot = {
                "name": c.get("name", ""),
                "phone": c.get("phone", ""),
                "address": c.get("address", ""),
            }
        else:
            name = (cust_in.get("name") or "").strip()
            if not name:
                return jsonify({"ok": False, "error": "name"}), 400
            new_id = append_customer(
                name,
                cust_in.get("phone", ""),
                cust_in.get("address", ""),
            )
            if not new_id:
                return jsonify({"ok": False, "error": "customer_create"}), 400
            cid = new_id
            snapshot = {
                "name": name,
                "phone": (cust_in.get("phone") or "").strip(),
                "address": (cust_in.get("address") or "").strip(),
            }

        oid = append_order(
            cid,
            snapshot,
            valid_plan_ids,
            merged_list,
            details,
            total,
        )
        receipt_path = create_receipt_pdf(
            order_id=oid,
            customer_snapshot=snapshot,
            services_detail=details,
            total_amount=total,
        )
        return jsonify({"ok": True, "order_id": oid, "receipt_path": receipt_path})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
