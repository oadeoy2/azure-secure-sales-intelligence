"""Mocked identity-boundary regressions: no Azure/GitHub calls or state access."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import runpy
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.parse

import yaml
import test_oidc_smoke as fixtures


ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / ".github/scripts/oidc-access.py"))
RUN = MODULE["run_access"]
GLOBALS = RUN.__globals__


class IdentityAccessTests(unittest.TestCase):
    def setUp(self):
        base = fixtures.OIDCSmokeTests()
        base.setUp()
        self.context = deepcopy(base.context)
        self.context.update(identity_kind="plan", storage_account_name="syntheticstatelab",
                            negative_client_id="00000000-0000-0000-0000-000000000005")
        self.context["workflow_ref"] = self.context["workflow_ref"].replace("oidc-smoke.yml", "oidc-access.yml")
        self.environment = deepcopy(base.environment)
        self.environment.update(IDENTITY_KIND="plan", ACCESS_CONFIRMATION="READ_ONLY_IDENTITY_BOUNDARY_TESTS",
                                GITHUB_WORKFLOW_REF=self.context["workflow_ref"])
        self.github = deepcopy(base.github_claims)
        self.github["workflow_ref"] = self.context["workflow_ref"]
        self.arm = deepcopy(base.access_claims)
        self.storage = {**self.arm, "aud": "https://storage.azure.com/"}
        self.group = deepcopy(base.group)
        self.http_calls, self.head_calls = [], []
        self.negative_codes = [700213]
        self.negative_status = 400
        self.negative_success = False
        self.lab_status, self.admin_status, self.admin_code = 200, 403, "AuthorizationPermissionMismatch"
        self.raw_failure = None

    def configure_deploy(self):
        self.context.update(identity_kind="deploy", negative_client_id=None,
                            client_id="00000000-0000-0000-0000-000000000005",
                            principal_id="00000000-0000-0000-0000-000000000006")
        self.context["subject"] = self.context["subject"].replace(":lab-plan", ":lab-deploy")
        self.environment["IDENTITY_KIND"] = "deploy"
        self.github.update(sub=self.context["subject"], environment="lab-deploy")
        for claims in (self.arm, self.storage):
            claims.update(appid=self.context["client_id"], oid=self.context["principal_id"])

    def fake_json(self, url, *, method="GET", headers=None, data=None):
        self.http_calls.append((url, method, data))
        if self.raw_failure:
            raise self.raw_failure
        host = urllib.parse.urlsplit(url).hostname
        if host == "runner.actions.githubusercontent.com":
            return {"value": fixtures.jwt(self.github)}
        if host == "login.microsoftonline.com":
            form = urllib.parse.parse_qs(data.decode())
            if form["client_id"][0] == self.context["negative_client_id"]:
                if not self.negative_success:
                    raise MODULE["SmokeHttpError"](self.negative_status, self.negative_codes)
                return {"token_type": "Bearer", "access_token": fixtures.jwt(self.arm)}
            claims = self.storage if form["scope"] == [MODULE["STORAGE_SCOPE"]] else self.arm
            return {"token_type": "Bearer", "access_token": fixtures.jwt(claims)}
        if host == "management.azure.com":
            return self.group
        raise AssertionError("Unapproved network host")

    def fake_head(self, account, container, blob, token):
        self.head_calls.append((account, container, blob, token))
        return (self.lab_status, None) if container == "lab-state" else (self.admin_status, self.admin_code)

    def execute(self):
        self.environment["OIDC_ACCESS_CONTEXT"] = json.dumps(self.context)
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(GLOBALS, {"request_json": self.fake_json, "head_blob": self.fake_head}), \
                patch.object(time, "time", return_value=fixtures.NOW), \
                patch("builtins.open", side_effect=AssertionError("Filesystem forbidden")), \
                patch("pathlib.Path.open", side_effect=AssertionError("Filesystem forbidden")), \
                patch("pathlib.Path.write_text", side_effect=AssertionError("Token files forbidden")), \
                patch("subprocess.run", side_effect=AssertionError("CLI forbidden")), \
                patch("subprocess.Popen", side_effect=AssertionError("CLI forbidden")), \
                patch("os.system", side_effect=AssertionError("Shell forbidden")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("Live HTTP forbidden")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = RUN(self.environment)
        rendered = output.getvalue() + errors.getvalue()
        for private in (fixtures.CANARY, self.context["subject"], self.context["principal_id"],
                        fixtures.jwt(self.github), fixtures.jwt(self.arm), fixtures.jwt(self.storage)):
            self.assertNotIn(private, rendered)
        self.assertEqual(errors.getvalue(), "")
        return status, json.loads(output.getvalue())

    def test_plan_success_has_exact_hosts_methods_and_known_blob_heads(self):
        status, result = self.execute()
        self.assertEqual(status, 0)
        self.assertTrue(result["wrong_subject_rejected"])
        self.assertEqual(len(self.http_calls), 5)
        for url, method, body in self.http_calls:
            host = urllib.parse.urlsplit(url).hostname
            self.assertIn(host, {"runner.actions.githubusercontent.com", "login.microsoftonline.com", "management.azure.com"})
            self.assertEqual(method, "POST" if host == "login.microsoftonline.com" else "GET")
            if method == "POST":
                self.assertEqual(url, "https://login.microsoftonline.com/" + self.context["tenant_id"] + "/oauth2/v2.0/token")
                self.assertEqual(urllib.parse.parse_qs(body.decode())["client_assertion"], [fixtures.jwt(self.github)])
            elif host == "management.azure.com":
                self.assertEqual(url, "https://management.azure.com" + self.context["resource_group_id"] + "?api-version=2021-04-01")
        self.assertEqual([(call[1], call[2]) for call in self.head_calls],
                         [("lab-state", "lab.tfstate"), ("admin-state", "bootstrap-access.tfstate")])
        self.assertTrue(all(call[0] == self.context["storage_account_name"] and call[3] == fixtures.jwt(self.storage)
                            for call in self.head_calls))

    def test_deploy_success_skips_subject_negative_case(self):
        self.configure_deploy()
        status, result = self.execute()
        self.assertEqual(status, 0)
        self.assertFalse(result["wrong_subject_test_required"])
        self.assertEqual((len(self.http_calls), len(self.head_calls)), (4, 2))

    def test_unexpected_negative_exchange_success_never_reaches_resources(self):
        self.negative_success = True
        status, result = self.execute()
        self.assertEqual(status, 1)
        self.assertEqual(result["failure_stage"], "wrong_subject_exchange")
        self.assertEqual((len(self.http_calls), len(self.head_calls)), (3, 0))

    def test_only_subject_specific_negative_errors_count_as_rejection(self):
        for codes, code in (([70021], 400), ([700213], 401), ([700016], 400), ([700213, 700016], 400), ([700213], 403), ([], 400)):
            self.http_calls, self.head_calls = [], []
            self.negative_codes, self.negative_status = codes, code
            actual, _ = self.execute()
            self.assertEqual(actual, 0 if codes and set(codes) <= {70021, 700213} and code in (400, 401) else 1)
            if actual:
                self.assertEqual((len(self.http_calls), len(self.head_calls)), (3, 0))

    def test_token_claim_mismatches_fail_before_blob_heads(self):
        for claims in (self.arm, self.storage):
            for key in ("iss", "aud", "tid", "oid", "appid"):
                old = claims[key]
                claims[key] = "wrong"
                self.http_calls, self.head_calls = [], []
                self.assertEqual(self.execute()[0], 1)
                self.assertEqual(self.head_calls, [])
                claims[key] = old

    def test_github_subject_or_environment_mismatch_stops_before_exchange(self):
        for key in ("iss", "aud", "sub", "environment", "ref", "workflow_sha"):
            old = self.github[key]
            self.github[key] = "wrong"
            self.http_calls = []
            self.assertEqual(self.execute()[0], 1)
            self.assertEqual(len(self.http_calls), 1)
            self.github[key] = old

    def test_admin_access_or_non_rbac_error_does_not_pass(self):
        for status, code in ((200, None), (401, "AuthorizationPermissionMismatch"), (403, None), (403, "AuthorizationFailure")):
            self.http_calls, self.head_calls = [], []
            self.admin_status, self.admin_code = status, code
            self.assertEqual(self.execute()[0], 1)

    def test_failed_lab_head_stops_before_admin_head(self):
        self.lab_status = 404
        self.assertEqual(self.execute()[0], 1)
        self.assertEqual(len(self.head_calls), 1)

    def test_wrong_branch_host_or_identity_kind_has_no_http(self):
        for key, value in (("GITHUB_REF", "refs/heads/feature"), ("IDENTITY_KIND", "deploy"),
                           ("ACTIONS_ID_TOKEN_REQUEST_URL", "https://evil.example/" + fixtures.CANARY)):
            old = self.environment[key]
            self.environment[key] = value
            self.http_calls = []
            self.assertEqual(self.execute()[0], 1)
            self.assertEqual(self.http_calls, [])
            self.environment[key] = old

    def test_raw_http_error_does_not_print_body_url_or_tokens(self):
        self.raw_failure = urllib.error.HTTPError("https://example.invalid/" + fixtures.CANARY, 403, fixtures.CANARY,
                                                  {}, io.BytesIO(fixtures.CANARY.encode()))
        self.assertEqual(self.execute()[0], 1)

    def test_real_head_transport_never_reads_a_body(self):
        response = MagicMock(status=200)
        response.read.side_effect = AssertionError("State body must never be read")
        response.__enter__.return_value = response
        with patch("urllib.request.build_opener") as builder:
            builder.return_value.open.return_value = response
            self.assertEqual(MODULE["head_blob"]("syntheticstatelab", "lab-state", "lab.tfstate", fixtures.CANARY), (200, None))
            request = builder.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), "HEAD")
            self.assertEqual(request.full_url, "https://syntheticstatelab.blob.core.windows.net/lab-state/lab.tfstate")
            response.read.assert_not_called()
        body = io.BytesIO(fixtures.CANARY.encode())
        error = urllib.error.HTTPError("https://syntheticstatelab.blob.core.windows.net/admin-state/bootstrap-access.tfstate",
                                       403, fixtures.CANARY, {"x-ms-error-code": "AuthorizationPermissionMismatch"}, body)
        with patch("urllib.request.build_opener") as builder:
            builder.return_value.open.side_effect = error
            self.assertEqual(MODULE["head_blob"]("syntheticstatelab", "admin-state", "bootstrap-access.tfstate", fixtures.CANARY),
                             (403, "AuthorizationPermissionMismatch"))
            self.assertEqual(body.tell(), 0)

    def test_workflow_requires_two_protected_manual_jobs(self):
        workflow = yaml.load((ROOT / ".github/workflows/oidc-access.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["jobs"]), {"plan", "deploy"})
        for kind, job in workflow["jobs"].items():
            self.assertEqual(job["environment"], "lab-" + kind)
            self.assertEqual(job["env"]["IDENTITY_KIND"], kind)
            self.assertEqual(job["permissions"], {"contents": "read", "id-token": "write"})
            guards = {"github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'",
                      "github.event.repository.default_branch == 'main'", "inputs.reviewed_commit == github.sha",
                      "inputs.confirmation == 'READ_ONLY_IDENTITY_BOUNDARY_TESTS'"}
            self.assertEqual({term.strip() for term in job["if"].split("&&")}, guards)
            self.assertEqual(len(job["steps"]), 2)
            self.assertEqual(set(job["env"]), {"OIDC_ACCESS_CONTEXT", "IDENTITY_KIND", "REVIEWED_COMMIT", "ACCESS_CONFIRMATION"})
            checkout = job["steps"][0]
            self.assertRegex(checkout["uses"], r"^actions/checkout@[0-9a-f]{40}$")
            self.assertEqual(checkout["with"], {"ref": "${{ github.sha }}", "persist-credentials": "false"})
            self.assertEqual(job["steps"][1]["run"], "python3 .github/scripts/oidc-access.py")
        self.assertEqual(workflow["jobs"]["deploy"]["needs"], "plan")


if __name__ == "__main__":
    unittest.main()
