import asyncio
import copy
import unittest

from service.expert_colleague_relation import ExpertColleagueRelationService
from tests.test_colleague_person_period_fallback import A_ID, B_ID, Gateway


class ColleagueDepartmentTests(unittest.TestCase):
    def setUp(self):
        self.service = ExpertColleagueRelationService()
        self.gateway = Gateway()
        for person in (self.gateway.a, self.gateway.b):
            person['properties']['work_experience_department_zh'] = '智能计算研究室'

    def query(self, department=None):
        return asyncio.run(self.service._query_impl(
            self.gateway, expert_id=A_ID, target_expert_id=B_ID,
            overlap_period='2015-01～2026-08', department=department,
            space='kgcfg_1808ec65d',
        ))

    def departments(self, a, b):
        self.gateway.a['properties']['work_experience_department_zh'] = a
        self.gateway.b['properties']['work_experience_department_zh'] = b

    def test_same_person_department_returns_with_filter(self):
        result = self.query('智能计算研究室')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['colleagues'][0]['commonDepartment'], '智能计算研究室')

    def test_multiple_values_match_despite_order_and_separator(self):
        self.departments('研发部；财务部', '财务部、研发部')
        self.assertEqual(self.query('财务部')['colleagues'][0]['commonDepartment'], '财务部')
        self.assertEqual(
            set(self.query()['colleagues'][0]['commonDepartment'].split('、')),
            {'研发部', '财务部'},
        )

    def test_lists_json_arrays_and_duplicates(self):
        self.departments(['研发部', '财务部', ' 财务部 '], '["财务部", "研发部"]')
        result = self.query('财务')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['colleagues'][0]['commonDepartment'], '财务部')

    def test_shared_department_is_an_intersection(self):
        self.departments('研发部、财务部', '财务部、市场部')
        self.assertEqual(self.query('研发部')['total'], 0)
        self.assertEqual(self.query('市场部')['total'], 0)
        self.assertEqual(self.query()['colleagues'][0]['commonDepartment'], '财务部')

    def test_one_missing_department_does_not_borrow_from_other_person(self):
        self.departments(None, '智能计算研究室')
        self.assertEqual(self.query('智能计算研究室')['total'], 0)
        self.assertEqual(self.query()['total'], 1)
        self.assertIsNone(self.query()['colleagues'][0]['commonDepartment'])

    def test_edge_department_has_priority_over_person_department(self):
        for edge in self.gateway.edges:
            edge['properties']['department'] = ['研发部', '财务部']
        self.assertEqual(self.query('智能计算研究室')['total'], 0)
        self.assertEqual(self.query('财务部')['total'], 1)

    def test_one_edge_department_and_one_person_department(self):
        self.gateway.edges[0]['properties']['work_experience_department_zh'] = '智能计算研究室'
        self.assertEqual(self.query('智能计算研究室')['total'], 1)

    def test_department_fallback_requires_institution_match_on_both_sides(self):
        for side in ('a', 'b'):
            with self.subTest(side=side):
                self.setUp()
                # Edge dates are complete, so only department fallback is under test.
                for edge in self.gateway.edges:
                    edge['properties']['work_experience_date'] = '2018-01 至 2024-12'
                getattr(self.gateway, side)['properties']['work_experience_institution_zh'] = '另一机构'
                self.assertEqual(self.query('智能计算研究室')['total'], 0)

    def test_unrelated_department_query_does_not_create_a_department(self):
        self.assertEqual(self.query('不存在的部门')['total'], 0)

    def test_all_edge_department_keys_are_supported(self):
        for key in ('work_experience_department_zh', 'department', 'team_name'):
            with self.subTest(key=key):
                self.setUp()
                for edge in self.gateway.edges:
                    edge['properties'][key] = '研发部;财务部'
                self.assertEqual(self.query('财务部')['total'], 1)

    def test_multiple_affiliation_edges_keep_all_common_departments(self):
        self.gateway.edges = [
            dict(copy.deepcopy(edge), properties={
                'department': dept, 'work_experience_date': '2018-01 至 2024-12'
            })
            for edge in self.gateway.edges
            for dept in ('研发部', '财务部')
        ]
        result = self.query()
        self.assertEqual(result['total'], 1)
        self.assertEqual(
            set(result['colleagues'][0]['commonDepartment'].split('、')),
            {'研发部', '财务部'},
        )
        self.assertEqual(self.query('财务部')['colleagues'][0]['commonDepartment'], '财务部')

    def test_parser_handles_empty_invalid_and_hierarchy_values(self):
        for value in (None, '', [], '[invalid', {'department': '财务部'}, 123):
            self.assertEqual(self.service._department_values(value), [])
        self.assertEqual(self.service._department_values('研发中心/智能计算室'), ['研发中心/智能计算室'])


if __name__ == '__main__':
    unittest.main()
