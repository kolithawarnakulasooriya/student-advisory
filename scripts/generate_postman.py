#!/usr/bin/env python3
"""Generate reproducible Postman 2.1 assets from the committed backend contract."""

import argparse
import copy
import json
import re
from pathlib import Path
from uuid import UUID, uuid5

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "postman"
PREFIX = "/api/v1"
NAMESPACE = UUID("20000000-0000-4000-8000-000000000001")


def fixture(name):
    return str(uuid5(NAMESPACE, name))


VALUES = {
    "profile_version": "0",
    "schema_version": "1",
    "schema_id": fixture("onboarding:department-a:1"),
    "source_id": "",
    "source_version_id": "",
    "source_version": "0",
    "context": "",
    "institution_id": fixture("synthetic"),
    "parent_id": fixture("college"),
    "kind": "college",
    "organization_id": fixture("department-a"),
    "organization_version": "",
    "organization_grant_id": "",
    "organization_grant_version": "",
    "base_url": "http://localhost:8000",
    "web_origin": "http://localhost:3000",
    "login_email": "manager@advisory.test",
    "registration_email": "",
    "registered_email": "",
    "actor_user_id": "",
    "display_name": "Synthetic Postman user",
    "verification_challenge": "",
    "scope_id": fixture("department-a"),
    "other_scope_id": fixture("department-b"),
    "org_unit_id": fixture("department-a"),
    "purpose": "administration",
    "limit": "25",
    "cursor": "",
    "target_email": "student-a@advisory.test",
    "user_id": fixture("student-a"),
    "grant_epoch": "",
    "request_id": "",
    "request_version": "",
    "requested_role": "student",
    "justification": "Synthetic Postman enrollment request",
    "invitation_id": "",
    "invitation_version": "",
    "invitation_email": "postman-invited@advisory.test",
    "invitation_token": "",
    "invitation_role": "student",
    "membership_grant_id": fixture("grant:student-a:department-a"),
    "membership_version": "",
    "student_membership_id": fixture("grant:student-a:department-a"),
    "assignment_version": "",
    "advisor_grant_id": fixture("grant:advisor-a:department-a"),
    "role_grant_id": fixture("grant:secretary:department-a"),
    "role_grant_version": "",
    "appointment_role": "advisor",
    "platform_grant_id": "",
    "platform_grant_version": "",
    "lifecycle_status": "suspended",
    "account_status": "suspended",
    "reason": "Synthetic local API exercise",
    "idempotency_key": "",
}

BODIES = {
    "RegisterInput": {"email": "{{new_email}}", "name": "{{display_name}}"},
    "EmailInput": {"email": "{{login_email}}"},
    "VerifyInput": {"challenge": "{{verification_challenge}}"},
    "RequestInput": {
        "org_unit_id": "{{scope_id}}",
        "requested_role": "{{requested_role}}",
        "justification": "{{justification}}",
    },
    "DecisionInput": {
        "reason": "{{reason}}",
        "advisor_grant_id": "{{advisor_grant_id}}",
    },
    "InviteInput": {
        "org_unit_id": "{{scope_id}}",
        "email": "{{invitation_email}}",
        "role": "{{invitation_role}}",
        "advisor_grant_id": "{{advisor_grant_id}}",
        "capabilities": [],
    },
    "AcceptInput": {"token": "{{invitation_token}}"},
    "ReasonInput": {"reason": "{{reason}}"},
    "LifecycleInput": {
        "status": "{{lifecycle_status}}",
        "reason": "{{reason}}",
        "advisor_grant_id": "{{advisor_grant_id}}",
    },
    "AssignmentInput": {
        "advisor_grant_id": "{{advisor_grant_id}}",
        "reason": "{{reason}}",
    },
    "GrantInput": {
        "user_id": "{{user_id}}",
        "org_unit_id": "{{scope_id}}",
        "role": "{{appointment_role}}",
        "capabilities": [],
        "ceiling": "advisor",
        "capacity": None,
        "advisor_grant_id": "{{advisor_grant_id}}",
        "reason": "{{reason}}",
    },
    "DelegationInput": {
        "capabilities": [
            "student.invite",
            "student.approve",
            "student.manage",
            "assignment.manage",
        ],
        "ceiling": "advisor",
        "capacity": None,
        "reason": "{{reason}}",
    },
    "PlatformInput": {"user_id": "{{user_id}}", "reason": "{{reason}}"},
    "AccountInput": {
        "status": "{{account_status}}",
        "approved_grant_ids": [],
        "reason": "{{reason}}",
    },
}


