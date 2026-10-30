from collections import Counter
import itertools

import pytest

from mage_island_solver.solver import (
    AVAILABLE_CODES,
    INITIAL_HP,
    INITIAL_STOCK,
    Code,
    Game,
    Location,
    Observation,
    Role,
    all_cases,
    assignment_of,
    deduce,
    matching_cases,
    simulate,
)

SEATS_1 = ('PYTHON', 'TASK', 'MONITOR', 'DB')
SEATS_2 = ('MONITOR', 'PYTHON', 'DB', 'TASK')

# 元の foo.py の __main__ に入っていた 1st game / 2nd game の観測値です。
SAMPLE_GAME_1 = Game(SEATS_1, Observation.of(-1, Location.RED, [Location.RED, Location.PURPLE]))
SAMPLE_GAME_2 = Game(SEATS_2, Observation.of(0, Location.BLUE, [Location.GREEN, Location.BLUE]))


def assignments_of(game):
    return {assignment_of(game.seats, case.roles) for case in matching_cases(game.observation)}


# --- 在庫 ---------------------------------------------------------------

@pytest.mark.parametrize('location, move', [
    (Location.BLUE, Code.BLUE),
    (Location.GREEN, Code.GREEN),
    (Location.PURPLE, Code.PURPLE),
])
def test_white_after_black_never_takes_more_than_stock(location, move):
    # move で1つ取ったあと、black → white で残りを最大3つ取る。合計は在庫数まで。
    outcome = simulate((move, Code.BLACK, Code.WHITE, Code.BLACK))

    assert outcome.items == (location.value,) * INITIAL_STOCK[location]
    assert outcome.hit_empty_stock is False


def test_white_after_black_takes_three_when_enough_stock():
    # RED は在庫4なので、1 + 3 でちょうど取り切る。
    outcome = simulate((Code.RED, Code.BLACK, Code.WHITE, Code.BLACK))

    assert outcome.items == ('RED',) * 4
    assert outcome.hp == INITIAL_HP - 1


def test_move_to_empty_location_moves_without_item():
    # GREEN の在庫は2。3回目の green は移動だけして、アイテムは取れない (docs/RULES.md の仮定)。
    outcome = simulate((Code.GREEN, Code.GREEN, Code.GREEN, Code.BLACK))

    assert outcome.location is Location.GREEN
    assert outcome.items == ('GREEN', 'GREEN')
    assert outcome.hp == INITIAL_HP - 1
    assert outcome.hit_empty_stock is True


def test_white_after_black_at_empty_location_takes_nothing():
    outcome = simulate((Code.GREEN, Code.GREEN, Code.BLACK, Code.WHITE))

    assert outcome.items == ('GREEN', 'GREEN')
    assert outcome.hp == INITIAL_HP
    assert outcome.hit_empty_stock is True


def test_white_after_black_at_initial_takes_nothing():
    outcome = simulate((Code.BLACK, Code.WHITE, Code.RED, Code.WHITE))

    assert outcome.items == ('RED',)
    assert outcome.hp == INITIAL_HP - 1
    assert outcome.hit_empty_stock is False


# --- 元の仕様の保持 ---------------------------------------------------------

def test_black_followed_by_white_is_nullified():
    assert simulate((Code.RED, Code.BLACK_RED, Code.WHITE, Code.BLUE)).hp == INITIAL_HP


def test_location_black_damages_only_at_its_location():
    assert simulate((Code.RED, Code.BLACK_BLUE, Code.BLUE, Code.BLACK_RED)).hp == INITIAL_HP
    assert simulate((Code.RED, Code.BLACK_RED, Code.BLUE, Code.RED)).hp == 0


def test_execution_stops_when_hp_runs_out_and_negative_hp_is_kept():
    # white(-1) → red → black_red(-3) で HP -1。残りの purple は実行されない。
    outcome = simulate((Code.WHITE, Code.RED, Code.BLACK_RED, Code.PURPLE))

    assert outcome.hp == -1
    assert outcome.location is Location.RED
    assert outcome.items == ('RED',)
    assert outcome.executed_count == 3


# --- 手で確認したサンプル ---------------------------------------------------------

