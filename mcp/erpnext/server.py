#!/usr/bin/env python3
"""MCP server for ERPNext / Frappe.

Exposes an ERPNext site over the Model Context Protocol so an LLM client can
read and write documents, call whitelisted methods and run reports.

Auth is a Frappe API key/secret pair. The pair this was built for belongs to
**Administrator**, which means this server has unrestricted access to the site:
every doctype, every record, and destructive operations included. There is no
permission layer between the model and the database beyond what Frappe itself
enforces for Administrator, which is essentially nothing. Treat the credentials
as root for the ERP.

Transport is stdio, which is what Claude Desktop / Claude Code launch.
"""
import json
import os
import sys
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from mcp.server.mcpserver import MCPServer

BASE = os.environ.get("ERPNEXT_URL", "https://erp.stratifyx.win").rstrip("/")
KEY = os.environ.get("ERPNEXT_API_KEY", "")
SECRET = os.environ.get("ERPNEXT_API_SECRET", "")
TIMEOUT = float(os.environ.get("ERPNEXT_TIMEOUT", "60"))
# Opt-in guard. Default False so an accidental launch cannot delete anything.
ALLOW_WRITE = os.environ.get("ERPNEXT_ALLOW_WRITE", "").lower() in ("1", "true", "yes")

if not (KEY and SECRET):
    sys.exit("set ERPNEXT_API_KEY and ERPNEXT_API_SECRET")

HEADERS = {"Authorization": f"token {KEY}:{SECRET}", "Accept": "application/json"}
mcp = MCPServer(name="erpnext", instructions=__doc__)


async def call(method: str, path: str, **kw) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as c:
        r = await c.request(method, f"{BASE}{path}", **kw)
    if r.status_code >= 400:
        # Frappe puts the useful part in the body, not the HTTP reason.
        raise RuntimeError(f"{r.status_code} {r.text[:1500]}")
    return r.json() if r.content else {}


def need_write(tool: str) -> None:
    if not ALLOW_WRITE:
        raise RuntimeError(
            f"{tool} is a write operation and ERPNEXT_ALLOW_WRITE is not set. "
            "Restart the server with ERPNEXT_ALLOW_WRITE=1 to enable writes."
        )


def j(o: Any) -> str:
    return json.dumps(o, indent=2, default=str)[:100000]


@mcp.tool(description="List doctypes (tables). Use this to discover what exists before querying.")
async def erp_list_doctypes(search: str = "", limit: int = 50) -> str:
    q = {"limit_page_length": limit, "fields": json.dumps(["name"])}
    if search:
        q["filters"] = json.dumps([["name", "like", f"%{search}%"]])
    return j(await call("GET", f"/api/resource/DocType?{urlencode(q)}"))


@mcp.tool(description='List records. filters e.g. {"status":"Open"} or {"grand_total":[">",1000]}.')
async def erp_list(doctype: str, fields: list[str] | None = None,
                   filters: dict | None = None, order_by: str = "",
                   limit: int = 20) -> str:
    q = {"limit_page_length": limit, "fields": json.dumps(fields or ["name"])}
    if filters:
        q["filters"] = json.dumps(filters)
    if order_by:
        q["order_by"] = order_by
    return j(await call("GET", f"/api/resource/{quote(doctype)}?{urlencode(q)}"))


@mcp.tool(description="Fetch one full document including its child tables.")
async def erp_get(doctype: str, name: str) -> str:
    return j(await call("GET", f"/api/resource/{quote(doctype)}/{quote(name)}"))


@mcp.tool(description="Create a document. WRITE — needs ERPNEXT_ALLOW_WRITE=1.")
async def erp_create(doctype: str, doc: dict) -> str:
    need_write("erp_create")
    return j(await call("POST", f"/api/resource/{quote(doctype)}", json=doc))


@mcp.tool(description="Update fields on a document. WRITE — needs ERPNEXT_ALLOW_WRITE=1.")
async def erp_update(doctype: str, name: str, updates: dict) -> str:
    need_write("erp_update")
    return j(await call("PUT", f"/api/resource/{quote(doctype)}/{quote(name)}", json=updates))


@mcp.tool(description="Delete a document. WRITE, irreversible — needs ERPNEXT_ALLOW_WRITE=1.")
async def erp_delete(doctype: str, name: str) -> str:
    need_write("erp_delete")
    out = await call("DELETE", f"/api/resource/{quote(doctype)}/{quote(name)}")
    return j(out or {"deleted": name})


@mcp.tool(description="Call a whitelisted Frappe/ERPNext method. write=true issues a POST.")
async def erp_method(method: str, args: dict | None = None, write: bool = False) -> str:
    if write:
        need_write("erp_method(write)")
        return j(await call("POST", f"/api/method/{quote(method)}", json=args or {}))
    qs = urlencode(args or {})
    return j(await call("GET", f"/api/method/{quote(method)}" + (f"?{qs}" if qs else "")))


@mcp.tool(description="Run a query report and return its rows.")
async def erp_report(report: str, filters: dict | None = None) -> str:
    q = {"report_name": report, "filters": json.dumps(filters or {})}
    return j(await call("GET", f"/api/method/frappe.desk.query_report.run?{urlencode(q)}"))


if __name__ == "__main__":
    mcp.run()
