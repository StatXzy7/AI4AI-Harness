"""Finite regression witnesses for the archived parser, not a replacement parser."""
import ast
import unittest

from experiment.revision.generation_extraction_audit import legacy_extractor, synthetic_cases


class LegacyExtractionTests(unittest.TestCase):
    def test_plain_python_is_preserved(self):
        case = synthetic_cases()[0]
        self.assertTrue(case['code_preserved'])
        self.assertIsNone(case['extracted_syntax_error'])

    def test_three_valid_python_forms_are_cut_at_inner_fences(self):
        for case in synthetic_cases()[1:]:
            with self.subTest(case=case['case']):
                ast.parse(case['original_code'])
                self.assertFalse(case['code_preserved'])
                self.assertIsNotNone(case['extracted_syntax_error'])
                self.assertFalse(case['legacy_truncated_flag'])

    def test_missing_outer_close_uses_legacy_truncation_flag(self):
        code, truncated = legacy_extractor()('```python\nx = 1', 'python')
        self.assertEqual(code, 'x = 1')
        self.assertTrue(truncated)


if __name__ == '__main__':
    unittest.main()
