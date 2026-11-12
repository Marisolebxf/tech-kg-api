import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from service.tech_enterprise_relation_business import (
    _matching_role_label,
    executive_position_from_source,
)

ORG = 'dd27ebcec9c1cbe02d80704c721172f1'


def record(position, org=ORG):
    return {'org_id': org, 'executives_position': position}


class MultipleExecutivePositionTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            'source_records': {
                'first': record('副总经理'),
                'second': record('财务负责人'),
                'third': record('董事'),
            },
            'existing_payload': record('董事'),
        }

    def resolve(self, payload=None):
        return executive_position_from_source(
            {'extra_json': self.payload if payload is None else payload}, org_id='org_' + ORG
        )

    def test_collects_all_positions_including_later_record(self):
        self.assertEqual(self.resolve(), '副总经理、财务负责人、董事')

    def test_string_and_list_source_records(self):
        self.assertEqual(self.resolve(json.dumps(self.payload)), self.resolve())
        self.assertEqual(self.resolve({'source_records': list(self.payload['source_records'].values())}), self.resolve())

    def test_existing_payload_adds_a_distinct_valid_position(self):
        self.payload['existing_payload'] = record('总会计师')
        self.assertEqual(self.resolve(), '副总经理、财务负责人、董事、总会计师')

    def test_positions_from_other_companies_are_excluded(self):
        self.payload['source_records']['foreign'] = record('董事长', 'other')
        self.payload['existing_payload'] = record('总经理', 'other')
        self.assertEqual(self.resolve(), '副总经理、财务负责人、董事')

    def test_duplicates_whitespace_and_prefixed_company_id(self):
        self.payload['source_records']['duplicate'] = record(' 财务负责人 ', 'org_' + ORG)
        self.assertEqual(self.resolve(), '副总经理、财务负责人、董事')

    def test_invalid_json_missing_company_and_nonstring_positions(self):
        for value in ('{bad', '[]', 123, [], {'existing_payload': {'executives_position': '财务负责人'}},
                      {'existing_payload': record(['财务负责人'])}):
            self.assertEqual(self.resolve(value), '')

    def test_filter_only_displays_matching_real_position(self):
        self.assertEqual(_matching_role_label(self.resolve(), '财务负责人'), '财务负责人')
        self.assertEqual(_matching_role_label(self.resolve(), '董事'), '董事')
        self.assertEqual(_matching_role_label(self.resolve(), '不存在'), '')

    def test_blank_filter_displays_all_and_substring_keeps_actual_label(self):
        self.assertEqual(_matching_role_label(self.resolve(), None), self.resolve())
        self.assertEqual(_matching_role_label(self.resolve(), ''), self.resolve())
        self.assertEqual(_matching_role_label(self.resolve(), '财务'), '财务负责人')

    def test_actual_relation_builder_uses_filtered_role_for_display(self):
        # Exercise the actual nested _add function; isolate unrelated background/provenance work.
        source = Path(__file__).parents[1] / 'service' / 'tech_enterprise_relation_business.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'KeyEnterpriseRelationService')
        run = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'run')
        add = next(n for n in run.body if isinstance(n, ast.FunctionDef) and n.name == '_add')
        code = compile(ast.Module(body=[add], type_ignores=[]), str(source), 'exec')
        for query, expected in ((None, self.resolve()), ('财务负责人', '财务负责人'), ('财务', '财务负责人'), ('不存在', None)):
            with self.subTest(query=query):
                rows = []
                env = {
                    'req': SimpleNamespace(expert_id='person_test', role_type=query),
                    'node_labels': {'org_' + ORG: {'Organization'}},
                    'node_props': {}, 'expert_props': {}, 'relations': rows,
                    'BusinessPeriod': object, 'EnterpriseRelationItem': lambda **kw: SimpleNamespace(**kw),
                    '_matching_role_label': _matching_role_label,
                    '_enterprise_background': lambda p: {}, '_period_from_mapping': lambda *p: None,
                    '_role_level': lambda r: None, '_pick_tech_field': lambda *p: None,
                    'COOPERATION_CONFIDENCE': {'governance': 0.9},
                }
                exec(code, env)
                env['_add']('org_' + ORG, 'governance', '高管任职', self.resolve(), SimpleNamespace(start=''), 'EXECUTIVE_OF')
                self.assertEqual(len(rows), 0 if expected is None else 1)
                if rows:
                    self.assertEqual(rows[0].role_label, expected)
                    self.assertEqual(rows[0].cooperation_mode, '高管任职')


if __name__ == '__main__':
    unittest.main()
