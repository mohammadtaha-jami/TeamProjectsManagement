from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for

from json_store import (
    append_category,
    append_customer,
    append_order,
    append_plan,
    append_service,
    delete_service_by_id,
    find_customer,
    normalize_categories,
    parse_price_amount,
    read_list,
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


def category_name_map(categories: list) -> dict:
    return {c["id"]: c.get("name", "") for c in categories}


def service_name_map(services: list) -> dict:
    return {s["id"]: s.get("name", "") for s in services}


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

    @app.route("/")
    def index():
        categories = normalize_categories(read_list("categories"))
        services = read_list("services")
        plans = read_list("plans")
        customers = read_list("customers")
        cat_map = category_name_map(categories)
        srv_map = service_name_map(services)
        order_catalog = build_order_catalog(services, plans, customers, cat_map)
        return render_template(
            "index.html",
            categories=categories,
            category_groups=build_category_groups(categories),
            category_name_map=cat_map,
            services=services,
            plans=plans,
            customers=customers,
            service_name_map=srv_map,
            order_catalog=order_catalog,
        )

    @app.get("/tailwind.js")
    def serve_tailwind_bundle():
        return send_from_directory(app.root_path, "tailwind.js")

    @app.post("/add/category")
    def add_category():
        name = request.form.get("name", "")
        kind = request.form.get("kind", "parent")
        if kind not in ("parent", "child"):
            kind = "parent"
        parent_id = (request.form.get("parent_id") or None) if kind == "child" else None
        append_category(name, kind, parent_id)
        return redirect(url_for("index"))

    @app.post("/add/service")
    def add_service():
        append_service(
            request.form.get("name", ""),
            request.form.getlist("category_ids"),
            request.form.get("price", ""),
            request.form.get("description", ""),
        )
        return redirect(url_for("index"))

    @app.post("/service/<sid>/edit")
    def edit_service(sid):
        update_service(
            sid,
            request.form.get("name", ""),
            request.form.getlist("category_ids"),
            request.form.get("price", ""),
            request.form.get("description", ""),
        )
        return redirect(url_for("index"))

    @app.post("/service/<sid>/delete")
    def remove_service(sid):
        delete_service_by_id(sid)
        return redirect(url_for("index"))

    @app.post("/add/plan")
    def add_plan():
        append_plan(
            request.form.get("name", ""),
            request.form.getlist("category_ids"),
            request.form.getlist("service_ids"),
        )
        return redirect(url_for("index"))

    @app.post("/add/customer")
    def add_customer():
        append_customer(
            request.form.get("name", ""),
            request.form.get("phone", ""),
            request.form.get("address", ""),
        )
        return redirect(url_for("index"))

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
