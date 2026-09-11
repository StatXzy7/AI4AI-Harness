"""Behavioral checks of typed profile attribution and real SQLite feedback."""
import json
import sqlite3
import unittest
from contextlib import closing

from experiment.revision.runtime_response_profiles import CURRENT_FIELD, STEPS, ResponseIO, current_step, run, settings


class ProfileTests(unittest.TestCase):
    def test_current_field_ignores_other_steps_in_context_but_rejects_ambiguity(self):
        context = '\n'.join(STEPS)
        for i, step in enumerate(STEPS):
            self.assertEqual(current_step(context + '\n' + CURRENT_FIELD + '\n' + step + '\n\n', STEPS), i)
        self.assertIsNone(current_step(context, STEPS))
        self.assertIsNone(current_step((CURRENT_FIELD + '\n' + STEPS[0] + '\n') * 2, STEPS))
        self.assertIsNone(current_step(CURRENT_FIELD + '\nunknown', STEPS))

    def test_partial_answers_must_be_carried_to_assembly(self):
        case = next(c for c in settings() if c['strategy'] == 'decompose')
        with closing(sqlite3.connect(':memory:')) as db:
            io = ResponseIO(case, db)
            self.assertEqual(json.loads(io.llm('plan')), STEPS)
            for i, step in enumerate(STEPS):
                self.assertEqual(io.llm(CURRENT_FIELD + '\n' + step), case['answers'][i])
            self.assertEqual(io.llm('assemble ' + '\n'.join(case['answers'])), case['final'])
            self.assertEqual(io.trace[-1]['response_role'], 'assembly_sql')
            io.llm('assemble without the received answers')
            self.assertTrue(io.issues)
            self.assertEqual(io.trace[-1]['response_role'], 'unresolved_request')

    def test_sqlite_feedback_is_actual_and_dropped_feedback_does_not_receive_fix(self):
        case = next(c for c in settings() if c['name'] == 'sqlite_missing_column')
        def solve(io, question):
            initial = io.llm(question)
            result = io.execute(initial)
            self.assertFalse(result['ok'])
            self.assertIn('absent', result['error'])
            discarded = io.llm('fix it')
            self.assertEqual(discarded, initial)
            repaired = io.llm('fix ' + result['error'])
            self.assertTrue(io.execute(repaired)['ok'])
            return repaired
        result = run(solve, case)
        self.assertIsNone(result['error'])
        self.assertEqual(result['trace'][1]['error_type'], 'OperationalError')

    def test_json_fields_and_invalid_input_are_preserved(self):
        cases = [c for c in settings() if c['strategy'] == 'schema_link']
        for case in cases:
            with closing(sqlite3.connect(':memory:')) as db:
                text = ResponseIO(case, db).llm('link')
                if case['linking'] is None:
                    with self.assertRaises(ValueError):
                        json.loads(text)
                else:
                    self.assertEqual(json.loads(text), case['linking'])


if __name__ == '__main__':
    unittest.main()
