"""验证知识检索、真实来源和知识证据约束，不调用外部接口。"""

import unittest

from sports.common.deepseek_agent import DeepSeekError, run_agent
from sports.common.tactical_knowledge import TacticalKnowledgeBase
from sports.common.tactical_tools import TacticalTools
from tests.test_agent import FakeClient, dataset, tool_call


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.knowledge = TacticalKnowledgeBase()

    def test_synonyms_and_bilingual_queries_retrieve_concept(self):
        for query in ('前场压迫', 'HIGH PRESS', '高位逼抢要哪些数据'):
            match = self.knowledge.search(query)['matches'][0]
            self.assertEqual(match['id'], 'K001')
            self.assertEqual(match['sources'][0]['publisher'], 'FIFA Training Centre')
            self.assertTrue(match['sources'][0]['url'].startswith('https://www.fifatrainingcentre.com/'))
        self.assertEqual(self.knowledge.search('counter pressing')['matches'][0]['id'], 'K004')

    def test_unknown_topic_is_not_given_unrelated_fallback(self):
        result = self.knowledge.search('量子纠缠的实验测量')
        self.assertEqual(result['status'], 'no_match')
        self.assertEqual(result['matches'], [])

    def test_limits_and_returned_cards_do_not_mutate_library(self):
        result = self.knowledge.search('高位逼抢', limit=1)
        result['matches'][0]['summary'] = '被修改的副本'
        self.assertNotEqual(self.knowledge.search('高位逼抢')['matches'][0]['summary'], '被修改的副本')
        for query, limit in (('', 1), ('x'*501, 1), ('反抢', True), ('反抢', 6)):
            with self.assertRaises(ValueError):
                self.knowledge.search(query, limit)

    def test_agent_forces_knowledge_and_accepts_real_card(self):
        fake = FakeClient([tool_call('get_dataset_overview', {}),
                           tool_call('search_tactical_knowledge', {'query': '高位逼抢'}, 'call-2'),
                           {'content': '高位逼抢需要球权和施压行为依据，当前不能自动判定。[E2][K001]'}])
        result = run_agent('什么是高位逼抢？', TacticalTools(dataset()), fake)
        self.assertIn('[K001]', result['answer'])
        self.assertEqual(fake.requests[1]['tool_choice']['function']['name'], 'search_tactical_knowledge')

    def test_unretrieved_card_and_missing_knowledge_citation_are_rejected(self):
        for answer in ('高位逼抢需要额外依据。[E2][K999]', '高位逼抢需要额外依据。[E1]'):
            fake = FakeClient([tool_call('get_dataset_overview', {}),
                               tool_call('search_tactical_knowledge', {'query': '高位逼抢'}, 'call-2'),
                               {'content': answer}])
            with self.assertRaises(DeepSeekError):
                run_agent('什么是高位逼抢？', TacticalTools(dataset()), fake, max_rounds=3)

    def test_no_match_can_be_reported_without_inventing_card(self):
        fake = FakeClient([tool_call('get_dataset_overview', {}),
                           tool_call('search_tactical_knowledge', {'query': '量子纠缠'}, 'call-2'),
                           {'content': '知识库未覆盖该概念，没有检索到匹配条目。[E2]'}])
        result = run_agent('这个概念是什么？', TacticalTools(dataset()), fake)
        self.assertEqual(result['evidence'][1]['result']['status'], 'no_match')


if __name__ == '__main__':
    unittest.main()
