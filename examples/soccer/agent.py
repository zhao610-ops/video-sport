"""通过 DeepSeek 查询本地战术指标，或仅运行不联网的工具检查。"""

import argparse
import json
from pathlib import Path

from sports.common.deepseek_agent import DeepSeekClient, DeepSeekError, load_local_env, run_agent
from sports.common.tactical_tools import TacticalTools


def main():
    parser = argparse.ArgumentParser(description='使用 DeepSeek 工具调用分析保存的足球战术指标')
    parser.add_argument('--metrics', required=True, help='本地 metrics.json')
    parser.add_argument('--question', help='中文问题')
    parser.add_argument('--output-dir', required=True, help='新的回答目录')
    parser.add_argument('--env-file', default=str(Path(__file__).resolve().parents[2] / '.env'))
    parser.add_argument('--check-tools', action='store_true', help='只检查本地工具，不调用模型或读取密钥')
    args = parser.parse_args()
    if not args.check_tools and not args.question:
        parser.error('联网问答需要 --question，或使用 --check-tools 离线检查')
    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError('输出目录非空，请选择新的目录')
    with open(args.metrics, encoding='utf-8') as stream:
        tools = TacticalTools(json.load(stream))
    if args.check_tools:
        result = {'status': 'local_tools_only', 'overview': tools.overview(),
                  'team_0': tools.summarize(0), 'team_1': tools.summarize(1)}
        output.mkdir(parents=True, exist_ok=True)
        with open(output / 'tools-check.json', 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        print(f'本地工具检查完成，未调用模型：{output.resolve()}')
        return
    load_local_env(args.env_file)
    client = DeepSeekClient()
    result = run_agent(args.question, tools, client)
    result['question'] = args.question
    result['model'] = client.model
    output.mkdir(parents=True, exist_ok=True)
    with open(output / 'trace.json', 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
    answer = '# 足球数据分析回答\n\n' + result['answer'] + '\n\n说明：' + result['note'] + '\n'
    (output / 'answer.md').write_text(answer, encoding='utf-8')
    print(result['answer'])
    print(f'回答及证据记录已保存：{output.resolve()}')


if __name__ == '__main__':
    try:
        main()
    except (DeepSeekError, ValueError, OSError) as error:
        # 这些异常来自经过限制的配置、文件操作或已脱敏的网络错误。
        raise SystemExit(str(error)) from None
