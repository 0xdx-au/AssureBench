import json
import hashlib
import io
import sys
import stat
import threading
import unittest
import zipfile
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import secassure


class FindingParserTests(unittest.TestCase):
    def test_secassure_defaults_to_scanning_current_directory(self):
        with patch.object(sys, "argv", ["secassure.py"]), patch.object(
            secassure.server, "run_cli_scan", return_value=0
        ) as scan:
            self.assertEqual(secassure.main(), 0)
        scan.assert_called_once_with(Path("."), None, False)

    def test_secassure_can_start_the_dashboard(self):
        with patch.object(
            sys, "argv", ["secassure.py", "--dashboard"]
        ), patch.object(secassure.server, "run_dashboard", return_value=0) as dashboard:
            self.assertEqual(secassure.main(), 0)
        dashboard.assert_called_once_with()

    def test_secassure_container_cli_enables_private_work_volume(self):
        with patch.object(
            sys, "argv", ["secassure.py", "--container", "/input"]
        ), patch.object(secassure.server, "enable_container_runtime") as enable, patch.object(
            secassure.server, "run_cli_scan", return_value=0
        ) as scan:
            self.assertEqual(secassure.main(), 0)
        enable.assert_called_once_with()
        scan.assert_called_once_with(Path("/input"), None, False)

    def test_assurebench_logo_assets_are_served_by_the_local_dashboard(self):
        for path, (asset, content_type) in server.ASSETS.items():
            if path.startswith("/assets/brand/"):
                self.assertTrue((server.APP / asset).is_file())
                self.assertEqual(content_type, "image/svg+xml")
        dashboard = (server.APP / "index.html").read_text(encoding="utf-8")
        self.assertIn("/assets/brand/assurebench-horizontal-dark.svg", dashboard)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.RequestHandler)
        port = httpd.server_address[1]
        host = "127.0.0.1:{}".format(port)
        with patch.object(server, "ALLOWED_HOSTS", {host}):
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request(
                    "GET",
                    "/assets/brand/assurebench-horizontal-dark.svg",
                    headers={"Host": host},
                )
                response = connection.getresponse()
                content = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "image/svg+xml")
                self.assertIn("<title id=\"title\">AssureBench</title>", content)
                connection.close()
            finally:
                httpd.shutdown()
                thread.join(timeout=5)
                httpd.server_close()

    def test_local_project_preparation_excludes_generated_dirs_and_rejects_symlinks(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            (project / "app.py").write_text("print('source')", encoding="utf-8")
            (project / "node_modules").mkdir()
            (project / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
            (project / ".git").mkdir()
            (project / ".git" / "config").write_text("ignored", encoding="utf-8")
            workspace = base / "workspace"
            target = server.prepare_local_project(project, workspace)
            self.assertEqual(
                sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()),
                ["app.py"],
            )
            self.assertEqual((target / "app.py").read_text(encoding="utf-8"), "print('source')")

            linked_project = base / "linked-project"
            linked_project.mkdir()
            (linked_project / "source.py").symlink_to(project / "app.py")
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                server.prepare_local_project(linked_project, base / "linked-workspace")

    def test_cli_outputs_only_markdown_to_stdout(self):
        with TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            (project / "README.md").write_text("# sample", encoding="utf-8")
            report = "# AssureBench report\n\n## Summary\n"
            snapshot = {
                "id": "cli-test-run",
                "status": "completed",
                "report": report,
                "stages": [
                    {"id": stage_id, "title": title, "status": "completed", "detail": "ok"}
                    for stage_id, title, _ in server.STAGES
                ],
                "logs": [],
            }
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(
                server.MANAGER, "register_upload", return_value={"upload_id": "upload"}
            ) as register, patch.object(
                server.MANAGER, "start", return_value={"id": "cli-test-run"}
            ), patch.object(
                server.MANAGER, "snapshot", return_value=snapshot
            ), patch.object(
                server.sys, "stdout", stdout
            ), patch.object(
                server.sys, "stderr", stderr
            ):
                self.assertEqual(server.run_cli_scan(project), 0)
            self.assertEqual(stdout.getvalue(), report)
            self.assertIn("Scanning", stderr.getvalue())
            registered_workspace, registered_target, archive_name = register.call_args.args
            self.assertEqual(archive_name, "project.zip")
            self.assertEqual(register.call_args.kwargs["source_type"], "local directory")
            self.assertTrue(registered_target.is_dir())
            self.assertTrue(registered_target.is_relative_to(registered_workspace))
            server.shutil.rmtree(registered_workspace, ignore_errors=True)

    def test_cli_output_path_receives_markdown_only(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            (project / "README.md").write_text("# sample", encoding="utf-8")
            output = base / "assessment.md"
            report = "# AssureBench report\n"
            snapshot = {
                "id": "cli-output-run",
                "status": "completed",
                "report": report,
                "stages": [],
                "logs": [],
            }
            stderr = io.StringIO()
            with patch.object(
                server.MANAGER, "register_upload", return_value={"upload_id": "upload"}
            ), patch.object(
                server.MANAGER, "start", return_value={"id": "cli-output-run"}
            ), patch.object(
                server.MANAGER, "snapshot", return_value=snapshot
            ), patch.object(
                server.sys, "stdout", io.StringIO()
            ), patch.object(
                server.sys, "stderr", stderr
            ):
                self.assertEqual(server.run_cli_scan(project, output), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), report)
            self.assertIn("Markdown report saved", stderr.getvalue())

    def test_cli_emits_markdown_report_when_docker_preflight_fails(self):
        with TemporaryDirectory() as temporary:
            project = Path(temporary) / "local-project"
            project.mkdir()
            (project / "README.md").write_text("# Sample", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(server.shutil, "which", return_value=None), patch.object(
                server.sys, "stdout", stdout
            ), patch.object(server.sys, "stderr", stderr):
                exit_code = server.run_cli_scan(project)
            report = stdout.getvalue()
            self.assertEqual(exit_code, 1)
            self.assertTrue(report.startswith("# AssureBench DevSecOps Security Assessment"))
            self.assertIn("- **Target:** Local directory `local-project`", report)
            self.assertIn("## Scan stage execution record", report)
            self.assertIn("Docker CLI was not found on PATH.", report)
            self.assertIn("Scan failed", stderr.getvalue())

    def test_trivy_secret_value_is_never_returned(self):
        secret_value = "sensitive-example-value"
        findings = server.extract_trivy({
            "Results": [{
                "Target": "src/config.ts",
                "Secrets": [{
                    "RuleID": "generic-api-key",
                    "Severity": "HIGH",
                    "StartLine": 12,
                    "Match": secret_value,
                }],
            }],
        })
        self.assertEqual(len(findings), 1)
        self.assertIn("redacted", findings[0]["title"])
        self.assertNotIn(secret_value, json.dumps(findings))

    def test_finding_paths_are_relative_and_sanitized(self):
        findings = server.extract_checkov({
            "results": {
                "failed_checks": [{
                    "check_id": "CKV_AWS_1",
                    "check_name": "Example",
                    "file_path": "/workspace/infra/template.yml",
                    "file_line_range": [10, 15],
                }],
            },
        })
        self.assertEqual(findings[0]["file"], "infra/template.yml")
        self.assertEqual(findings[0]["line"], "10")

    def test_severity_counts_are_normalized(self):
        counts = server.summarize_findings([
            {"severity": "critical"},
            {"severity": "MEDIUM"},
            {"severity": "UNEXPECTED"},
        ])
        self.assertEqual(counts["CRITICAL"], 1)
        self.assertEqual(counts["MEDIUM"], 1)
        self.assertEqual(counts["UNKNOWN"], 1)

    def test_trivy_cve_preserves_affected_package_and_source_paths(self):
        findings = server.extract_trivy({
            "Results": [{
                "Target": "pnpm-lock.yaml",
                "Vulnerabilities": [{
                    "VulnerabilityID": "CVE-2026-12345",
                    "Severity": "CRITICAL",
                    "PkgName": "example-package",
                    "InstalledVersion": "1.2.3",
                    "FixedVersion": "1.2.4",
                    "PkgPath": "node_modules/example-package/package.json",
                    "PkgIdentifier": {"PURL": "pkg:npm/example-package@1.2.3"},
                    "PrimaryURL": "https://nvd.nist.gov/vuln/detail/CVE-2026-12345",
                }],
            }],
        })
        self.assertEqual(findings[0]["id"], "CVE-2026-12345")
        self.assertEqual(findings[0]["package_name"], "example-package")
        self.assertEqual(findings[0]["package_version"], "1.2.3")
        self.assertEqual(findings[0]["package_file"], "pnpm-lock.yaml")
        self.assertEqual(
            findings[0]["package_path"],
            "node_modules/example-package/package.json",
        )
        self.assertEqual(findings[0]["purl"], "pkg:npm/example-package@1.2.3")

    def test_dependency_graph_uses_sbom_bom_refs_and_relationships(self):
        graph = server.extract_dependency_graph({
            "metadata": {
                "component": {
                    "type": "application",
                    "bom-ref": "pkg:npm/app@1.0.0",
                    "name": "app",
                    "version": "1.0.0",
                },
            },
            "components": [{
                "type": "library",
                "bom-ref": "pkg:npm/react@19.0.0",
                "name": "react",
                "version": "19.0.0",
            }],
            "dependencies": [{
                "ref": "pkg:npm/app@1.0.0",
                "dependsOn": ["pkg:npm/react@19.0.0"],
            }],
        })
        self.assertEqual(graph["roots"], ["pkg:npm/app@1.0.0"])
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(graph["edges"], [{
            "from": "pkg:npm/app@1.0.0",
            "to": "pkg:npm/react@19.0.0",
        }])
        self.assertIn("app@1.0.0 -> react@19.0.0", server.render_dependency_graph(graph))

    def test_sbom_package_files_are_nested_under_matching_cve_package(self):
        findings = server.extract_trivy({
            "Results": [{
                "Target": "package-lock.json",
                "Vulnerabilities": [{
                    "VulnerabilityID": "GHSA-EXAMPLE",
                    "Severity": "HIGH",
                    "PkgName": "example-package",
                    "InstalledVersion": "1.2.3",
                    "PkgPath": "node_modules/example-package/package.json",
                    "Title": "Example package vulnerability",
                }],
            }],
        })
        graph = server.extract_dependency_graph({
            "components": [{
                "type": "library",
                "bom-ref": "pkg:npm/example-package@1.2.3",
                "name": "example-package",
                "version": "1.2.3",
                "purl": "pkg:npm/example-package@1.2.3",
                "properties": [{
                    "name": "syft:location:0:path",
                    "value": "node_modules/example-package/index.js",
                }],
            }],
            "dependencies": [],
        })
        inventory = server.package_vulnerability_inventory(findings, graph)
        self.assertEqual(inventory[0]["name"], "example-package")
        self.assertEqual(inventory[0]["cves"][0]["id"], "GHSA-EXAMPLE")
        self.assertEqual(inventory[0]["package_files"], ["package-lock.json"])
        self.assertEqual(
            inventory[0]["package_locations"],
            [
                "node_modules/example-package/index.js",
                "node_modules/example-package/package.json",
            ],
        )
        self.assertEqual(
            inventory[0]["cves"][0]["affected_files"],
            [],
        )

    def test_interrupted_scan_marks_every_unstarted_stage_with_reason(self):
        stages = [
            {"id": "preflight", "title": "Preflight", "status": "completed", "detail": "Engine ready"},
            {"id": "images", "title": "Images", "status": "running", "detail": "Pulling image"},
            {"id": "sast", "title": "SAST", "status": "queued", "detail": "Waiting"},
        ]
        server.mark_interrupted_stages(stages, "registry unavailable")
        self.assertEqual(stages[1]["status"], "failed")
        self.assertIn("registry unavailable", stages[1]["detail"])
        self.assertEqual(stages[2]["status"], "skipped")
        self.assertIn("Images", stages[2]["detail"])
        self.assertIn("registry unavailable", stages[2]["detail"])

    def test_report_contains_frameworks_scope_and_signature(self):
        scan_id = "f5e01498-229c-42a8-8ccc-32f8a4536188"
        run = {
            "id": scan_id,
            "version": 2,
            "status": "completed-with-warnings",
            "mode": "rerun",
            "started_at": "now",
            "completed_at": "later",
            "report_generated_at": "2026-10-22T11:47:00Z",
            "findings": [{
                "kind": "Dependency",
                "severity": "CRITICAL",
                "id": "CVE-EXAMPLE",
                "file": "pnpm-lock.yaml",
                "line": "",
                "title": "sample package issue",
                "fixed": "2.0",
            }],
            "dependency_graph": server.extract_dependency_graph({
                "metadata": {"component": {
                    "type": "application",
                    "bom-ref": "pkg:npm/app@1.0.0",
                    "name": "app",
                    "version": "1.0.0",
                }},
                "components": [],
                "dependencies": [{"ref": "pkg:npm/app@1.0.0", "dependsOn": []}],
            }),
            "stages": [{
                "id": "preflight",
                "title": "Archive preflight",
                "status": "completed",
                "detail": "Input validated",
            }],
        }
        report = server.build_report(run)
        for expected in (
            "# AssureBench DevSecOps Security Assessment",
            "AssureBench performs an automated repository-based security assessment",
            "Scan UUID:** `{}`".format(scan_id),
            "Started (UTC)",
            "Completed (UTC)",
            "Report generated (UTC):** 2026-10-22T11:47:00Z",
            "Overall status:** completed-with-warnings",
            "Dependency graph",
            "ROOT app@1.0.0",
            "Scan architecture",
            "| completed | Input validated |",
            "Browser (127.0.0.1)",
            "private temporary extraction",
            "uploaded project commands are never executed",
            "UUID-bound report signature",
            "SHA-256 over `scan UUID + newline + report content before this section`",
            "OWASP Top 10:2025",
            "NIST CSF 2.0",
            "NIST SP 800-218 SSDF",
            "OWASP SAMM 2.0",
            "dynamic application testing",
            "Scan stage execution record",
            "Every configured step is listed below",
            "01 | ARCHIVE PREFLIGHT",
            "No execution result was recorded for this stage.",
            "Vulnerable packages and CVE/advisory file tracking",
            "Detected in:",
            "Affected source/call-site files: not identified by this dependency scan.",
            "## References",
            "https://nvd.nist.gov/vuln/detail/CVE-EXAMPLE",
            "CRITICAL",
            "CVE-EXAMPLE",
            "1 matching finding(s); scan evidence: SCA, SBOM, workflow integrity.",
            "Scope and interpretation",
        ):
            self.assertIn(expected, report)
        unsigned_report = report.split("\n## UUID-bound report signature", 1)[0].rstrip("\n")
        expected_signature = hashlib.sha256(
            (scan_id + "\n" + unsigned_report).encode("utf-8")
        ).hexdigest()
        self.assertEqual(run["signature"], "sha256:" + expected_signature)
        self.assertIn("`{}`".format(run["signature"]), report)

    def test_report_assigns_utc_generation_time_and_uuid_signature(self):
        run = {
            "id": "f5e01498-229c-42a8-8ccc-32f8a4536188",
            "version": 1,
            "started_at": "2026-10-22T11:00:00Z",
            "completed_at": "2026-10-22T11:01:00Z",
            "source_type": "local directory",
            "project_name": "sample-project",
            "findings": [],
            "stages": [],
        }
        report = server.build_report(run)
        self.assertIn("- **Target:** Local directory `sample-project`", report)
        self.assertRegex(run["report_generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        unsigned_report = report.split("\n## UUID-bound report signature", 1)[0].rstrip("\n")
        expected_signature = hashlib.sha256(
            (run["id"] + "\n" + unsigned_report).encode("utf-8")
        ).hexdigest()
        self.assertEqual(run["signature"], "sha256:" + expected_signature)

    def test_scanner_root_does_not_escape_its_standalone_repository(self):
        self.assertEqual(server.ROOT, server.APP)
        topology = server.build_application_topology()
        self.assertEqual(topology["routes"], [])
        self.assertTrue(all(item["evidence"] for item in topology["interfaces"]))
        self.assertNotIn("Power BI", json.dumps(topology))
        self.assertNotIn(server.APP.parent.name, json.dumps(topology))

    def test_report_documents_application_topology_and_database_evidence_boundary(self):
        run = {
            "id": "f5e01498-229c-42a8-8ccc-32f8a4536188",
            "version": 1,
            "started_at": "2026-10-22T11:00:00Z",
            "completed_at": "2026-10-22T11:01:00Z",
            "findings": [],
            "stages": [],
        }
        report = server.build_report(run)
        self.assertIn("Application topology and data mapping", report)
        self.assertIn("Trust zones", report)
        self.assertIn("End-to-end application flow", report)
        self.assertIn("Interfaces", report)
        self.assertIn("Mappings above are inferred from files in the uploaded archive", report)
        self.assertIn("do not establish deployed database schemas or runtime connectivity", report)
        self.assertNotIn("Member.member_name", report)
        self.assertNotIn("Actual API hostnames", report)

    def test_uploaded_project_analysis_builds_mermaid_architecture(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"react": "19.0.0", "pg": "8.0.0"}}),
                encoding="utf-8",
            )
            (root / "src").mkdir()
            (root / "src" / "App.tsx").write_text(
                'export default function App(){ return fetch("/api/items"); }',
                encoding="utf-8",
            )
            (root / "api").mkdir()
            (root / "api" / "server.py").write_text(
                "from fastapi import FastAPI\\nimport psycopg",
                encoding="utf-8",
            )
            (root / "Dockerfile").write_text("FROM python:3.12", encoding="utf-8")
            topology = server.analyze_project_topology(root, "sample-app")

        self.assertIn("flowchart TD", topology["mermaid"])
        self.assertIn("Frontend / web client", [item["label"] for item in topology["components"]])
        self.assertIn("Backend / API service", [item["label"] for item in topology["components"]])
        self.assertIn("PostgreSQL", topology["databases"])
        self.assertTrue(topology["infrastructure"])
        self.assertIn("IF-01", [item["id"] for item in topology["interfaces"]])
        self.assertIn("src/App.tsx", next(
            component["source_files"]
            for component in topology["components"]
            if component["id"] == "ui"
        ))
        marker_map = server.topology_finding_map([
            {"kind": "SAST", "id": "RULE-1", "file": "src/App.tsx"},
            {"kind": "Dependency", "id": "CVE-1", "file": "pnpm-lock.yaml"},
        ], topology)
        self.assertEqual(
            {item["component"]: item["count"] for item in marker_map},
            {"Frontend / web client": 1, "Package ecosystems": 1},
        )

    def test_uploaded_architecture_uses_explicit_evidence_and_separates_systems(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "package.json").write_text(json.dumps({
                "dependencies": {
                    "next": "16.3.8",
                    "react": "19.0.0",
                    "powerbi-client-react": "2.0.2",
                },
            }), encoding="utf-8")
            (root / "README.md").write_text(
                "Examples: Vue, Vite, PostgreSQL, Redis, and FastAPI.",
                encoding="utf-8",
            )
            (root / "src" / "app").mkdir(parents=True)
            (root / "src" / "app" / "page.tsx").write_text(
                'export default () => fetch(process.env.API_URL);',
                encoding="utf-8",
            )
            (root / "src" / "lib").mkdir(parents=True)
            (root / "src" / "lib" / "report.tsx").write_text(
                "export const embed = PowerBIReportEmbed;",
                encoding="utf-8",
            )
            (root / "infra").mkdir()
            (root / "infra" / "cfn-template.yaml").write_text(
                "Resources:\n"
                "  AppBucket:\n"
                "    Type: AWS::S3::Bucket\n"
                "  AppDistribution:\n"
                "    Type: AWS::CloudFront::Distribution\n"
                "    Properties:\n"
                "      Origin: !GetAtt AppBucket.RegionalDomainName\n"
                "Outputs:\n"
                "  Url:\n"
                "    Value: example\n",
                encoding="utf-8",
            )
            topology = server.analyze_project_topology(root, "sample-app")

        labels = [item["label"] for item in topology["components"]]
        self.assertIn("Next.js, React", next(
            item["evidence"] for item in topology["components"] if item["id"] == "ui"
        ))
        self.assertFalse(any("Vue" in label or "Vite" in label for label in labels))
        self.assertNotIn("FastAPI", labels)
        self.assertFalse(topology["databases"])
        self.assertIn("API_URL", next(
            item["evidence"] for item in topology["components"] if item["id"] == "apis"
        ))
        self.assertIn("Microsoft Power BI", labels)
        self.assertTrue(any("AWS S3 bucket" in label for label in labels))
        self.assertTrue(any("AWS CloudFront distribution" in label for label in labels))
        self.assertTrue(any("declared resource reference" == edge["label"] for edge in topology["edges"]))
        self.assertTrue(any("CloudFront" in interface["to"] for interface in topology["interfaces"]))

    def test_stride_assessments_and_top_threat_scenarios_are_evidence_qualified(self):
        findings = [
            {
                "kind": "Dependency",
                "severity": "CRITICAL",
                "id": "GHSA-EXAMPLE",
                "file": "pnpm-lock.yaml",
                "title": "next 16.3.8 Next.js: Unauthenticated Remote Code Execution in Image Optimization API when SVG files are used",
                "fixed": "16.4.1",
            },
            {
                "kind": "Dependency",
                "severity": "CRITICAL",
                "id": "GHSA-CACHE",
                "file": "pnpm-lock.yaml",
                "title": "next 16.3.8 Remote Code Execution in `use cache` functions returning typed arrays",
                "fixed": "16.4.1",
            },
            {
                "kind": "Dependency",
                "severity": "CRITICAL",
                "id": "CVE-SEROVAL",
                "file": "pnpm-lock.yaml",
                "title": "seroval 1.5.6 `fromJSON()` Promise thenable assimilation invokes plugin-produced callables",
                "fixed": "1.6.2",
            },
        ]
        model = server.build_threat_model(findings, {
            "interfaces": [{"from": "Browser", "to": "API"}],
        })
        report = server.build_report({
            "id": "f5e01498-229c-42a8-8ccc-32f8a4536188",
            "version": 1,
            "started_at": "now",
            "completed_at": "later",
            "findings": findings,
            "application_topology": {"interfaces": [{"from": "Browser", "to": "API"}]},
            "stages": [],
        })

        self.assertEqual(len(model["stride"]), 6)
        self.assertEqual(len(model["scenarios"]), 3)
        self.assertEqual(model["scenarios"][0]["finding"]["id"], "GHSA-EXAMPLE")
        self.assertIn("static export", model["scenarios"][0]["preconditions"])
        self.assertEqual(model["scenarios"][0]["mitre"][0]["id"], "T1190")
        self.assertEqual(model["scenarios"][2]["mitre"][0]["id"], "T1190")
        self.assertIn("Browser → API", model["stride"][0]["boundaries"])
        self.assertIn("Detailed finding assessments", report)
        self.assertIn("Threat model (STRIDE)", report)
        self.assertIn("Top three threat scenarios", report)
        self.assertIn("ATT&CK IDs describe candidate adversary behavior", report)
        self.assertIn("Browser → API", report)
        self.assertIn("pnpm-lock.yaml:line not reported", report)
        self.assertIn("16.4.1", report)

    def test_archive_extraction_rejects_traversal_and_symlinks(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            traversal = base / "traversal.zip"
            with zipfile.ZipFile(traversal, "w") as archive:
                archive.writestr("../escape.txt", "no")
            with self.assertRaisesRegex(ValueError, "escapes"):
                server.extract_repository_archive(traversal, base / "out")

            symlink = base / "symlink.zip"
            info = zipfile.ZipInfo("repo/link")
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(symlink, "w") as archive:
                archive.writestr(info, "../target")
            with self.assertRaisesRegex(ValueError, "link"):
                server.extract_repository_archive(symlink, base / "out-link")

    def test_extracted_scanner_workspace_is_group_readable_but_not_group_writable(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive_path = base / "source.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("repo/src/app.py", "print('safe')")
            root = server.extract_repository_archive(archive_path, base / "source")
            directory_mode = stat.S_IMODE(root.stat().st_mode)
            file_mode = stat.S_IMODE((root / "src" / "app.py").stat().st_mode)

        self.assertEqual(directory_mode, 0o750)
        self.assertEqual(file_mode, 0o640)

    def test_upload_endpoint_accepts_safe_github_zip_and_rejects_invalid_archive(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.RequestHandler)
        port = httpd.server_address[1]
        origin = "http://127.0.0.1:{}".format(port)
        host = "127.0.0.1:{}".format(port)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        uploaded_dir = None
        with TemporaryDirectory() as temporary:
            zip_path = Path(temporary) / "owner-repo-main.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("owner-repo-main/package.json", '{"dependencies":{"react":"19"}}')
                archive.writestr("owner-repo-main/src/App.jsx", 'export default () => fetch("/api");')
            zip_bytes = zip_path.read_bytes()
            with patch.object(server, "ALLOWED_HOSTS", {host}):
                thread.start()
                try:
                    conn = HTTPConnection("127.0.0.1", port, timeout=5)
                    conn.request("GET", "/api/bootstrap", headers={"Host": host})
                    response = conn.getresponse()
                    bootstrap = json.loads(response.read())
                    headers = {
                        "Host": host,
                        "Origin": origin,
                        "Content-Type": "application/zip",
                        "Content-Length": str(len(zip_bytes)),
                        "X-Scan-Token": bootstrap["csrfToken"],
                        "X-Archive-Name": "owner-repo-main.zip",
                    }
                    conn.request("POST", "/api/uploads", body=zip_bytes, headers=headers)
                    response = conn.getresponse()
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, 201)
                    self.assertEqual(payload["archive_name"], "owner-repo-main.zip")
                    self.assertIn("flowchart TD", payload["mermaid"])
                    with server.MANAGER.lock:
                        uploaded = server.MANAGER.uploads.pop(payload["upload_id"])
                        uploaded_dir = uploaded["upload_dir"]

                    headers["Content-Length"] = "22"
                    conn.request("POST", "/api/uploads", body=b"not a zip archive payload", headers=headers)
                    response = conn.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read()
                    conn.close()
                finally:
                    httpd.shutdown()
                    thread.join(timeout=5)
                    httpd.server_close()
        if uploaded_dir:
            server.shutil.rmtree(uploaded_dir, ignore_errors=True)


class ContainerSecurityTests(unittest.TestCase):
    def test_new_scan_link_opens_a_clean_run_in_a_separate_tab(self):
        page = (server.APP / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="new-scan-link"', page)
        self.assertIn('href="/" target="_blank" rel="noopener noreferrer"', page)

    def test_scanner_caches_are_group_writable_after_umask(self):
        with TemporaryDirectory() as temporary:
            reports = Path(temporary) / "reports"
            reports.mkdir(mode=0o770)
            cache = server._prepare_scanner_cache(reports, "trivy")
            self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o770)

    def test_container_image_drops_privileges_and_defines_healthcheck(self):
        dockerfile = (server.APP / "Dockerfile").read_text(encoding="utf-8")
        entrypoint = (server.APP / "docker-entrypoint.py").read_text(encoding="utf-8")
        self.assertIn("USER 10001:0", dockerfile)
        self.assertIn("os.setuid(10001)", entrypoint)
        self.assertIn("os.setgroups(sorted({0, socket_gid}))", entrypoint)
        self.assertIn("HEALTHCHECK", dockerfile)

    def test_compose_limits_root_volume_initializer_and_privilege_drop(self):
        compose = (server.APP / "compose.yaml").read_text(encoding="utf-8")
        init = compose.split("  assurebench:\n", 1)[0]
        app = compose.split("  assurebench:\n", 1)[1]
        self.assertIn('user: "0:0"', init)
        self.assertIn("entrypoint: []", init)
        self.assertIn('user: "0:0"', app)
        self.assertIn("network_mode: none", init)
        self.assertIn("- CHOWN", init)
        self.assertNotIn("docker.sock", init)
        self.assertIn("      - SETGID", app)
        self.assertIn("      - SETUID", app)
        self.assertIn("condition: service_completed_successfully", app)
        self.assertIn("healthcheck:", app)
        self.assertIn('"127.0.0.1::8765"', app)
        launcher = (server.APP / "start-compose.sh").read_text(encoding="utf-8")
        self.assertIn("docker compose port assurebench 8765", launcher)

    def test_images_are_pinned_and_runner_never_mounts_docker_socket(self):
        for image in server.IMAGES.values():
            self.assertRegex(image, r"@sha256:[0-9a-f]{64}$")
        workspace_mount = server.ScanManager._workspace_mount(Path("/tmp/uploaded-source"))
        report_mount = server.ScanManager._report_mount(Path("/tmp/scan-reports"))
        args = server.ScanManager()._docker_args(
            "docker", None, server.IMAGES["Semgrep"], [workspace_mount, report_mount], "run-id"
        )
        self.assertTrue(all(isinstance(argument, str) for argument in args))
        self.assertIn("/tmp/uploaded-source:/workspace:ro", args)
        self.assertIn("/tmp/scan-reports:/reports:rw", args)
        self.assertIn("--read-only", args)
        self.assertIn("--cap-drop=ALL", args)
        self.assertIn("--security-opt=no-new-privileges", args)
        self.assertIn("--network=bridge", args)
        self.assertIn("GRYPE_DB_CACHE_DIR=/reports/cache/grype", args)
        self.assertFalse(any("docker.sock" in str(item) for item in args))

    def test_scan_mount_uses_selected_uploaded_source(self):
        root = Path("/tmp/untrusted-upload/source/project")
        self.assertEqual(server.ScanManager._workspace_mount(root), ["-v", "{}:/workspace:ro".format(root)])
        self.assertEqual(server._safe_relpath("../../secret.txt"), "_/_/secret.txt")

    def test_container_cli_scanners_use_only_private_volume_subpaths(self):
        root = Path("/var/lib/assurebench/cli/input/project")
        reports = Path("/var/lib/assurebench/cli/reports")
        with patch.object(server, "TEMP_ROOT", Path("/var/lib/assurebench")), patch.object(
            server, "DOCKER_WORK_VOLUME", "assurebench-work"
        ):
            self.assertEqual(
                server.ScanManager._workspace_mount(root),
                ["--mount", "type=volume,source=assurebench-work,target=/workspace,volume-subpath=cli/input/project,readonly"],
            )
            self.assertEqual(
                server.ScanManager._report_mount(reports),
                ["--mount", "type=volume,source=assurebench-work,target=/reports,volume-subpath=cli/reports"],
            )


class LocalHTTPGuardTests(unittest.TestCase):
    def test_requires_origin_token_and_rejects_unrecognized_run_requests(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.RequestHandler)
        port = httpd.server_address[1]
        origin = "http://127.0.0.1:{}".format(port)
        host = "127.0.0.1:{}".format(port)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        with patch.object(server, "ALLOWED_HOSTS", {host}):
            thread.start()
            try:
                conn = HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", "/api/bootstrap", headers={"Host": host})
                response = conn.getresponse()
                bootstrap = json.loads(response.read())
                self.assertEqual(response.status, 200)

                conn.request(
                    "POST", "/api/runs", body=json.dumps({"target": "/"}),
                    headers={
                        "Host": host,
                        "Origin": origin,
                        "Content-Type": "application/json",
                        "X-Scan-Token": bootstrap["csrfToken"],
                    },
                )
                response = conn.getresponse()
                response.read()
                self.assertEqual(response.status, 400)

                dynamic_host = "127.0.0.1:{}".format(port + 1)
                conn.request(
                    "POST", "/api/runs", body=json.dumps({"target": "/"}),
                    headers={
                        "Host": dynamic_host,
                        "Origin": "http://{}".format(dynamic_host),
                        "Content-Type": "application/json",
                        "X-Scan-Token": bootstrap["csrfToken"],
                    },
                )
                response = conn.getresponse()
                response.read()
                self.assertEqual(response.status, 400)

                conn.request(
                    "POST", "/api/runs", body="{}",
                    headers={
                        "Host": host,
                        "Origin": "https://attacker.example",
                        "Content-Type": "application/json",
                        "X-Scan-Token": bootstrap["csrfToken"],
                    },
                )
                response = conn.getresponse()
                response.read()
                self.assertEqual(response.status, 403)

                conn.request(
                    "POST", "/api/runs", body="{}",
                    headers={
                        "Host": host,
                        "Origin": origin,
                        "Content-Type": "application/json",
                    },
                )
                response = conn.getresponse()
                response.read()
                self.assertEqual(response.status, 403)

                conn.close()
            finally:
                httpd.shutdown()
                thread.join(timeout=5)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