def test_sample_game_1_matches_hand_checked_cases():
    # HP -1 = -1 と -3 (black_red) の組み合わせしかない。-3 が後でないと途中で止まる。
    # RED にいて RED と PURPLE を持つので purple → red の順に移動し、最後に black_red。
    # 残り1枠の -1 は black か、黒の直後でない white。
    expected_codes = set()
    for minus_one in (Code.BLACK, Code.WHITE):
        for codes in ((minus_one, Code.PURPLE, Code.RED),
                      (Code.PURPLE, minus_one, Code.RED),
                      (Code.PURPLE, Code.RED, minus_one)):
            expected_codes.add(codes + (Code.BLACK_RED,))

    cases = matching_cases(SAMPLE_GAME_1.observation)

    assert {case.codes for case in cases} == expected_codes
    # black を使う3通りは役割が PURPLE / WHITE / {RAINBOW, BLACK} で 2 通りずつ。
    # white を使う3通りは black_red が BLACK に決まり、残りの役割が 3 通りずつ。
    assert len(cases) == 3 * 2 + 3 * 3
    assert {dict(assignment)['DB'] for assignment in assignments_of(SAMPLE_GAME_1)} == {Role.RAINBOW, Role.BLACK}


def test_sample_games_are_intersected_as_whole_assignments():
    expected = assignments_of(SAMPLE_GAME_1) & assignments_of(SAMPLE_GAME_2)

    deduction = deduce([SAMPLE_GAME_1, SAMPLE_GAME_2])

    assert set(deduction.assignments) == expected
    assert len(expected) == 7
    for result in deduction.games:
        assert {assignment_of(result.game.seats, case.roles) for case in result.cases} == expected


def test_inconsistent_observations_have_no_assignment():
    impossible = Game(SEATS_1, Observation.of(3, Location.INITIAL, [Location.RED]))

    assert deduce([impossible]).consistent is False
    assert deduce([SAMPLE_GAME_1, Game(SEATS_2, impossible.observation)]).consistent is False


@pytest.mark.parametrize('games', [
    [],
    [Game(('A', 'B', 'C'), SAMPLE_GAME_1.observation)],
    [Game(('A', 'A', 'B', 'C'), SAMPLE_GAME_1.observation)],
    [SAMPLE_GAME_1, Game(('PYTHON', 'TASK', 'MONITOR', 'X'), SAMPLE_GAME_2.observation)],
])
def test_invalid_games_are_rejected(games):
    with pytest.raises(ValueError):
        deduce(games)


# --- 全ケース網羅 ---------------------------------------------------------

def test_all_cases_cover_every_role_order_and_allowed_code():
    cases = all_cases()

    assert len(cases) == 19_200
    assert Counter(case.roles for case in cases) == {roles: 800 for roles in itertools.permutations(Role)}
    for case in cases:
        assert all(code in AVAILABLE_CODES[role] for role, code in zip(case.roles, case.codes))


def test_every_outcome_respects_stock_and_hp_bounds():
    for case in all_cases():
        outcome = case.outcome
        counts = Counter(outcome.items)
        for location, stock in INITIAL_STOCK.items():
            assert counts[location.value] <= stock, case
        assert -2 <= outcome.hp <= INITIAL_HP, case


def test_every_case_is_found_from_its_own_observation():
    cases_by_observation = {}
    for case in all_cases():
        cases_by_observation.setdefault(case.outcome.observation, []).append(case)

    for observation, cases in cases_by_observation.items():
        assignments = set(deduce([Game(SEATS_1, observation)]).assignments)
        assert {assignment_of(SEATS_1, case.roles) for case in cases} == assignments


def test_two_games_match_brute_force_for_every_observation_pair_of_one_truth():
    # 真の割り当てを1つ固定し、2ゲームの観測の全組み合わせについて
    # 「両方のゲームを説明できる割り当ての集合」をそのまま数えた結果と一致することを確認します。
    truth = dict(zip(SEATS_1, (Role.PURPLE, Role.RAINBOW, Role.WHITE, Role.BLACK)))
    roles_1 = tuple(truth[player] for player in SEATS_1)
    roles_2 = tuple(truth[player] for player in SEATS_2)
    observations_1 = {case.outcome.observation for case in all_cases() if case.roles == roles_1}
    observations_2 = {case.outcome.observation for case in all_cases() if case.roles == roles_2}
    truth_assignment = assignment_of(SEATS_1, roles_1)

    explaining_roles = {}
    for case in all_cases():
        explaining_roles.setdefault(case.outcome.observation, set()).add(case.roles)

    def explains(seats, roles_by_player, observation):
        return tuple(roles_by_player[player] for player in seats) in explaining_roles[observation]

    for observation_1, observation_2 in itertools.product(sorted(observations_1, key=repr),
                                                          sorted(observations_2, key=repr)):
        games = [Game(SEATS_1, observation_1), Game(SEATS_2, observation_2)]
        brute_force = {
            assignment_of(SEATS_1, roles)
            for roles in itertools.permutations(Role)
            if all(explains(game.seats, dict(zip(SEATS_1, roles)), game.observation) for game in games)
        }

        deduction = deduce(games)

        assert truth_assignment in deduction.assignments
        assert set(deduction.assignments) == brute_force