BODIES.update(
    {
        "OrganizationCreate": {
            "institution_id": "{{institution_id}}",
            "kind": "college",
            "parent_id": None,
            "name": "Synthetic Postman college",
            "code": "postman-college",
            "timezone": "UTC",
            "reason": "{{reason}}",
        },
        "OrganizationMetadata": {
            "name": "Synthetic renamed organization",
            "code": "postman-organization",
            "timezone": "UTC",
            "reason": "{{reason}}",
        },
        "EnrollmentInput": {"enabled": True, "reason": "{{reason}}"},
        "OrganizationGrantInput": {
            "user_id": "{{user_id}}",
            "institution_id": "{{institution_id}}",
            "scope_kind": "college",
            "root_org_unit_id": "{{parent_id}}",
            "reason": "{{reason}}",
        },
        "OrganizationGrantState": {
            "status": "{{lifecycle_status}}",
            "reason": "{{reason}}",
        },
    }
)

BODIES.update(
    {
        "SchemaInput": {
            "activate": True,
            "definition": {
                "fields": [
                    {
                        "key": "program",
                        "label": "Program",
                        "kind": "choice",
                        "required": True,
                        "choices": ["Synthetic Program"],
                    },
                    {
                        "key": "catalog_year",
                        "label": "Catalog year",
                        "kind": "choice",
                        "required": True,
                        "choices": ["2026"],
                    },
                ],
                "terms": ["2026 Fall", "2027 Spring"],
                "program_tracks": {},
            },
        },
        "ProfileInput": {
            "schema_id": "{{schema_id}}",
            "status": "draft",
            "facts": {"program": {"value": "Synthetic Program"}},
            "catalog_confirmed": False,
        },
        "ReviewInput": {
            "field": "program",
            "decision": "confirmed",
            "reason": "Synthetic advisor review",
        },
        "SourceMetadata": {
            "title": "Synthetic Postman document",
            "document_class": "other",
            "authority_rank": 0,
        },
        "TextInput": {
            "institution_id": "{{institution_id}}",
            "org_unit_id": "{{scope_id}}",
            "student_membership_id": "{{student_membership_id}}",
            "visibility": "student",
            "metadata": {
                "title": "Synthetic Postman document",
                "document_class": "student_evidence",
                "authority_rank": 0,
            },
            "text": "Synthetic document evidence. No institutional policy.",
        },
    }
)


def event(kind, code):
    return {
        "listen": kind,
        "script": {"type": "text/javascript", "exec": code.strip().splitlines()},
    }


def group(path):
    if "/profile" in path:
        return "15 Student profiles"
    resource = path.removeprefix(PREFIX + "/").split("/")[0]
    return {
        "departments": "14 Onboarding schemas",
        "sources": "16 Document intake",
        "admin": "12 Organization administration",
        "organization-admin-grants": "13 Organization administration grants",
        "health": "01 Health",
        "auth": "02 Identity and sessions",
        "me": "03 Account and organizations",
        "org-units": "03 Account and organizations",
        "membership-options": "04 Enrollment requests",
        "membership-requests": "04 Enrollment requests",
        "invitations": "05 Invitations",
        "memberships": "06 Membership lifecycle",
        "students": "07 Students and assignments",
        "eligible-advisors": "07 Students and assignments",
        "assignment-state": "07 Students and assignments",
        "role-grants": "08 Scoped appointments and delegation",
        "platform-grants": "09 Platform administration",
        "users": "10 Users and history",
        "audit-events": "11 Audit",
    }[resource]


def path_variable(path, name):
    if name == "gid":
        return {
            "memberships": "membership_grant_id",
            "role-grants": "role_grant_id",
            "platform-grants": "platform_grant_id",
            "organization-admin-grants": "organization_grant_id",
        }[path.split("/")[3]]
    return {
        "sid": "schema_id" if "/onboarding-schemas/" in path else "source_id",
        "vid": "source_version_id",
        "mid": "student_membership_id",
        "iid": "invitation_id",
        "rid": "request_id",
        "uid": "user_id",
        "org_id": "org_unit_id",
        "oid": "organization_id",
    }[name]


