import unittest
from unittest.mock import mock_open, patch
from ..util.log_config import setup_logging
from ..parsers.er_parser import er_parser
from ..util.evaluator import evaluate, eval_ER

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

logger = setup_logging("test_er_parser_evaluator")

SOLUTION = {
    "tables": {
        "doctor": (),
        "Patient": (),
        "Medicine": ()
    },
    "relations": {
        "prescribes": {
            "tables": (["doctor", 1, "n"], ["Patient", 1, "n"]),
            "attr": (["Medicine", 0, "n"])
        }
    },
    "punkte": {"tables": 50, "relations": 50}
}

TEST_DIR = "src/er_parser/test_cases"


class TestERParserEvaluator(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        logger.info("Setting up test case")
        self.test_dir = TEST_DIR

    def test_completely_correct_submission(self):
        submission = self.test_dir + "/test_case1/test1_correct.txt"
        mock_file = mock_open(read_data=submission)
        with patch("builtins.open", mock_file):
            logger.info("Parsing completely correct submission")
            parsed = er_parser.parse_file_ER("mock_path", "correct_submission.txt")
            logger.info(f"Parsed data: {parsed}")
            result = eval_ER(parsed, SOLUTION)
            logger.info(f"Evaluation result: {result}")
            self.assertEqual(parsed["tables"], SOLUTION["tables"])
            self.assertEqual(parsed["relations"], SOLUTION["relations"])
            total_points = result.get("Gesamtpunktzahl", 0)
            max_points = result.get("Erreichbare_punktzahl", 0)
            logger.info(f"Total points: {total_points}, Max points: {max_points}")
            self.assertEqual(total_points, max_points)
            self.assertEqual(total_points, 100)

    def test_correct_with_wrong_parts(self):
        submission = self.test_dir + "/test_case1/test1_correct_ok.txt"
        mock_file = mock_open(read_data=submission)
        with patch("builtins.open", mock_file):
            logger.info("Parsing submission with wrong parts")
            parsed = er_parser.parse_file_ER("mock_path", "wrong_parts.txt")
            logger.info(f"Parsed data: {parsed}")
            result = eval_ER(parsed, SOLUTION)
            logger.info(f"Evaluation result: {result}")
            self.assertIn("doctor", parsed["tables"])
            self.assertIn("Patient", parsed["tables"])
            self.assertIn("prescribes", parsed["relations"])
            self.assertNotEqual(parsed["tables"], SOLUTION["tables"])
            self.assertNotIn("Medicine", parsed["tables"])
            total_points = result.get("Gesamtpunktzahl", 0)
            logger.info(f"Total points: {total_points}")
            self.assertTrue(60 <= total_points <= 70, f"Expected 60-70, got {total_points}")

    def test_wrong_format(self):
        submission = self.test_dir + "/test_case1/test1_wrong_format.txt"
        mock_file = mock_open(read_data=submission)
        with patch("builtins.open", mock_file):
            logger.info("Parsing wrong format submission")
            try:
                parsed = er_parser.parse_file_ER("mock_path", "wrong_format.txt")
                logger.info(f"Parsed data: {parsed}")
            except Exception as e:
                logger.info(f"Parsing failed as expected: {str(e)}")
                parsed = {}
            result = eval_ER(parsed, SOLUTION)
            logger.info(f"Evaluation result: {result}")
            self.assertTrue(len(parsed) == 0 or "tables" not in parsed or "relations" not in parsed)
            total_points = result.get("Gesamtpunktzahl", 0)
            logger.info(f"Total points: {total_points}")
            self.assertTrue(total_points <= 10, f"Expected <=10, got {total_points}")

    def test_completely_false(self):
        submission = self.test_dir + "/test_case1/test1_false.txt"
        mock_file = mock_open(read_data=submission)
        with patch("builtins.open", mock_file):
            logger.info("Parsing completely false submission")
            parsed = er_parser.parse_file_ER("mock_path", "false_submission.txt")
            logger.info(f"Parsed data: {parsed}")
            result = eval_ER(parsed, SOLUTION)
            logger.info(f"Evaluation result: {result}")
            self.assertNotEqual(parsed["tables"], SOLUTION["tables"])
            self.assertNotEqual(parsed["relations"], SOLUTION["relations"])
            total_points = result.get("Gesamtpunktzahl", 0)
            logger.info(f"Total points: {total_points}")
            self.assertEqual(total_points, 0)

    def test_wrong_names(self):
        submission = self.test_dir + "/test_case1/test1_correct_false_names.txt"
        mock_file = mock_open(read_data=submission)
        with patch("builtins.open", mock_file):
            logger.info("Parsing submission with wrong names")
            parsed = er_parser.parse_file_ER("mock_path", "wrong_names.txt")
            logger.info(f"Parsed data: {parsed}")
            result = eval_ER(parsed, SOLUTION)
            logger.info(f"Evaluation result: {result}")
            self.assertEqual(len(parsed["tables"]), len(SOLUTION["tables"]))
            self.assertEqual(len(parsed["relations"]), len(SOLUTION["relations"]))
            self.assertNotEqual(parsed["tables"], SOLUTION["tables"])
            self.assertNotEqual(parsed["relations"], SOLUTION["relations"])
            total_points = result.get("Gesamtpunktzahl", 0)
            logger.info(f"Total points: {total_points}")
            self.assertTrue(85 <= total_points <= 95, f"Expected 85-95, got {total_points}")

    def test_parse_tables(self):
        section = (
            "//Tables\n"
            "['doctor']\n"
            "['Patient']\n"
            "['Medicine']"
        )
        logger.info("Parsing tables section")
        result = er_parser.parse_tables(section)
        logger.info(f"Parsed tables: {result}")
        expected = {"doctor": (), "Patient": (), "Medicine": ()}
        self.assertEqual(result, expected)

    def test_parse_relations(self):
        section = (
            "//Relations\n"
            "(\"prescribes\", ([\"doctor\", 1, \"n\"], [\"Patient\", 1, \"n\"]), ([\"Medicine\", 0, \"n\"]))"
        )
        logger.info("Parsing relations section")
        result = er_parser.parse_relations(section)
        logger.info(f"Parsed relations: {result}")
        expected = {
            "prescribes": {
                "tables": (["doctor", 1, "n"], ["Patient", 1, "n"]),
                "attr": (["Medicine", 0, "n"])
            }
        }
        self.assertEqual(result, expected)

if __name__ == "__main__":
    unittest.main(verbosity=2)