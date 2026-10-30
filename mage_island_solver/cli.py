"""
JSON で渡したゲームの観測結果から、各プレイヤーの正体の候補を表示する CLI です。

終了コード:
    0: 矛盾しない割り当てがある
    1: 矛盾 (一致するケースがない。入力ミスか、モデルが実際のルールと違う)
    2: 入力エラー
"""

import argparse
import json
import sys

from .solver import Game, Location, Observation, Role, deduce

GAME_KEYS = {'seats', 'hp', 'location', 'items'}
ITEM_NAMES = [location.name for location in Location if location is not Location.INITIAL]
MODEL_NOTE = '1ターン目のみ・公式ルール未照合 (docs/RULES.md)'
EMPTY_STOCK_NOTE = '在庫切れのときの挙動 (docs/RULES.md の仮定) に依存するケースを含みます。'
INCONSISTENT_NOTE = '入力ミスか、このモデルが実際のルールと違う可能性があります。'


class InputError(ValueError):
    pass


def _reject_duplicate_keys(pairs):
    # 重複したキーは、どちらの値を使うべきか分からないので入力エラーにします。
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise InputError(f'キーが重複しています: {", ".join(duplicates)}')
    return dict(pairs)


def parse_games(data):
    # JSON をパースした値を検証して Game のリストにします。
    if not isinstance(data, dict) or set(data) != {'games'}:
        raise InputError('トップレベルは {"games": [...]} にしてください。')
    if not isinstance(data['games'], list) or not data['games']:
        raise InputError('games には1つ以上のゲームを指定してください。')
    return [_parse_game(number, game) for number, game in enumerate(data['games'], start=1)]


def _parse_game(number, game):
    prefix = f'ゲーム{number}'
    if not isinstance(game, dict) or set(game) != GAME_KEYS:
        raise InputError(f'{prefix}: キーは {", ".join(sorted(GAME_KEYS))} の4つにしてください。')

    seats = game['seats']
    if not isinstance(seats, list) or not all(isinstance(seat, str) and seat for seat in seats):
        raise InputError(f'{prefix}: seats はプレイヤー名 (文字列) のリストにしてください。')

    hp = game['hp']
    if isinstance(hp, bool) or not isinstance(hp, int):
        raise InputError(f'{prefix}: hp は整数にしてください。')

    location = game['location']
    if not isinstance(location, str) or location not in Location.__members__:
        raise InputError(f'{prefix}: location は {", ".join(Location.__members__)} のどれかにしてください。')

    items = game['items']
    if not isinstance(items, list) or not all(item in ITEM_NAMES for item in items):
        raise InputError(f'{prefix}: items は {", ".join(ITEM_NAMES)} のリストにしてください。')

    observation = Observation.of(hp, Location[location], [Location[item] for item in items])
    return Game(tuple(seats), observation)


def _format_assignment(assignment):
    return ', '.join(f'{player}={role.value}' for player, role in assignment)


def _format_case(seats, case):
    executed = case.outcome.executed_count
    codes = ' -> '.join(
        code.value if i < executed else f'[{code.value}]' for i, code in enumerate(case.codes)
    )
    roles = ', '.join(f'{player}={role.value}' for player, role in zip(seats, case.roles))
    return f'{codes}  ({roles})'


def render_text(deduction):
    lines = [f'ルールモデル: {MODEL_NOTE}', '']
    for number, result in enumerate(deduction.games, start=1):
        game = result.game
        observation = game.observation
        lines.append(
            f'ゲーム{number}: 座席順 {", ".join(game.seats)} / HP {observation.hp} / '
            f'{observation.location.value} / アイテム {", ".join(observation.items) or "なし"}'
        )
        lines.append(f'  単体で一致: {result.matched_case_count} ケース, 割り当て {result.assignment_count} 通り')
        if result.cases:
            lines.append('  全ゲームと矛盾しないコード順 ([...] は HP 切れで未実行):')
            lines.extend(f'    {_format_case(game.seats, case)}' for case in result.cases)
        lines.append('')

    if not deduction.consistent:
        empty_games = [str(number) for number, result in enumerate(deduction.games, start=1)
                       if result.matched_case_count == 0]
        if empty_games:
            lines.append(f'矛盾: ゲーム{", ".join(empty_games)} に一致するケースがありません。')
        else:
            lines.append('矛盾: 全ゲームに共通する割り当てがありません。')
        lines.append(INCONSISTENT_NOTE)
        return '\n'.join(lines)

    lines.append(f'矛盾しない割り当て: {len(deduction.assignments)} 通り')
    lines.extend(f'  {_format_assignment(assignment)}' for assignment in deduction.assignments)
    lines.append('プレイヤーごとの候補:')
    lines.extend(
        f'  {player}: {", ".join(role.value for role in roles)}'
        for player, roles in deduction.role_candidates().items()
    )
    lines.append(f'BLACK の候補: {", ".join(deduction.black_candidates())}')
    if deduction.relies_on_empty_stock_model:
        lines.append(f'注意: {EMPTY_STOCK_NOTE}')
    return '\n'.join(lines)


def to_json(deduction):
    return {
        'model': {'scope': 'turn-1-only', 'rules': 'docs/RULES.md', 'official_rules_verified': False},
        'consistent': deduction.consistent,
        'relies_on_empty_stock_model': deduction.relies_on_empty_stock_model,
        'games': [
            {
                'seats': list(result.game.seats),
                'hp': result.game.observation.hp,
                'location': result.game.observation.location.value,
                'items': list(result.game.observation.items),
                'matched_case_count': result.matched_case_count,
                'matched_assignment_count': result.assignment_count,
                'consistent_cases': [
                    {
                        'codes': [code.value for code in case.codes],
                        'executed_count': case.outcome.executed_count,
                        'roles': [role.value for role in case.roles],
                    }
                    for case in result.cases
                ],
            }
            for result in deduction.games
        ],
        'assignments': [{player: role.value for player, role in assignment} for assignment in deduction.assignments],
        'role_candidates': {
            player: [role.value for role in roles] for player, roles in deduction.role_candidates().items()
        },
        'black_candidates': list(deduction.black_candidates()),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog='python -m mage_island_solver',
        description='「魔法使いの眠る島」1ターン目の観測結果から、各プレイヤーの正体の候補を求めます。'
                    ' ルールの仮定は docs/RULES.md (公式ルールとは未照合)。',
        epilog=f'入力例は examples/sample.json。終了コード: 0=候補あり, 1=矛盾, 2=入力エラー。 役割: {", ".join(Role.__members__)}',
    )
    parser.add_argument('input', help='ゲームの観測結果を書いた JSON ファイル')
    parser.add_argument('--json', action='store_true', help='結果を JSON で出力する')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        with open(args.input, encoding='utf-8') as file:
            data = json.load(file, object_pairs_hook=_reject_duplicate_keys)
        deduction = deduce(parse_games(data))
    except OSError as error:
        parser.error(f'{args.input} を読めません: {error.strerror}')
    except json.JSONDecodeError as error:
        parser.error(f'JSON として読めません: {error}')
    except ValueError as error:
        parser.error(str(error))

    if args.json:
        print(json.dumps(to_json(deduction), ensure_ascii=False, indent=2))
    else:
        print(render_text(deduction))
    return 0 if deduction.consistent else 1


if __name__ == '__main__':
    sys.exit(main())
