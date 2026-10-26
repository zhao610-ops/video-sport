"""跨平台准备足球示例所需的公开模型和可选示例视频。"""

import argparse
from pathlib import Path


MODEL_FILES = {
    "football-ball-detection.pt": "1isw4wx-MK9h9LMr36VvIWlJD6ppUvw7V",
    "football-player-detection.pt": "17PXFNlx-jI7VjVo_vQnB1sONjRyvoB-q",
    "football-pitch-detection.pt": "1Ma5Kt86tgpdjCTKfum79YMgNnSjcoOyf",
}

SAMPLE_FILES = {
    "0bfacc_0.mp4": "12TqauVZ9tLAv8kWxTTBFWtgt2hNQ4_ZF",
    "2e57b9_0.mp4": "19PGw55V8aA6GZu5-Aac5_9mCy3fNxmEf",
    "08fd33_0.mp4": "1OG8K6wqUw9t7lp9ms1M48DxRhwTYciK-",
    "573e61_0.mp4": "1yYPKuXbHsCxqjA9G-S6aeR2Kcnos8RPU",
    "121364_0.mp4": "1vVwjW1dE1drIdd4ZSILfbCGPD4weoNiu",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="下载足球示例模型和可选视频")
    parser.add_argument(
        "--include-samples",
        action="store_true",
        help="同时下载上游提供的示例视频（文件较大）",
    )
    args = parser.parse_args()

    try:
        import gdown
    except ImportError as exc:
        raise SystemExit("请先运行：python -m pip install gdown") from exc

    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    files = dict(MODEL_FILES)
    if args.include_samples:
        files.update(SAMPLE_FILES)

    for filename, file_id in files.items():
        destination = data_dir / filename
        if destination.is_file() and destination.stat().st_size > 0:
            print(f"已存在，跳过：{destination}")
            continue
        print(f"正在下载：{filename}")
        result = gdown.download(id=file_id, output=str(destination), quiet=False)
        if not result or not destination.is_file() or destination.stat().st_size == 0:
            raise SystemExit(f"下载失败：{filename}。请检查网络或上游文件权限。")

    print(f"准备完成，文件位于：{data_dir}")


if __name__ == "__main__":
    main()
