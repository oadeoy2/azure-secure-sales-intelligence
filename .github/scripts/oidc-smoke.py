"""Bounded OIDC exchange and one ARM GET; credentials stay in process memory.

JWT claims are decoded from TLS-authenticated responses, not advertised as local
signature verification. Entra verifies the GitHub client assertion during the
real exchange, and ARM must accept the resulting token for the approved GET.
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


GITHUB_ISSUER = "https://token.actions.githubusercontent.com"
ASSERTION_AUDIENCE = "api://AzureADTokenExchange"
ARM_AUDIENCES = {"https://management.azure.com/", "https://management.azure.com",
                 "https://management.core.windows.net/", "https://management.core.windows.net"}
CONFIRMATION = "READ_ONLY_PLAN_IDENTITY_SMOKE"


class SmokeError(Exception):
    pass


class SmokeHttpError(SmokeError):
    def __init__(self, status, codes=None):
        super().__init__("HTTP request failed")
        self.http_status = status if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599 else None
        self.aad_error_codes = codes or []


def require(condition):
    if not condition:
        raise SmokeError("Rejected smoke precondition or claim")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SmokeError("Redirect rejected")


def request_json(url, *, method="GET", headers=None, data=None):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            require(response.status == 200)
            body = response.read(65537)
            require(len(body) <= 65536)
            result = json.loads(body)
            require(isinstance(result, dict))
            return result
    except urllib.error.HTTPError as error:
        codes = []
        target = urllib.parse.urlsplit(url)
        if target.hostname == "login.microsoftonline.com" and target.path.endswith("/oauth2/v2.0/token"):
            try:
                payload = error.read(8193)
                if len(payload) <= 8192:
                    failure = json.loads(payload)
                    raw_codes = failure.get("error_codes") if isinstance(failure, dict) else None
                    if isinstance(raw_codes, list):
                        codes = [code for code in raw_codes if isinstance(code, int) and not isinstance(code, bool) and 0 <= code <= 99999999][:3]
            except (OSError, ValueError, TypeError):
                pass
        raise SmokeHttpError(error.code, codes) from None


def validate_context(environment):
    context = json.loads(environment["OIDC_SMOKE_CONTEXT"])
    require(isinstance(context, dict))
    required = {"tenant_id", "subscription_id", "client_id", "principal_id", "subject",
                "resource_group_name", "resource_group_id", "location", "tags", "repository",
                "repository_id", "repository_owner_id", "workflow_ref"}
    require(set(context) == required)
    for name in ("tenant_id", "subscription_id", "client_id", "principal_id"):
        require(isinstance(context[name], str) and str(uuid.UUID(context[name])) == context[name].lower())
    for name in ("repository_id", "repository_owner_id"):
        require(isinstance(context[name], str) and re.fullmatch(r"[1-9][0-9]*", context[name]))
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", context["repository"]))
    require(re.fullmatch(r"[A-Za-z0-9._()-]{1,90}", context["resource_group_name"]))
    require(context["resource_group_id"] == "/subscriptions/" + context["subscription_id"] + "/resourceGroups/" + context["resource_group_name"])
    require(isinstance(context["subject"], str) and len(context["subject"]) <= 1024 and "*" not in context["subject"])
    owner, repository_name = context["repository"].split("/")
    immutable_subject = ("repo:" + owner + "@" + context["repository_owner_id"] + "/" + repository_name + "@" + context["repository_id"] + ":environment:lab-plan")
    require(context["subject"] == immutable_subject)
    require(isinstance(context["tags"], dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in context["tags"].items()))
    require(isinstance(context["location"], str) and re.fullmatch(r"[a-z0-9]+", context["location"]))
    expected_workflow = context["repository"] + "/.github/workflows/oidc-smoke.yml@refs/heads/main"
    require(context["workflow_ref"] == expected_workflow)
    require(environment["GITHUB_EVENT_NAME"] == "workflow_dispatch" and environment["GITHUB_REF"] == "refs/heads/main")
    require(environment["GITHUB_REPOSITORY"] == context["repository"] and environment["GITHUB_REPOSITORY_ID"] == context["repository_id"] and environment["GITHUB_REPOSITORY_OWNER_ID"] == context["repository_owner_id"])
    require(environment["GITHUB_WORKFLOW_REF"] == expected_workflow)
    require(re.fullmatch(r"[0-9a-f]{40}", environment["GITHUB_SHA"]) and environment["REVIEWED_COMMIT"] == environment["GITHUB_SHA"])
    require(environment["SMOKE_CONFIRMATION"] == CONFIRMATION)
    request_url = urllib.parse.urlsplit(environment["ACTIONS_ID_TOKEN_REQUEST_URL"])
    require(request_url.scheme == "https" and request_url.hostname is not None and request_url.hostname.endswith(".actions.githubusercontent.com") and not request_url.username and not request_url.password and request_url.port in (None, 443) and not request_url.fragment)
    require(bool(environment["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]))
    return context


def decode_claims(token):
    require(isinstance(token, str) and len(token) <= 32768)
    parts = token.split(".")
    require(len(parts) == 3 and all(parts))
    header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4)))
    require(header.get("alg") == "RS256")
    claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    require(isinstance(claims, dict))
    now = time.time()
    require(isinstance(claims.get("exp"), (int, float)) and claims["exp"] > now)
    require(isinstance(claims.get("nbf"), (int, float)) and claims["nbf"] <= now + 60)
    return claims


def validate_github_claims(claims, context, environment):
    require(claims.get("iss") == GITHUB_ISSUER and claims.get("aud") == ASSERTION_AUDIENCE and claims.get("sub") == context["subject"])
    require(claims.get("repository") == context["repository"] and str(claims.get("repository_id")) == context["repository_id"] and str(claims.get("repository_owner_id")) == context["repository_owner_id"])
    require(claims.get("ref") == "refs/heads/main" and claims.get("sha") == environment["GITHUB_SHA"] and claims.get("environment") == "lab-plan")
    require(claims.get("workflow_ref") == context["workflow_ref"] and claims.get("workflow_sha") == environment["GITHUB_SHA"] and claims.get("event_name") == "workflow_dispatch")


def validate_access_claims(claims, context):
    issuers = {"https://sts.windows.net/" + context["tenant_id"] + "/", "https://login.microsoftonline.com/" + context["tenant_id"] + "/v2.0"}
    require(claims.get("iss") in issuers and claims.get("aud") in ARM_AUDIENCES)
    require(claims.get("tid", "").lower() == context["tenant_id"].lower() and claims.get("oid", "").lower() == context["principal_id"].lower())
    clients = [claims[key] for key in ("appid", "azp") if key in claims]
    require(bool(clients) and all(isinstance(client, str) and client.lower() == context["client_id"].lower() for client in clients))


def run_smoke(environment=None):
    environment = os.environ if environment is None else environment
    stage = "context"
    result = {"context_valid": False, "github_claims_valid": False, "entra_exchange_succeeded": False,
              "access_claims_valid": False, "approved_group_read_succeeded": False}
    assertion = access_token = None
    try:
        context = validate_context(environment)
        result["context_valid"] = True
        stage = "github_assertion"
        parts = urllib.parse.urlsplit(environment["ACTIONS_ID_TOKEN_REQUEST_URL"])
        query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query) if key != "audience"]
        query.append(("audience", ASSERTION_AUDIENCE))
        request_url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
        assertion = request_json(request_url, headers={"Authorization": "Bearer " + environment["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})["value"]
        validate_github_claims(decode_claims(assertion), context, environment)
        result["github_claims_valid"] = True
        stage = "entra_exchange"
        # ARM's resource URI ends in '/'; preserve it before '/.default'.
        # https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc#trailing-slash-and-default
        body = urllib.parse.urlencode({"client_id": context["client_id"], "scope": "https://management.azure.com//.default",
                                       "grant_type": "client_credentials", "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                                       "client_assertion": assertion}).encode("ascii")
        exchanged = request_json("https://login.microsoftonline.com/" + context["tenant_id"] + "/oauth2/v2.0/token", method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"}, data=body)
        require(exchanged.get("token_type", "").lower() == "bearer")
        access_token = exchanged["access_token"]
        result["entra_exchange_succeeded"] = True
        stage = "access_claims"
        validate_access_claims(decode_claims(access_token), context)
        result["access_claims_valid"] = True
        stage = "approved_group_get"
        url = "https://management.azure.com" + context["resource_group_id"] + "?api-version=2021-04-01"
        group = request_json(url, headers={"Authorization": "Bearer " + access_token})
        require(group.get("id", "").lower() == context["resource_group_id"].lower() and group.get("location", "").lower() == context["location"])
        require(group.get("properties", {}).get("provisioningState") == "Succeeded")
        require(all(group.get("tags", {}).get(key) == value for key, value in context["tags"].items()))
        result["approved_group_read_succeeded"] = True
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
        # Drop references; Python cannot promise secure erasure of immutable
        # strings. No credential is written to disk, an output, cache or artifact.
        assertion = access_token = None


if __name__ == "__main__":
    raise SystemExit(run_smoke())
