import json
from pathlib import Path
import subprocess
import sys

import pytest

from mage_island_solver.cli import main

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / 'examples' / 'sample.json'
SEATS = ['PYTHON', 'TASK', 'MONITOR', 'DB']


def write_games(tmp_path, *games):
    path = tmp_path / 'games.json'
    path.write_text(json.dumps({'games': list(games)}), encoding='utf-8')
    return str(path)


def game(**overrides):
    return {'seats': SEATS, 'hp': -1, 'location': 'RED', 'items': ['RED', 'PURPLE'], **overrides}


def test_sample_text_output(capsys):
    assert main([str(SAMPLE)]) == 0

    out = capsys.readouterr().out
    assert '1ターン目のみ・公式ルール未照合' in out
    assert '単体で一致: 15 ケース, 割り当て 9 通り' in out
    assert 'green -> blue -> black_blue -> [red]' in out
    assert '矛盾しない割り当て: 7 通り' in out
    assert 'BLACK の候補: DB, TASK' in out
    assert '注意:' not in out


def test_sample_json_output(capsys):
    assert main([str(SAMPLE), '--json']) == 0

    result = json.loads(capsys.readouterr().out)
    assert result['model']['official_rules_verified'] is False
    assert result['consistent'] is True
    assert result['relies_on_empty_stock_model'] is False
    assert len(result['assignments']) == 7
    assert result['black_candidates'] == ['DB', 'TASK']
    assert result['role_candidates']['DB'] == ['RAINBOW', 'BLACK']
    assert [game['matched_case_count'] for game in result['games']] == [15, 82]


def test_inconsistent_observation_exits_1(tmp_path, capsys):
    path = write_games(tmp_path, game(hp=3, location='INITIAL', items=['RED']))

    assert main([path]) == 1

    out = capsys.readouterr().out
    assert '矛盾: ゲーム1 に一致するケースがありません。' in out


def test_no_common_assignment_exits_1(tmp_path, capsys):
    # purple → purple → blue → black_blue しかなく、3人目 (MONITOR) は WHITE に決まる。
    monitor_white = game(hp=0, location='BLUE', items=['BLUE', 'PURPLE', 'PURPLE'])
    # purple → purple → black_purple で止まるしかなく、3人目 (MONITOR) は BLACK に決まる。
    monitor_black = game(hp=0, location='PURPLE', items=['PURPLE', 'PURPLE'])
    path = write_games(tmp_path, monitor_white, monitor_black)

    assert main([path]) == 1

    assert '矛盾: 全ゲームに共通する割り当てがありません。' in capsys.readouterr().out


def test_empty_stock_dependency_is_reported(tmp_path, capsys):
    # green を3回使うと3回目は在庫切れ。 docs/RULES.md の仮定に依存する。
    path = write_games(tmp_path, game(hp=2, location='GREEN', items=['GREEN', 'GREEN']))

    assert main([path]) == 0
    assert '注意: 在庫切れのときの挙動' in capsys.readouterr().out
    assert main([path, '--json']) == 0
    assert json.loads(capsys.readouterr().out)['relies_on_empty_stock_model'] is True


@pytest.mark.parametrize('data', [
    [],
    {},
    {'games': []},
    {'games': [game(), game()], 'extra': 1},
    {'games': [{k: v for k, v in game().items() if k != 'items'}]},
    {'games': [game(note='x')]},
    {'games': [game(seats='PYTHON')]},
    {'games': [game(seats=SEATS[:3])]},
    {'games': [game(seats=['PYTHON', 'PYTHON', 'TASK', 'DB'])]},
    {'games': [game(seats=['PYTHON', 'TASK', 'MONITOR', ''])]},
    {'games': [game(), game(seats=['PYTHON', 'TASK', 'MONITOR', 'X'])]},
    {'games': [game(hp=True)]},
    {'games': [game(hp='-1')]},
    {'games': [game(hp=-1.0)]},
    {'games': [game(location='red')]},
    {'games': [game(location=['RED'])]},
    {'games': [game(location={'RED': 1})]},
    {'games': [game(location=None)]},
    {'games': [game(items=['INITIAL'])]},
    {'games': [game(items='RED')]},
])
def test_invalid_input_exits_2(tmp_path, data):
    path = tmp_path / 'games.json'
    path.write_text(json.dumps(data), encoding='utf-8')

    with pytest.raises(SystemExit) as error:
        main([str(path)])
    assert error.value.code == 2


@pytest.mark.parametrize('text', [
    '{"games": [], "games": [' + json.dumps(game()) + ']}',
    json.dumps({'games': [game()]}).replace('"hp": -1', '"hp": 3, "hp": -1'),
])
def test_duplicate_keys_exit_2(tmp_path, text):
    # 重複したキーは、どちらの値を使うべきか分からないので入力エラーにします。
    path = tmp_path / 'games.json'
    path.write_text(text, encoding='utf-8')

    with pytest.raises(SystemExit) as error:
        main([str(path)])
    assert error.value.code == 2


def test_unreadable_input_exits_2(tmp_path):
    broken = tmp_path / 'broken.json'
    broken.write_text('{', encoding='utf-8')

    for path in (broken, tmp_path / 'missing.json'):
        with pytest.raises(SystemExit) as error:
            main([str(path)])
        assert error.value.code == 2


def test_module_entry_point():
    completed = subprocess.run(
        [sys.executable, '-m', 'mage_island_solver', str(SAMPLE), '--json'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)['black_candidates'] == ['DB', 'TASK']
