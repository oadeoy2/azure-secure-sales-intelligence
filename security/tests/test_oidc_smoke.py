"""Offline OIDC smoke regression tests. All HTTP is mocked; no cloud calls."""
import base64
import contextlib
import io
import json
from pathlib import Path
import runpy
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse


ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / ".github/scripts/oidc-smoke.py"))
RUN = MODULE["run_smoke"]
GLOBALS = RUN.__globals__
NOW = 2_000_000_000
CANARY = "SYNTHETIC_PRIVATE_TOKEN_NEVER_PRINT"
COMMIT = "a" * 40


def jwt(claims, algorithm="RS256"):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return encode({"alg": algorithm}) + "." + encode(claims) + ".synthetic-signature"


class OIDCSmokeTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "subscription_id": "00000000-0000-0000-0000-000000000002",
            "client_id": "00000000-0000-0000-0000-000000000003",
            "principal_id": "00000000-0000-0000-0000-000000000004",
            "subject": "repo:demo-owner@111/sales-lab@222:environment:lab-plan",
            "resource_group_name": "rg-smoke-lab", "location": "eastus2",
            "tags": {"project": "synthetic-sales"}, "repository": "demo-owner/sales-lab",
            "repository_id": "222", "repository_owner_id": "111",
            "workflow_ref": "demo-owner/sales-lab/.github/workflows/oidc-smoke.yml@refs/heads/main",
        }
        self.context["resource_group_id"] = "/subscriptions/" + self.context["subscription_id"] + "/resourceGroups/rg-smoke-lab"
        self.environment = {
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
            "GITHUB_REPOSITORY": self.context["repository"], "GITHUB_REPOSITORY_ID": "222",
            "GITHUB_REPOSITORY_OWNER_ID": "111", "GITHUB_WORKFLOW_REF": self.context["workflow_ref"],
            "GITHUB_SHA": COMMIT, "REVIEWED_COMMIT": COMMIT,
            "SMOKE_CONFIRMATION": "READ_ONLY_PLAN_IDENTITY_SMOKE",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://runner.actions.githubusercontent.com/oidc?audience=wrong&api-version=1",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": CANARY + "_RUNTIME",
        }
        self.github_claims = {
            "iss": "https://token.actions.githubusercontent.com", "aud": "api://AzureADTokenExchange",
            "sub": self.context["subject"], "repository": self.context["repository"], "repository_id": "222",
            "repository_owner_id": "111", "ref": "refs/heads/main", "sha": COMMIT, "environment": "lab-plan",
            "workflow_ref": self.context["workflow_ref"], "workflow_sha": COMMIT, "event_name": "workflow_dispatch",
            "exp": NOW + 600, "nbf": NOW - 5, "private_canary": CANARY,
        }
        self.access_claims = {
            "iss": "https://sts.windows.net/" + self.context["tenant_id"] + "/",
            "aud": "https://management.azure.com/", "tid": self.context["tenant_id"],
            "oid": self.context["principal_id"], "appid": self.context["client_id"],
            "exp": NOW + 600, "nbf": NOW - 5, "private_canary": CANARY,
        }
        self.group = {"id": self.context["resource_group_id"], "location": "eastus2",
                      "properties": {"provisioningState": "Succeeded"}, "tags": self.context["tags"]}
        self.calls = []
        self.fail_at = None
        self.failure = None
        self.algorithm = "RS256"
        self.assertion_override = None

    def fake_http(self, url, *, method="GET", headers=None, data=None):
        self.calls.append((url, method, headers or {}, data))
        index = len(self.calls)
        if index == self.fail_at:
            raise self.failure
        if index == 1:
            return {"value": self.assertion_override or jwt(self.github_claims, self.algorithm)}
        if index == 2:
            return {"token_type": "Bearer", "access_token": jwt(self.access_claims)}
        if index == 3:
            return self.group
        raise AssertionError("Unexpected HTTP request")

    def execute(self):
        self.environment["OIDC_SMOKE_CONTEXT"] = json.dumps(self.context)
        output, errors = io.StringIO(), io.StringIO()
        # The script must not invoke a CLI or write token/context files. The
        # real transport is patched before entry; fallback HTTP is forbidden.
        with patch.dict(GLOBALS, {"request_json": self.fake_http}), patch.object(time, "time", return_value=NOW), \
                patch("builtins.open", side_effect=AssertionError("Filesystem use forbidden")), \
                patch("pathlib.Path.open", side_effect=AssertionError("Filesystem use forbidden")), \
                patch("pathlib.Path.write_text", side_effect=AssertionError("Token files forbidden")), \
                patch("pathlib.Path.write_bytes", side_effect=AssertionError("Token files forbidden")), \
                patch("subprocess.run", side_effect=AssertionError("CLI use forbidden")), \
                patch("subprocess.Popen", side_effect=AssertionError("CLI use forbidden")), \
                patch("os.system", side_effect=AssertionError("Shell use forbidden")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("Live HTTP forbidden")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = RUN(self.environment)
        rendered = output.getvalue() + errors.getvalue()
        for private in (CANARY, self.context["subject"], self.context["principal_id"],
                        jwt(self.github_claims), jwt(self.access_claims)):
            self.assertNotIn(private, rendered)
        self.assertEqual(errors.getvalue(), "")
        result = json.loads(output.getvalue())
        self.assertTrue(all(isinstance(value, bool) for key, value in result.items()
                            if key not in {"failure_stage", "error_class", "http_status", "aad_error_codes"}))
        return code, result

    def transport_error(self, url, payload, status=400):
        error = urllib.error.HTTPError(url, status, CANARY, {}, io.BytesIO(payload))
        with patch("urllib.request.build_opener") as builder:
            builder.return_value.open.side_effect = error
            with self.assertRaises(MODULE["SmokeHttpError"]) as caught:
                MODULE["request_json"](url, method="POST" if "login.microsoftonline.com" in url else "GET")
        self.assertNotIn(CANARY, str(caught.exception))
        return caught.exception, error

    def test_success_has_only_three_approved_requests(self):
        code, result = self.execute()
        self.assertEqual(code, 0)
        self.assertTrue(result["approved_group_read_succeeded"])
        self.assertEqual(len(self.calls), 3)
        github, entra, arm = self.calls
        self.assertEqual(urllib.parse.urlsplit(github[0]).hostname, "runner.actions.githubusercontent.com")
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(github[0]).query)["audience"], ["api://AzureADTokenExchange"])
        self.assertEqual((github[1], github[3]), ("GET", None))
        self.assertEqual(entra[0], "https://login.microsoftonline.com/" + self.context["tenant_id"] + "/oauth2/v2.0/token")
        self.assertEqual(entra[1], "POST")
        form = urllib.parse.parse_qs(entra[3].decode())
        self.assertEqual(form["client_id"], [self.context["client_id"]])
        # ARM's resource identifier ends in '/', followed by '/.default'.
        self.assertEqual(form["scope"], ["https://management.azure.com//.default"])
        self.assertEqual(form["client_assertion"], [jwt(self.github_claims)])
        self.assertEqual(arm[0], "https://management.azure.com" + self.context["resource_group_id"] + "?api-version=2021-04-01")
        self.assertEqual((arm[1], arm[3]), ("GET", None))
        self.assertFalse(any("blob.core.windows.net" in call[0] for call in self.calls))

    def test_github_claim_mismatches_stop_before_exchange(self):
        for key in ("iss", "aud", "sub", "repository", "repository_id", "repository_owner_id", "ref", "sha", "environment", "workflow_ref", "workflow_sha", "event_name"):
            with self.subTest(claim=key):
                old = self.github_claims[key]
                self.github_claims[key] = "wrong"
                self.calls = []
                code, result = self.execute()
                self.assertEqual((code, len(self.calls)), (1, 1))
                self.assertEqual(result["failure_stage"], "github_assertion")
                self.github_claims[key] = old

    def test_access_claim_mismatches_stop_before_arm(self):
        for key in ("iss", "aud", "tid", "oid", "appid"):
            with self.subTest(claim=key):
                old = self.access_claims[key]
                self.access_claims[key] = "wrong"
                self.calls = []
                code, result = self.execute()
                self.assertEqual((code, len(self.calls)), (1, 2))
                self.assertEqual(result["failure_stage"], "access_claims")
                self.access_claims[key] = old

    def test_conflicting_azp_is_rejected(self):
        self.access_claims["azp"] = "00000000-0000-0000-0000-000000000005"
        self.assertEqual(self.execute()[0], 1)
        self.assertEqual(len(self.calls), 2)

    def test_v2_issuer_and_azp_only_client_are_supported(self):
        self.access_claims["iss"] = "https://login.microsoftonline.com/" + self.context["tenant_id"] + "/v2.0"
        self.access_claims["azp"] = self.access_claims.pop("appid")
        self.assertEqual(self.execute()[0], 0)

    def test_invalid_lifetime_or_algorithm_is_rejected(self):
        for claims in (self.github_claims, self.access_claims):
            for key, value in (("exp", NOW), ("nbf", NOW + 61)):
                old = claims[key]
                claims[key] = value
                self.calls = []
                self.assertEqual(self.execute()[0], 1)
                claims[key] = old
        self.calls = []
        self.algorithm = "none"
        self.assertEqual(self.execute()[0], 1)
        self.assertEqual(len(self.calls), 1)

    def test_wrong_event_ref_commit_or_confirmation_never_requests_a_token(self):
        for key, value in (("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_REF", "refs/heads/feature"),
                           ("REVIEWED_COMMIT", "b" * 40), ("SMOKE_CONFIRMATION", "wrong")):
            old = self.environment[key]
            self.environment[key] = value
            self.calls = []
            self.assertEqual(self.execute()[0], 1)
            self.assertEqual(self.calls, [])
            self.environment[key] = old

    def test_unapproved_runtime_hosts_and_redirects_are_rejected(self):
        for url in ("http://runner.actions.githubusercontent.com/token", "https://evil.example/token",
                    "https://runner.actions.githubusercontent.com.evil.example/token", "https://user@runner.actions.githubusercontent.com/token",
                    "https://runner.actions.githubusercontent.com:444/token"):
            self.environment["ACTIONS_ID_TOKEN_REQUEST_URL"] = url
            self.calls = []
            self.assertEqual(self.execute()[0], 1)
            self.assertEqual(self.calls, [])
        with self.assertRaises(MODULE["SmokeError"]):
            MODULE["NoRedirect"]().redirect_request(None, None, 302, CANARY, {}, "https://evil.example/" + CANARY)

    def test_http_failures_never_print_response_or_tokens(self):
        for stage in (1, 2, 3):
            self.calls = []
            self.fail_at = stage
            self.failure = urllib.error.HTTPError("https://example.invalid/" + CANARY, 403, CANARY, {}, io.BytesIO(CANARY.encode()))
            self.assertEqual(self.execute()[0], 1)
            self.assertEqual(len(self.calls), stage)

    def test_malformed_token_and_wrong_group_are_not_success(self):
        self.assertion_override = CANARY
        self.assertEqual(self.execute()[0], 1)
        self.assertion_override = None
        self.calls = []
        self.group["id"] += "-wrong"
        self.assertEqual(self.execute()[0], 1)

    def test_context_identity_and_subject_injection_never_reaches_http(self):
        for key, value in (("tenant_id", "../other-tenant"), ("client_id", "not-a-uuid"),
                           ("principal_id", "not-a-uuid"), ("subject", "repo:wrong:environment:lab-deploy"),
                           ("resource_group_id", "https://evil.example/" + CANARY)):
            old = self.context[key]
            self.context[key] = value
            self.calls = []
            self.assertEqual(self.execute()[0], 1)
            self.assertEqual(self.calls, [])
            self.context[key] = old

    def test_entra_transport_failure_exposes_only_bounded_numeric_diagnostics(self):
        url = "https://login.microsoftonline.com/" + self.context["tenant_id"] + "/oauth2/v2.0/token"
        payload = json.dumps({"error_description": CANARY, "access_token": CANARY,
                              "error_codes": [700213, True, CANARY, -1, 100000000, 700016, 500011, 123]}).encode()
        error, _ = self.transport_error(url, payload)
        self.assertEqual(error.http_status, 400)
        self.assertEqual(error.aad_error_codes, [700213, 700016, 500011])
        self.fail_at, self.failure = 2, error
        code, result = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(result["failure_stage"], "entra_exchange")
        self.assertEqual(result["http_status"], 400)
        self.assertEqual(result["aad_error_codes"], [700213, 700016, 500011])

    def test_other_host_failure_body_is_not_read_or_reported(self):
        error, original = self.transport_error("https://management.azure.com/" + CANARY,
                                                json.dumps({"error_codes": [700213], "description": CANARY}).encode(), 403)
        self.assertEqual(original.fp.tell(), 0)
        self.assertEqual(error.aad_error_codes, [])
        self.fail_at, self.failure = 3, error
        code, result = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(result["http_status"], 403)
        self.assertNotIn("aad_error_codes", result)

    def test_oversized_or_malformed_failure_has_no_parsed_codes(self):
        url = "https://login.microsoftonline.com/" + self.context["tenant_id"] + "/oauth2/v2.0/token"
        for payload in (b"x" * 8193 + CANARY.encode(), CANARY.encode()):
            with self.subTest(size=len(payload)):
                error, original = self.transport_error(url, payload)
                self.assertLessEqual(original.fp.tell(), 8193)
                self.assertEqual(error.aad_error_codes, [])
                self.calls = []
                self.fail_at, self.failure = 2, error
                self.assertEqual(self.execute()[0], 1)


if __name__ == "__main__":
    unittest.main()
