import argparse
import json
from pathlib import Path

from app.journal.serialization import serialize_value
from app.replay.comparison import build_replay_comparison
from app.replay.dataset import ReplayDataset
from app.replay.strategy_replay import StrategyReplayRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Replay an Earendil run from its market journal and compare it to the real run.',
    )
    parser.add_argument('manifest', help='Path to run_manifest.json')
    parser.add_argument(
        '--output',
        default=None,
        help='Output JSON path. Defaults to REPLAY_REPORT_PATH stored in the manifest.',
    )
    args = parser.parse_args()

    dataset = ReplayDataset(args.manifest)
    replay_report = StrategyReplayRunner(dataset).run()
    comparison = build_replay_comparison(dataset, replay_report)
    report = {
        'replay': replay_report,
        'comparison': comparison,
    }

    output_path = Path(
        args.output
        or dataset.manifest.get('runtime', {})
        .get('settings', {})
        .get('REPLAY_REPORT_PATH', 'data/logs/replay_report.json')
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(serialize_value(report), ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(output_path)


if __name__ == '__main__':
    main()
