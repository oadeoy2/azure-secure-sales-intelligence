"""Bounded identity boundary checks; no state body, lease or cloud mutation.

Uses the reviewed smoke transport/claim primitives. Entra verifies assertion
signatures during real exchanges; local decoding alone is not authentication.
"""
from datetime import datetime, timezone
import email.utils
import importlib.util
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid


_spec = importlib.util.spec_from_file_location("reviewed_oidc_smoke", Path(__file__).with_name("oidc-smoke.py"))
_smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smoke)
require = _smoke.require
decode_claims = _smoke.decode_claims
request_json = _smoke.request_json
SmokeHttpError = _smoke.SmokeHttpError
CONFIRMATION = "READ_ONLY_IDENTITY_BOUNDARY_TESTS"
STORAGE_SCOPE = "https://storage.azure.com/.default"
STORAGE_AUDIENCES = {"https://storage.azure.com", "https://storage.azure.com/"}


def validate_context(environment):
    context = json.loads(environment["OIDC_ACCESS_CONTEXT"])
    fields = {"tenant_id", "subscription_id", "client_id", "principal_id", "subject", "resource_group_name",
              "resource_group_id", "location", "tags", "repository", "repository_id", "repository_owner_id",
              "workflow_ref", "identity_kind", "storage_account_name", "negative_client_id"}
    require(isinstance(context, dict) and set(context) == fields)
    kind = context["identity_kind"]
    require(kind in ("plan", "deploy") and environment["IDENTITY_KIND"] == kind)
    for field in ("tenant_id", "subscription_id", "client_id", "principal_id"):
        require(isinstance(context[field], str) and str(uuid.UUID(context[field])) == context[field].lower())
    if kind == "plan":
        require(isinstance(context["negative_client_id"], str) and str(uuid.UUID(context["negative_client_id"])) == context["negative_client_id"].lower())
        require(context["negative_client_id"].lower() != context["client_id"].lower())
    else:
        require(context["negative_client_id"] is None)
    require(re.fullmatch(r"[a-z0-9]{3,24}", context["storage_account_name"]))
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", context["repository"]))
    require(all(isinstance(context[name], str) and re.fullmatch(r"[1-9][0-9]*", context[name]) for name in ("repository_id", "repository_owner_id")))
    owner, repository = context["repository"].split("/")
    subject = "repo:" + owner + "@" + context["repository_owner_id"] + "/" + repository + "@" + context["repository_id"] + ":environment:lab-" + kind
    require(context["subject"] == subject)
    require(re.fullmatch(r"[A-Za-z0-9._()-]{1,90}", context["resource_group_name"]))
    require(context["resource_group_id"] == "/subscriptions/" + context["subscription_id"] + "/resourceGroups/" + context["resource_group_name"])
    require(re.fullmatch(r"[a-z0-9]+", context["location"]) and isinstance(context["tags"], dict))
    require(all(isinstance(k, str) and isinstance(v, str) for k, v in context["tags"].items()))
    workflow = context["repository"] + "/.github/workflows/oidc-access.yml@refs/heads/main"
    require(context["workflow_ref"] == workflow and environment["GITHUB_WORKFLOW_REF"] == workflow)
    require(environment["GITHUB_EVENT_NAME"] == "workflow_dispatch" and environment["GITHUB_REF"] == "refs/heads/main")
    require(environment["GITHUB_REPOSITORY"] == context["repository"] and environment["GITHUB_REPOSITORY_ID"] == context["repository_id"] and environment["GITHUB_REPOSITORY_OWNER_ID"] == context["repository_owner_id"])
    require(re.fullmatch(r"[0-9a-f]{40}", environment["GITHUB_SHA"]) and environment["REVIEWED_COMMIT"] == environment["GITHUB_SHA"] and environment["ACCESS_CONFIRMATION"] == CONFIRMATION)
    target = urllib.parse.urlsplit(environment["ACTIONS_ID_TOKEN_REQUEST_URL"])
    require(target.scheme == "https" and target.hostname and target.hostname.endswith(".actions.githubusercontent.com") and target.port in (None, 443) and not target.username and not target.password and not target.fragment)
    require(bool(environment["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]))
    return context


def validate_github(claims, context, environment):
    require(claims.get("iss") == _smoke.GITHUB_ISSUER and claims.get("aud") == _smoke.ASSERTION_AUDIENCE and claims.get("sub") == context["subject"])
    for name in ("repository", "repository_id", "repository_owner_id", "workflow_ref"):
        require(str(claims.get(name)) == context[name])
    require(claims.get("ref") == "refs/heads/main" and claims.get("event_name") == "workflow_dispatch" and claims.get("environment") == "lab-" + context["identity_kind"])
    require(claims.get("sha") == environment["GITHUB_SHA"] and claims.get("workflow_sha") == environment["GITHUB_SHA"])


def exchange(context, assertion, scope, client_id=None):
    body = urllib.parse.urlencode({"client_id": client_id or context["client_id"], "scope": scope,
                                   "grant_type": "client_credentials", "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                                   "client_assertion": assertion}).encode("ascii")
    return request_json("https://login.microsoftonline.com/" + context["tenant_id"] + "/oauth2/v2.0/token", method="POST",
                        headers={"Content-Type": "application/x-www-form-urlencoded"}, data=body)


def validate_access(response, context, audiences):
    require(response.get("token_type", "").lower() == "bearer")
    token = response["access_token"]
    claims = decode_claims(token)
    issuers = {"https://sts.windows.net/" + context["tenant_id"] + "/", "https://login.microsoftonline.com/" + context["tenant_id"] + "/v2.0"}
    require(claims.get("iss") in issuers and claims.get("aud") in audiences)
    require(claims.get("tid", "").lower() == context["tenant_id"].lower() and claims.get("oid", "").lower() == context["principal_id"].lower())
    clients = [claims[name] for name in ("appid", "azp") if name in claims]
    require(bool(clients) and all(isinstance(client, str) and client.lower() == context["client_id"].lower() for client in clients))
    return token


def head_blob(account, container, blob, token):
    require(re.fullmatch(r"[a-z0-9]{3,24}", account))
    require((container, blob) in {("lab-state", "lab.tfstate"), ("admin-state", "bootstrap-access.tfstate")})
    url = "https://" + account + ".blob.core.windows.net/" + container + "/" + blob
    request = urllib.request.Request(url, method="HEAD", headers={"Authorization": "Bearer " + token,
        "x-ms-version": "2023-11-03", "x-ms-date": email.utils.format_datetime(datetime.now(timezone.utc), usegmt=True)})
    opener = urllib.request.build_opener(_smoke.NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            # HEAD inspects only status/one allowlisted error header. Never read
            # a state body or expose metadata, ETag, lease or identifiers.
            return response.status, None
    except urllib.error.HTTPError as error:
        code = error.headers.get("x-ms-error-code") if error.headers else None
        return error.code, "AuthorizationPermissionMismatch" if code == "AuthorizationPermissionMismatch" else None


def run_access(environment=None):
    environment = os.environ if environment is None else environment
    stage = "context"
    result = {"context_valid": False, "github_claims_valid": False, "intended_arm_identity_valid": False,
              "wrong_subject_test_required": False, "wrong_subject_rejected": False, "approved_group_read_succeeded": False,
              "intended_storage_identity_valid": False, "lab_blob_head_succeeded": False, "admin_blob_head_denied": False}
    assertion = arm_token = storage_token = None
    try:
        context = validate_context(environment)
        result["context_valid"] = True
        result["wrong_subject_test_required"] = context["identity_kind"] == "plan"
        stage = "github_assertion"
        target = urllib.parse.urlsplit(environment["ACTIONS_ID_TOKEN_REQUEST_URL"])
        query = [(k, v) for k, v in urllib.parse.parse_qsl(target.query) if k != "audience"] + [("audience", _smoke.ASSERTION_AUDIENCE)]
        assertion = request_json(urllib.parse.urlunsplit(target._replace(query=urllib.parse.urlencode(query))),
                                 headers={"Authorization": "Bearer " + environment["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})["value"]
        validate_github(decode_claims(assertion), context, environment)
        result["github_claims_valid"] = True
        stage = "arm_token_exchange"
        arm_token = validate_access(exchange(context, assertion, "https://management.azure.com//.default"), context, _smoke.ARM_AUDIENCES)
        result["intended_arm_identity_valid"] = True
        if context["identity_kind"] == "plan":
            stage = "wrong_subject_exchange"
            try:
                exchange(context, assertion, "https://management.azure.com//.default", context["negative_client_id"])
            except SmokeHttpError as error:
                result["wrong_subject_http_status"] = error.http_status
                result["wrong_subject_aad_error_codes"] = error.aad_error_codes
                require(error.http_status in (400, 401) and bool(error.aad_error_codes) and set(error.aad_error_codes) <= {700213, 70021})
                result["wrong_subject_rejected"] = True
            # A valid plan assertion must never authenticate the deploy client.
            require(result["wrong_subject_rejected"])
        stage = "approved_group_get"
        group = request_json("https://management.azure.com" + context["resource_group_id"] + "?api-version=2021-04-01", headers={"Authorization": "Bearer " + arm_token})
        require(group.get("id", "").lower() == context["resource_group_id"].lower() and group.get("location", "").lower() == context["location"] and group.get("properties", {}).get("provisioningState") == "Succeeded")
        require(all(group.get("tags", {}).get(k) == v for k, v in context["tags"].items()))
        result["approved_group_read_succeeded"] = True
        stage = "storage_token_exchange"
        # Azure Storage SDK builds this scope from DefaultAudience and .default:
        # github.com/Azure/azure-sdk-for-net/blob/main/sdk/storage/Azure.Storage.Common/src/Shared/Constants.cs
        storage_token = validate_access(exchange(context, assertion, STORAGE_SCOPE), context, STORAGE_AUDIENCES)
        result["intended_storage_identity_valid"] = True
        stage = "lab_blob_head"
        status, _ = head_blob(context["storage_account_name"], "lab-state", "lab.tfstate", storage_token)
        result["lab_head_status"] = status if isinstance(status, int) and 100 <= status <= 599 else None
        require(status == 200)
        result["lab_blob_head_succeeded"] = True
        stage = "admin_blob_head"
        status, code = head_blob(context["storage_account_name"], "admin-state", "bootstrap-access.tfstate", storage_token)
        result["admin_head_status"] = status if isinstance(status, int) and 100 <= status <= 599 else None
        require(status == 403 and code == "AuthorizationPermissionMismatch")
        result["admin_blob_head_denied"] = True
        result["success"] = True
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        result.update(success=False, failure_stage=stage, error_class=type(error).__name__)
        if isinstance(error, SmokeHttpError):
            if error.http_status is not None:
                result["http_status"] = error.http_status
            if error.aad_error_codes:
                result["aad_error_codes"] = error.aad_error_codes
        print(json.dumps(result, sort_keys=True))
        return 1
    finally:
        # Python immutable strings cannot be securely erased; no tokens are
        # persisted, logged, cached or emitted as action outputs/artifacts.
        assertion = arm_token = storage_token = None


if __name__ == "__main__":
    raise SystemExit(run_access())