def revision(path, method):
    if method == "get":
        return None
    if "/profile" in path:
        return "profile_version"
    if "/sources" in path:
        return "source_version"
    if "/onboarding-schemas" in path:
        return "schema_version"
    if "{oid}" in path:
        return "organization_version"
    if "{rid}" in path:
        return "request_version"
    if "{iid}" in path:
        return "invitation_version"
    if path.endswith("/advisor"):
        return "assignment_version"
    if "{uid}" in path:
        return "grant_epoch"
    if "{gid}" in path:
        return {
            "memberships": "membership_version",
            "role-grants": "role_grant_version",
            "platform-grants": "platform_grant_version",
            "organization-admin-grants": "organization_grant_version",
        }[path.split("/")[3]]
    return None


def capture_scripts(path, method):
    scripts = []

    def capture(field, variable):
        scripts.append(
            f'if (data.{field} !== undefined && data.{field} !== null) pm.environment.set("{variable}", String(data.{field}));'
        )

    if "/onboarding-schemas" in path:
        capture("version", "schema_version")
        capture("active_schema_id", "schema_id")
    if "/profile" in path and not path.endswith("/history"):
        capture("version", "profile_version")
        capture("context_version", "context")
    if "/sources" in path and not path.endswith(
        ("/download", "/extraction", "/versions")
    ):
        capture("id", "source_id")
        capture("source_version_id", "source_version_id")
        capture("version", "source_version")
    if (
        path.startswith(PREFIX + "/admin/org-units")
        and (method != "get" or "{oid}" in path)
        and not path.endswith("/history")
    ):
        capture("id", "organization_id")
        capture("version", "organization_version")
    if path.startswith(PREFIX + "/organization-admin-grants") and method != "get":
        capture("id", "organization_grant_id")
        capture("version", "organization_grant_version")
    if path == PREFIX + "/me":
        capture("user_id", "actor_user_id")
        scripts.append(
            'if (!pm.variables.get("scope_id") && data.active_scope) pm.environment.set("scope_id", data.active_scope);'
        )
    if path == PREFIX + "/auth/register":
        scripts.append(
            'pm.environment.set("registered_email", pm.variables.get("new_email"));'
        )
    if path == PREFIX + "/auth/verify":
        scripts.append('pm.environment.unset("verification_challenge");')
    if path == PREFIX + "/auth/logout":
        scripts.append(
            'pm.environment.unset("actor_user_id"); pm.environment.unset("verification_challenge");'
        )
    if path.startswith(PREFIX + "/membership-requests") and method != "get":
        capture("id", "request_id")
        capture("version", "request_version")
    if (
        path.startswith(PREFIX + "/invitations")
        and method != "get"
        and not path.endswith("/accept")
    ):
        capture("id", "invitation_id")
        capture("version", "invitation_version")
    if path == PREFIX + "/invitations/accept":
        scripts.append('pm.environment.unset("invitation_token");')
    if path.startswith(PREFIX + "/memberships/") or path.endswith(
        "/invitations/accept"
    ):
        capture("id", "membership_grant_id")
        capture("version", "membership_version")
        capture("student_membership_id", "student_membership_id")
    if path.startswith(PREFIX + "/role-grants") and method != "get":
        capture("id", "role_grant_id")
        capture("version", "role_grant_version")
    if path.startswith(PREFIX + "/platform-grants") and method != "get":
        capture("id", "platform_grant_id")
        capture("version", "platform_grant_version")
    if path == PREFIX + "/assignment-state/{mid}" or (
        path == PREFIX + "/students/{mid}" and method == "get"
    ):
        capture("version", "assignment_version")
    if path.endswith("/advisor") and method == "put":
        scripts.append(
            'pm.environment.unset("assignment_version"); // Read assignment-state before another update.'
        )
    if path == PREFIX + "/users" and method == "get":
        scripts.append(
            'const target = data.items.find(u => u.email === pm.variables.get("target_email")); if (target) { pm.environment.set("user_id", target.id); pm.environment.set("grant_epoch", String(target.grant_epoch)); }'
        )
    if path == PREFIX + "/users/{uid}/state":
        scripts.append(
            'pm.environment.unset("grant_epoch"); // Search the user again for a fresh revision.'
        )
    return scripts


