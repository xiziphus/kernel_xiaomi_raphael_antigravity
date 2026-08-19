# ERPNext MCP server

Gives an MCP client (Claude Code, Claude Desktop) direct access to the ERPNext
site running on the phone — query records, create and edit documents, call
Frappe methods, run reports.

## Read this before you install it

The credentials are **Administrator** API keys. That is the ERP's root account:
every doctype, every record, no permission checks worth the name. An MCP client
holding them can read your entire ledger and, with writes on, delete it.

Two mitigations are built in, and you should keep both:

* **Writes are off by default.** `erp_create`, `erp_update`, `erp_delete` and
  `erp_method(write=true)` refuse to run unless `ERPNEXT_ALLOW_WRITE=1` is set.
  Run read-only unless you are actively doing a task that needs writes.
* **Credentials live in the client config**, not in this repo. Nothing here
  contains a key.

If the keys leak, rotate them: `python3 tools/rotate_key.py` (below) or delete
`api_key`/`api_secret` on the Administrator user in ERPNext.

## Install

```bash
cd mcp/erpnext
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Configure

### Claude Code

```bash
claude mcp add erpnext \
  --env ERPNEXT_URL=https://erp.stratifyx.win \
  --env ERPNEXT_API_KEY=<key> \
  --env ERPNEXT_API_SECRET=<secret> \
  -- /absolute/path/to/mcp/erpnext/.venv/bin/python /absolute/path/to/mcp/erpnext/server.py
```

Add `--env ERPNEXT_ALLOW_WRITE=1` only when you want it to be able to change data.

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "erpnext": {
      "command": "/absolute/path/to/mcp/erpnext/.venv/bin/python",
      "args": ["/absolute/path/to/mcp/erpnext/server.py"],
      "env": {
        "ERPNEXT_URL": "https://erp.stratifyx.win",
        "ERPNEXT_API_KEY": "<key>",
        "ERPNEXT_API_SECRET": "<secret>"
      }
    }
  }
}
```

Restart the client. Paths must be absolute — the client does not run from this
directory.

## Tools

| tool | what it does |
|---|---|
| `erp_list_doctypes(search, limit)` | discover what tables exist |
| `erp_list(doctype, fields, filters, order_by, limit)` | query records |
| `erp_get(doctype, name)` | one full document, child tables included |
| `erp_create(doctype, doc)` | **write** |
| `erp_update(doctype, name, updates)` | **write** |
| `erp_delete(doctype, name)` | **write**, irreversible |
| `erp_method(method, args, write)` | any whitelisted Frappe method |
| `erp_report(report, filters)` | run a query report |

`filters` uses Frappe syntax: `{"status": "Open"}` for equality,
`{"grand_total": [">", 1000]}` for operators.

## Things to ask it

    what doctypes are there matching "invoice"?
    list the 10 most recent Sales Invoices with customer and grand_total
    show me Sales Invoice ACC-SINV-2026-00001 in full
    run the General Ledger report for this month
    which GST returns does india_compliance track?

With writes enabled:

    create a Customer called "Acme Ltd" in territory India
    set the due date on ACC-SINV-2026-00001 to 30 days out

## How it talks to ERPNext

Plain Frappe REST over the Cloudflare tunnel — `/api/resource/<doctype>` for
documents, `/api/method/<dotted.path>` for methods. Nothing is installed on the
phone; the server runs on your machine and the site sees ordinary API calls.
So it works from anywhere the site is reachable, and it stops working the
moment the tunnel or the phone does.

Errors return Frappe's response body rather than just an HTTP status, because
Frappe puts the useful part (`_server_messages`, the traceback) in the body.

## Rotating the credentials

On the phone:

```bash
adb shell su -c '/data/local/tmp/nd/bin/docker -H unix:///data/local/tmp/nd/docker.sock \
  exec -w /home/frappe/frappe-bench/sites erpnext-backend-1 ../env/bin/python /tmp/genkey.py'
```

That regenerates `api_secret` for Administrator and prints the new pair; the old
secret stops working immediately.
