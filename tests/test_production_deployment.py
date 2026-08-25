import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_env_example() -> dict[str, str]:
    values = {}
    for raw_line in (ROOT / "deploy" / "production.env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


class ProductionDeploymentTests(unittest.TestCase):
    def test_production_environment_targets_leda_database(self):
        values = read_env_example()

        self.assertIn("@127.0.0.1:13306/chbzg", values["FACE_DEMO_STATE_DB_DSN"])
        self.assertIn("@127.0.0.1:13306/chbzg", values["FACE_DEMO_REGULATOR_DB_DSN"])
        self.assertEqual(
            values["FACE_DEMO_CORS_ORIGINS"],
            "https://chbzg.com,https://www.chbzg.com,https://faces.chbzg.com.cn",
        )

    def test_production_environment_matches_tested_behavior(self):
        values = read_env_example()

        expected = {
            "FACE_DEMO_VERIFICATION_FAILURE_MAX_ATTEMPTS": "3",
            "FACE_DEMO_VERIFICATION_FAILURE_COOLDOWN_SECONDS": "60",
            "FACE_DEMO_VERIFICATION_FAILURE_EXEMPT_SCENES": "doctor_audit",
            "FACE_DEMO_MIN_FRAMES_PER_ACTION": "8",
            "FACE_DEMO_SMILE_DELTA_THRESHOLD": "0.015",
            "FACE_DEMO_SHAKE_YAW_RANGE_THRESHOLD": "4.0",
            "FACE_DEMO_NOD_PITCH_RANGE_THRESHOLD": "3.0",
            "FACE_DEMO_HEAD_AXIS_CROSS_TOLERANCE_DEGREES": "16.0",
            "FACE_DEMO_HEAD_AXIS_CROSS_RANGE_RATIO": "1.20",
        }
        self.assertEqual({key: values[key] for key in expected}, expected)

    def test_production_files_do_not_reference_test_environment(self):
        paths = [
            ROOT / "deploy" / "production.env.example",
            ROOT / "deploy" / "face-verify.service",
            ROOT / "deploy" / "leda-face_verify.php.example",
            ROOT / "deploy" / "verify-production.sh",
        ]
        content = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        for forbidden in ("shualian", "newchbceshi", "ld_chbzg_com_cn", "9005", "13316"):
            self.assertNotIn(forbidden, content)
        self.assertIn("--port 8005", content)
        self.assertIn("/www/wwwroot/leda", content)

    def test_manual_schema_contains_required_state_tables_and_switch(self):
        schema = (ROOT / "deploy" / "production-schema.sql").read_text(encoding="utf-8")

        for table in (
            "fa_face_service_template",
            "fa_face_service_session",
            "fa_face_service_proof",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS `{table}`", schema)
        self.assertIn("COLUMN_NAME = 'face_verify_enabled'", schema)
        self.assertIn("ADD COLUMN `face_verify_enabled`", schema)


if __name__ == "__main__":
    unittest.main()