def make_request(path, method, operation):
    headers = [{"key": "Accept", "value": "application/json"}]
    params = operation.get("parameters", [])
    rendered_path = re.sub(
        r"\{(\w+)\}", lambda m: "{{" + path_variable(path, m[1]) + "}}", path
    )
    query = []
    for parameter in params:
        if parameter["in"] != "query":
            continue
        name = parameter["name"]
        query.append(
            {
                "key": name,
                "value": "{{" + ("target_email" if name == "email" else name) + "}}",
                "disabled": name in {"cursor", "parent_id", "kind"}
                or (name == "scope_id" and not parameter.get("required")),
            }
        )
    suffix = "&".join(q["key"] + "=" + q["value"] for q in query if not q["disabled"])
    url = {
        "raw": "{{base_url}}" + rendered_path + ("?" + suffix if suffix else ""),
        "host": ["{{base_url}}"],
        "path": rendered_path.strip("/").split("/"),
        "query": query,
    }
    schema_name = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref", "")
        .split("/")[-1]
    )
    description = [
        f"{method.upper()} {path}. Generated from OpenAPI {operation['operationId']}."
    ]
    request = {
        "method": method.upper(),
        "header": headers,
        "url": url,
        "description": "",
    }
    pre = []
    if method != "get":
        headers.extend(
            [
                {"key": "Origin", "value": "{{web_origin}}"},
                {"key": "X-CSRF-Token", "value": "{{csrf_token}}"},
            ]
        )
        if "/auth/" not in path:
            headers.append({"key": "Idempotency-Key", "value": "{{operation_key}}"})
            description.append(
                "Requires current authority, simulated staff MFA where applicable, and recent authentication. Each send uses a new idempotency key; set idempotency_key to retry the same logical operation."
            )
    rev = revision(path, method)
    if rev:
        headers.append({"key": "If-Match", "value": '"{{' + rev + '}}"'})
        pre.append(
            f'if (!/^\\d+$/.test(String(pm.variables.get("{rev}") || ""))) {{ pm.execution.skipRequest(); throw new Error("Read the current resource and set {rev} before this mutation."); }}'
        )
        description.append(f"Requires a fresh {rev}; stale revisions return 409.")
    if path.endswith("/sources/uploads"):
        request["body"] = {
            "mode": "formdata",
            "formdata": [
                {
                    "key": "target",
                    "type": "text",
                    "value": json.dumps(BODIES["TextInput"] | {"text": None}),
                },
                {"key": "file", "type": "file", "src": ""},
            ],
        }
        target = dict(BODIES["TextInput"])
        target.pop("text")
        request["body"]["formdata"][0]["value"] = json.dumps(target)
        description.append(
            "Choose a synthetic local file. The target part is JSON; scope is immutable on replacement."
        )
    if schema_name:
        body = copy.deepcopy(BODIES[schema_name])
        if path.endswith("/reject"):
            body.pop("advisor_grant_id", None)
        if path.startswith(PREFIX + "/platform-grants"):
            body.pop("advisor_grant_id", None)
        headers.append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
        description.append(
            "Body schema: "
            + schema_name
            + ". Edit the example for your intended role/action; server authorization always applies."
        )
    if path.endswith("/auth/register"):
        pre.append(
            'pm.variables.set("new_email", pm.variables.get("registration_email") || "postman-" + Date.now() + "@advisory.test");'
        )
    if path.endswith("/invitations/accept"):
        description.append(
            "Paste the token from the local Mailpit link fragment into the local invitation_token value. Sign in/verify as the invited email first. Success clears that variable. The API never returns the delivery token."
        )
    if path == PREFIX + "/me":
        description.append(
            "scope_id is disabled initially: enable it to select a department. Only actor_user_id is captured, never target user_id."
        )
    if method == "get" and any(q["key"] == "cursor" for q in query):
        description.append(
            "Enable cursor and paste this response's next_cursor for the next page; retain actor, scope, purpose, email filter and limit. A changed binding returns 409."
        )
    request["description"] = "\n\n".join(description)
    status = next(int(code) for code in operation["responses"] if code.startswith("2"))
    binary = path.endswith("/download")
    tests = (
        [
            f'pm.test("Expected HTTP {status}", () => pm.response.to.have.status({status}));',
            "if (pm.response.code >= 200 && pm.response.code < 300) {",
            "const data = {};" if binary else "const data = pm.response.json();",
        ]
        + capture_scripts(path, method)
        + ["}"]
    )
    item = {
        "name": f"{method.upper()} {path.removeprefix(PREFIX)} — {operation['summary']}",
        "request": request,
        "event": [event("test", "\n".join(tests))],
        "response": [],
    }
    if pre:
        item["event"].insert(0, event("prerequest", "\n".join(pre)))
    return item


