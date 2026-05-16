from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for

from json_store import (
    append_category,
    append_customer,
    append_custom_order,
    append_order,
    append_plan,
    append_service,
    delete_category_by_id,
    delete_customer_by_id,
    delete_service_by_id,
    find_customer,
    find_order_by_source,
    normalize_categories,
    parse_price_amount,
    read_list,
    update_category,
    update_customer_row,
    update_service,
)
from receipt_pdf import issue_invoice_for_stored_order


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
                "terms": [x.strip() for x in (s.get("terms") or []) if isinstance(x, str) and x.strip()],
                "extra_note": s.get("extra_note", ""),
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
        terms = [x.strip() for x in (p.get("terms") or []) if isinstance(x, str) and x.strip()]
        price_text = p.get("price", "")
        plan_rows.append(
            {
                "id": pid.strip(),
                "name": p.get("name", ""),
                "service_ids": sids,
                "price": price_text,
                "amount": parse_price_amount(price_text),
                "terms": terms,
                "extra_note": p.get("extra_note", ""),
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
                "terms": [x.strip() for x in (s.get("terms") or []) if isinstance(x, str) and x.strip()],
                "extra_note": s.get("extra_note", ""),
            }
        )
    catalog_plans = []
    for p in plans:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        sids = [x for x in (p.get("service_ids") or []) if isinstance(x, str) and x.strip()]
        terms = [x.strip() for x in (p.get("terms") or []) if isinstance(x, str) and x.strip()]
        price_text = p.get("price", "")
        catalog_plans.append(
            {
                "id": p["id"],
                "name": p.get("name", ""),
                "service_ids": sids,
                "price": price_text,
                "amount": parse_price_amount(price_text),
                "terms": terms,
                "extra_note": p.get("extra_note", ""),
            }
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

    def normalize_invoice_type(raw) -> str:
        t = str(raw or "current").strip()
        if t not in ("current", "simple", "roadmap"):
            return "current"
        return t

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

    @app.get("/receipts/<path:filename>")
    def serve_receipt_file(filename: str):
        safe_name = Path(filename).name
        return send_from_directory(Path(app.root_path) / "reciept", safe_name)

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
            "",
            [x.strip() for x in request.form.getlist("terms") if isinstance(x, str) and x.strip()],
            request.form.get("extra_note", ""),
        )
        return redirect(url_for("modir"))

    @app.post("/service/<sid>/edit")
    def edit_service(sid):
        update_service(
            sid,
            request.form.get("name", ""),
            request.form.getlist("category_ids"),
            request.form.get("price", ""),
            "",
            [x.strip() for x in request.form.getlist("terms") if isinstance(x, str) and x.strip()],
            request.form.get("extra_note", ""),
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
            request.form.get("price", ""),
            [x.strip() for x in request.form.getlist("terms") if isinstance(x, str) and x.strip()],
            request.form.get("extra_note", ""),
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
        plan_by_id = {
            p["id"]: p
            for p in plans_all
            if isinstance(p, dict) and isinstance(p.get("id"), str) and p.get("id")
        }

        valid_service_ids: list[str] = []
        seen_service_ids: set[str] = set()
        for sid in service_ids_in:
            if sid in srv_by_id and sid not in seen_service_ids:
                seen_service_ids.add(sid)
                valid_service_ids.append(sid)
        valid_plan_ids: list[str] = []
        selected_plan_rows: list[dict] = []
        for pid in plan_ids_in:
            pl = plan_by_id.get(pid)
            if not pl:
                continue
            valid_plan_ids.append(pid)
            selected_plan_rows.append(pl)
        if not valid_service_ids and not valid_plan_ids:
            return jsonify({"ok": False, "error": "no_items"}), 400

        details: list[dict] = []
        total = 0
        for sid in valid_service_ids:
            s = srv_by_id[sid]
            total += parse_price_amount(s.get("price", ""))
            service_terms = [x.strip() for x in (s.get("terms") or []) if isinstance(x, str) and x.strip()]
            service_extra_note = (s.get("extra_note") or "").strip()
            legacy_description = (s.get("description") or "").strip()
            service_desc_parts: list[str] = []
            if service_terms:
                service_desc_parts.append("مفاد:")
                service_desc_parts.extend(f"- {x}" for x in service_terms)
            if service_extra_note:
                service_desc_parts.append("توضیحات تکمیلی:")
                service_desc_parts.append(service_extra_note)
            if not service_desc_parts and legacy_description:
                service_desc_parts.append(legacy_description)
            details.append(
                {
                    "id": sid,
                    "name": s.get("name", ""),
                    "price": s.get("price", ""),
                    "description": "\n".join(service_desc_parts),
                    "terms": service_terms,
                    "extra_note": service_extra_note,
                }
            )
        selected_plans_for_receipt: list[dict] = []
        for pl in selected_plan_rows:
            plan_price_text = pl.get("price", "")
            total += parse_price_amount(plan_price_text)
            details.append(
                {
                    "id": pl.get("id", ""),
                    "name": pl.get("name", ""),
                    "price": plan_price_text,
                    "description": "",
                }
            )
            selected_plans_for_receipt.append(
                {
                    "id": pl.get("id", ""),
                    "name": pl.get("name", ""),
                    "terms": [x.strip() for x in (pl.get("terms") or []) if isinstance(x, str) and x.strip()],
                    "extra_note": (pl.get("extra_note") or "").strip(),
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

        inv_t = normalize_invoice_type(data.get("invoice_type"))
        if inv_t == "simple":
            inv_t = "current"
        oid = append_order(
            cid,
            snapshot,
            valid_plan_ids,
            valid_service_ids,
            details,
            total,
            invoice_type=inv_t,
            selected_plans_snapshot=selected_plans_for_receipt,
        )
        return jsonify(
            {
                "ok": True,
                "order_id": oid,
                "source": "orders",
                "invoice_type": inv_t,
            }
        )

    @app.post("/custom-orders")
    def create_custom_order():
        data = request.get_json(silent=True) or {}
        inv_t = normalize_invoice_type(data.get("invoice_type"))

        def parse_positive_int(val, minimum: int = 1) -> int:
            if isinstance(val, bool):
                return minimum
            if isinstance(val, int):
                return max(minimum, val)
            if isinstance(val, float):
                return max(minimum, int(val))
            s = str(val or "").strip()
            for i, d in enumerate("۰۱۲۳۴۵۶۷۸۹"):
                s = s.replace(d, str(i))
            digits = "".join(c for c in s if c.isdigit())
            if not digits:
                return minimum
            return max(minimum, int(digits))

        cust_in = data.get("customer") or {}
        name = (cust_in.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "name"}), 400

        if inv_t == "simple":
            lines_in = data.get("simple_lines") or []
            if not isinstance(lines_in, list) or not lines_in:
                return jsonify({"ok": False, "error": "no_simple_lines"}), 400
            simple_lines_out: list[dict] = []
            total = 0
            for i, raw in enumerate(lines_in):
                if not isinstance(raw, dict):
                    continue
                nm = (raw.get("name") or "").strip()
                if not nm:
                    return jsonify({"ok": False, "error": "simple_line_name", "index": i}), 400
                qty = parse_positive_int(raw.get("quantity"), minimum=1)
                raw_price = raw.get("price")
                if isinstance(raw_price, (int, float)):
                    price_text = str(int(raw_price)) if float(raw_price) == int(raw_price) else str(raw_price)
                else:
                    price_text = (str(raw_price) if raw_price is not None else "").strip()
                unit = parse_price_amount(price_text)
                line_total = unit * qty
                total += line_total
                desc = (raw.get("description") or "")
                desc_text = desc if isinstance(desc, str) else ""
                desc_stripped = desc_text.strip()
                simple_lines_out.append(
                    {
                        "name": nm,
                        "price": price_text,
                        "unit_amount": unit,
                        "quantity": qty,
                        "description": desc_stripped,
                        "line_total": line_total,
                    }
                )
            if not simple_lines_out:
                return jsonify({"ok": False, "error": "no_simple_lines"}), 400

            new_id = append_customer(
                name,
                cust_in.get("phone", ""),
                cust_in.get("address", ""),
            )
            if not new_id:
                return jsonify({"ok": False, "error": "customer_create"}), 400
            snapshot = {
                "name": name,
                "phone": (cust_in.get("phone") or "").strip(),
                "address": (cust_in.get("address") or "").strip(),
            }
            oid = append_custom_order(
                new_id,
                snapshot,
                [],
                total,
                invoice_type="simple",
                simple_lines=simple_lines_out,
            )
            return jsonify({"ok": True, "order_id": oid, "source": "custom-order", "invoice_type": "simple"})

        steps_in = data.get("steps")
        if not isinstance(steps_in, list) or not steps_in:
            return jsonify({"ok": False, "error": "no_steps"}), 400

        steps_out: list[dict] = []
        total = 0
        for i, raw in enumerate(steps_in):
            if not isinstance(raw, dict):
                continue
            title = (raw.get("title") or "").strip()
            step_name = (raw.get("name") or "").strip()
            if not title and not step_name:
                return jsonify({"ok": False, "error": "step_title_or_name", "step_index": i}), 400
            desc = raw.get("description") or ""
            desc_text = desc if isinstance(desc, str) else ""
            lines = [ln.strip() for ln in desc_text.splitlines() if ln.strip()]
            raw_price = raw.get("price")
            if isinstance(raw_price, (int, float)):
                price_text = str(int(raw_price)) if float(raw_price) == int(raw_price) else str(raw_price)
            else:
                price_text = (str(raw_price) if raw_price is not None else "").strip()
            amt = parse_price_amount(price_text)
            total += amt
            steps_out.append(
                {
                    "title": title,
                    "name": step_name,
                    "description_lines": lines,
                    "price": price_text,
                    "price_amount": amt,
                }
            )

        if not steps_out:
            return jsonify({"ok": False, "error": "no_valid_steps"}), 400

        new_id = append_customer(
            name,
            cust_in.get("phone", ""),
            cust_in.get("address", ""),
        )
        if not new_id:
            return jsonify({"ok": False, "error": "customer_create"}), 400
        snapshot = {
            "name": name,
            "phone": (cust_in.get("phone") or "").strip(),
            "address": (cust_in.get("address") or "").strip(),
        }
        oid = append_custom_order(new_id, snapshot, steps_out, total, invoice_type=inv_t)
        return jsonify({"ok": True, "order_id": oid, "source": "custom-order", "invoice_type": inv_t})

    @app.post("/issue-invoice")
    def issue_invoice():
        data = request.get_json(silent=True) or {}
        src = (data.get("source") or "").strip()
        oid = (data.get("order_id") or "").strip()
        if src not in ("orders", "custom-order") or not oid:
            return jsonify({"ok": False, "error": "bad_request"}), 400
        row = find_order_by_source(src, oid)
        if not row:
            return jsonify({"ok": False, "error": "not_found"}), 404
        try:
            receipt_path = issue_invoice_for_stored_order(src, row)
        except RuntimeError as e:
            return jsonify({"ok": False, "error": "roadmap_pdf", "message": str(e)}), 500
        except Exception as e:
            return jsonify({"ok": False, "error": "pdf_failed", "message": str(e)}), 500
        receipt_url = url_for("serve_receipt_file", filename=Path(receipt_path).name)
        return jsonify({"ok": True, "receipt_path": receipt_path, "receipt_url": receipt_url})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
