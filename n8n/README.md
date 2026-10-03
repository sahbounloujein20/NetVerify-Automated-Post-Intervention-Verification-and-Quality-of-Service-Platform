# n8n automation — NetVerify

Workflow: **`netverify-verification.json`** — "NetVerify — D+14 compliance control".

It carries three responsibilities on a single pipeline:

| Trigger | Cadence | Effect |
|---|---|---|
| Schedule | every day at 06:00 | backend health → refresh → D+14 control → e-mail |
| Webhook `POST /webhook/netverify-verification` | on demand | same pipeline, called by the "Run the verification" button of the dashboard, which receives the report back |
| Collection | every hour | `POST /measurements/refresh-all`, so that the morning control works on fresh measurements |

## Installation

### 1. Service token

The backend accepts automatons through the `X-Service-Token` header (see
`Backend/security.py`). Generate the secret:

```powershell
python Backend/manage_users.py service-token
```

Declare it on the backend side (`.env` at the root, never versioned):

```
NETVERIFY_SERVICE_TOKEN=<the token>
```

### 2. n8n credentials

The workflow contains **no secret in clear text**: it points at two credentials
to create in the n8n UI (*Credentials → New*).

| Type | Expected name | Setting |
|---|---|---|
| **Header Auth** | `NetVerify — Service token` | Name = `X-Service-Token`, Value = the generated token |
| **SMTP** | `SMTP NetVerify` | sending server; for Gmail, an [app password](https://myaccount.google.com/apppasswords), not the account password |

### 3. Import

1. `docker compose up -d` from this folder, then <http://localhost:5678>.
2. *Workflows → Import from File* → `netverify-verification.json`.
3. Open every node marked in red and **re-select the credential**: the
   identifiers in the file are placeholders (`REMPLACER_PAR_ID_CREDENTIAL`),
   which n8n cannot resolve on import.
4. Open **`NetVerify parameters`** and adjust: `api_base_url`, `recipients`,
   `sender`.
5. Activate the workflow (switch at the top right).

> **If an old `netverify-workflow.json` is still present**, disable or delete it
> before activating this one: two active workflows cannot share the
> `netverify-verification` webhook path.

### 4. `api_base_url` depending on how n8n is launched

| n8n runs… | Value |
|---|---|
| in a container (`docker compose`, the default case) | `http://host.docker.internal:8000` |
| natively (`npx n8n`) | `http://127.0.0.1:8000` |

From inside the n8n container, `127.0.0.1` designates n8n itself, not the
backend — that is the most frequent cause of failure on a first launch.

## Troubleshooting

### "Execute workflow" stays pending, nothing runs

The *Waiting for you to call the Test URL* banner on the `Dashboard trigger`
node is not an error: the workflow has three triggers, and the *Execute
workflow* button puts the **webhook** into listening mode. Three ways to
actually run a test:

| What you want to test | How |
|---|---|
| The full pipeline, as the dashboard does | Leave n8n listening, then click "Run the verification" in Streamlit — or `curl -X POST http://localhost:5678/webhook-test/netverify-verification` |
| The scheduled 06:00 control | Right-click on `Daily control — 06:00` → **Execute step** |
| The hourly collection | Right-click on `Hourly collection` → **Execute step** |

The `/webhook-test/…` path only exists while the editor is listening. Once the
workflow is **activated**, it is `/webhook/…` that answers permanently — that is
the one `NETVERIFY_N8N_WEBHOOK` points at.

### Red triangles on the nodes

Six nodes carry one after import: `Refresh the measurements`, `D+14 compliance
control`, `Collection — refresh the measurements` (Header Auth) and the three
e-mail nodes (SMTP). The credential identifiers in the file are placeholders:
n8n cannot resolve them, so each node has to be opened and the credential
**re-selected** from the drop-down list (step 2 then 3 above).

Hovering over the triangle always shows the exact reason. On an HTTP node with
no credential, an invalid-URL warning at rest is normal: the expression
`{{ $json.api_base_url }}` only resolves at run time, once the
`NetVerify parameters` node has been passed.

## Verifying the installation

1. **Empty run** — *Execute workflow* button in the editor, or from the
   dashboard. The execution must finish green, and the webhook response must
   contain `nb_anomalies`.
2. **Backend switched off** — stop the backend, run again: the pipeline must
   stop on `Backend health`, send the *Technical alert* and return a **200** to
   the dashboard with `error.message`.
3. **E-mail** — on a control with anomalies, check that the report sorted by
   urgency is received.

## Design choices

- **Backend health first.** Separates "the backend is switched off" from "the
  control crashed": two causes, two diagnoses, two recovery instructions.
- **Non-blocking refresh.** If it fails (timeout, 6 calls/hour quota reached),
  the control runs anyway on the last known measurements: a control on
  yesterday's data beats no control at all.
- **No retry on the pre-control refresh.** The endpoint is capped at 6
  calls/hour; insisting would burn the quota of the hourly collection.
- **All the formatting in a single Code node.** The HTML rendering and the
  indicators are computed once, in readable JavaScript, instead of 40-line
  expressions in the fields of the e-mail nodes.
- **Work orders with no measurement are excluded from the compliance rate.** A
  work order with no NetScan measurement is neither compliant nor at fault;
  counting it in the denominator would sink the rate because of a probe gap, not
  because of a service defect.
- **No "all clear" digest on a manual click.** The result is already displayed
  on screen; only the scheduled control sends the daily digest.
- **The dashboard always receives a 200**, on success as on failure. A 5xx would
  make Streamlit fall back on the direct backend call
  (`/verification/run`) and replay a control that has already run,
  duplicating the follow-up logs.
- **Response wired in parallel with the e-mails.** The e-mail node overwrites
  the JSON of the item: placing the response behind it would lose the body to
  return.

## Webhook security

The webhook is open: n8n listens on `localhost` only and the dashboard sends no
authentication header. To close it once the deployment leaves the local machine,
set the `Dashboard trigger` node to *Authentication → Header Auth* and make
`api.post_url` in `frontend/netverify/api.py` carry the same header.