def generate():
    contract = json.loads((ROOT / "backend/contracts/openapi.json").read_text())
    groups = {}
    operations = {}
    for path, methods in contract["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            item = make_request(path, method, operation)
            groups.setdefault(group(path), []).append(item)
            operations[(method, path)] = item
    smoke = []
    for method, path in [
        ("get", "/health/live"),
        ("get", "/health/ready"),
        ("post", "/auth/sign-in"),
        ("post", "/auth/simulator/step-up"),
        ("get", "/me"),
        ("get", "/org-units/{org_id}"),
        ("post", "/auth/logout"),
        ("get", "/me"),
    ]:
        item = copy.deepcopy(operations[(method, PREFIX + path)])
        if path == "/org-units/{org_id}":
            item["name"] = "Wrong-scope organization returns generic 404"
            item["request"]["url"]["raw"] = (
                "{{base_url}}/api/v1/org-units/{{other_scope_id}}"
            )
            item["request"]["url"]["path"][-1] = "{{other_scope_id}}"
            item["event"] = [
                event(
                    "test",
                    'pm.test("Wrong scope denied", () => pm.response.to.have.status(404)); pm.test("Generic not-found", () => pm.expect(pm.response.json().code).to.equal("NOT_FOUND"));',
                )
            ]
        if (
            path == "/me"
            and smoke
            and smoke[-1]["request"]["url"]["raw"].endswith("/auth/logout")
        ):
            item["name"] = "Logged-out session returns 401"
            item["event"] = [
                event(
                    "test",
                    'pm.test("Session revoked", () => pm.response.to.have.status(401));',
                )
            ]
        smoke.append(item)
    collection = {
        "info": {
            "_postman_id": "70162eaa-7d57-4a23-a9e4-1d946ac1d716",
            "name": "Student Advisory Backend — Release " + contract["info"]["version"],
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": f"All {len(operations)} current backend operations, generated from backend/contracts/openapi.json. Import the local environment and read postman/README.md. Run only 00 Smoke for a sequential check; the reference folders require deliberate role, target and revision selection. Cookie sessions; no bearer tokens. Synthetic local data only. CSRF is fetched before mutations and tokens stay in the cookie jar or request-local variables. No operator/bootstrap, Mailpit-internal, future academic, or cloud APIs are invented.",
        },
        "auth": {"type": "noauth"},
        "event": [
            event("prerequest", (DEST / "prerequest.js").read_text()),
            event("test", (DEST / "postresponse.js").read_text()),
        ],
        "item": [
            {
                "name": "00 Smoke",
                "description": "Run this folder with the default manager fixture: health, sign-in, simulated MFA, /me, wrong-scope denial, logout and revocation. No memberships are changed.",
                "item": smoke,
            }
        ]
        + [
            {
                "name": name,
                "description": "API reference: send individual requests with the appropriate role, target, current revision and prerequisites. This folder is not a sequential scenario.",
                "item": items,
            }
            for name, items in sorted(groups.items())
        ],
        "variable": [
            {"key": key, "value": value, "type": "string"}
            for key, value in VALUES.items()
        ],
    }
    environment = {
        "id": "e5148742-a1b7-4a83-9526-74ae5e6fe2cc",
        "name": "Student Advisory — Local synthetic",
        "_postman_variable_scope": "environment",
        "values": [
            {
                "key": key,
                "value": value,
                "type": "secret"
                if key in {"invitation_token", "verification_challenge"}
                else "default",
                "enabled": True,
            }
            for key, value in VALUES.items()
        ],
    }
    return {
        "Student-Advisory.postman_collection.json": collection,
        "Local.postman_environment.json": environment,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, value in generate().items():
        path = DEST / name
        expected = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != expected:
                raise SystemExit(
                    f"Postman drift: regenerate with python3 scripts/generate_postman.py ({name})"
                )
        else:
            path.write_text(expected)
    print(
        "Postman assets match OpenAPI."
        if args.check
        else "Generated Postman collection and local environment."
    )


if __name__ == "__main__":
    main()
