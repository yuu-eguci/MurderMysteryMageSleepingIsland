"""
マーダーミステリー「魔法使いの眠る島」、黒のコード所有者特定プログラム。

1ターン目終了時のドローンの HP・場所・所持アイテムから、
実行されたコードの順番と、各プレイヤーの正体 (役割) の候補を求めます。
ルールの仮定は docs/RULES.md を参照してください。公式ルールとは照合していません。
"""

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import itertools


class Location(Enum):
    # Drone の居場所を表す enum です。
    INITIAL = 'INITIAL'
    RED = 'RED'
    BLUE = 'BLUE'
    GREEN = 'GREEN'
    PURPLE = 'PURPLE'


class Role(Enum):
    # Player の正体を表す enum です。
    PURPLE = 'PURPLE'
    RAINBOW = 'RAINBOW'
    WHITE = 'WHITE'
    BLACK = 'BLACK'


class Code(Enum):
    # プレイヤーが選択できるコードです。
    RED = 'red'
    BLUE = 'blue'
    GREEN = 'green'
    PURPLE = 'purple'
    WHITE = 'white'
    BLACK = 'black'
    BLACK_RED = 'black_red'
    BLACK_BLUE = 'black_blue'
    BLACK_GREEN = 'black_green'
    BLACK_PURPLE = 'black_purple'


INITIAL_HP = 3
SEAT_COUNT = 4
WHITE_PICKUP_LIMIT = 3

# 各地域に最初に置かれているアイテムの個数です。
INITIAL_STOCK = {
    Location.RED: 4,
    Location.BLUE: 3,
    Location.GREEN: 2,
    Location.PURPLE: 3,
}

# 移動コードと、その移動先です。
MOVE_TARGET = {
    Code.RED: Location.RED,
    Code.BLUE: Location.BLUE,
    Code.GREEN: Location.GREEN,
    Code.PURPLE: Location.PURPLE,
}

# 場所指定つきの黒コードと、ダメージが入る場所です。
BLACK_TARGET = {
    Code.BLACK_RED: Location.RED,
    Code.BLACK_BLUE: Location.BLUE,
    Code.BLACK_GREEN: Location.GREEN,
    Code.BLACK_PURPLE: Location.PURPLE,
}

BLACK_CODES = frozenset([Code.BLACK, *BLACK_TARGET])

# 各役割が利用できるコードの種類です。
AVAILABLE_CODES = {
    Role.PURPLE: (Code.RED, Code.BLUE, Code.GREEN, Code.PURPLE),
    Role.RAINBOW: tuple(Code),
    Role.WHITE: (Code.RED, Code.BLUE, Code.GREEN, Code.WHITE),
    Role.BLACK: (Code.BLACK, *BLACK_TARGET),
}


@dataclass(frozen=True)
class Outcome:
    # ゲーム終了時のドローンの状態です。 items は色の名前をソートした tuple です。
    hp: int
    location: Location
    items: tuple
    # 実際に実行されたコードの数です。 HP が尽きると残りのコードは実行されません。
    executed_count: int
    # 在庫 0 の場所でアイテムを取ろうとしたか。 docs/RULES.md の「在庫切れ」の仮定に依存します。
    hit_empty_stock: bool

    @property
    def observation(self):
        return Observation(self.hp, self.location, self.items)


@dataclass(frozen=True)
class Observation:
    # 実際のゲームで観測したドローンの状態です。
    hp: int
    location: Location
    items: tuple

    @classmethod
    def of(cls, hp, location, items):
        return cls(hp, location, tuple(sorted(item.value for item in items)))


def _take_items(stock, items, location, limit):
    # location のアイテムを、在庫の範囲で最大 limit 個取ります。
    # 在庫 0 なら何も取らず True を返します。 (公式の挙動は不明。 docs/RULES.md の仮定)
    taken = min(limit, stock[location])
    stock[location] -= taken
    items.extend([location] * taken)
    return taken == 0


def _black_damage(code, location):
    if code is Code.BLACK:
        return 1
    return 3 if location is BLACK_TARGET[code] else 0


def simulate(codes):
    # codes を順番に実行したあとのドローンの状態を返します。
    hp = INITIAL_HP
    location = Location.INITIAL
    stock = dict(INITIAL_STOCK)
    items = []
    hit_empty_stock = False
    executed_count = 0

    for i, code in enumerate(codes):
        executed_count += 1
        previous_code = codes[i - 1] if i > 0 else None
        next_code = codes[i + 1] if i + 1 < len(codes) else None

        if code in MOVE_TARGET:
            location = MOVE_TARGET[code]
            hit_empty_stock |= _take_items(stock, items, location, 1)
        elif code is Code.WHITE and previous_code in BLACK_CODES:
            # 黒の無効化は、黒 code 側で行います。
            # drone の現在地のアイテムを3つまで取得。アイテム取得は INITIAL では不可。
            if location is not Location.INITIAL:
                hit_empty_stock |= _take_items(stock, items, location, WHITE_PICKUP_LIMIT)
        elif code is Code.WHITE:
            hp -= 1
        elif next_code is not Code.WHITE:
            # 直後が white の黒コードは無効です。
            hp -= _black_damage(code, location)

        # Drone の hp が尽きたらコードの実行は終了です。
        if hp <= 0:
            break

    return Outcome(hp, location, tuple(sorted(item.value for item in items)), executed_count, hit_empty_stock)


@dataclass(frozen=True)
class Case:
    # 座席順の役割と、座席順に実行されたコードの組み合わせ1つぶんです。
    roles: tuple
    codes: tuple
    outcome: Outcome


@lru_cache(maxsize=1)
def all_cases():
    # 全役割順列 × 各役割が使えるコードの全組み合わせを網羅します。 (24 × 800 = 19,200 ケース)
    cases = []
    for roles in itertools.permutations(Role):
        for codes in itertools.product(*(AVAILABLE_CODES[role] for role in roles)):
            cases.append(Case(roles, codes, simulate(codes)))
    return tuple(cases)


@lru_cache(maxsize=1)
def _cases_by_observation():
    index = {}
    for case in all_cases():
        index.setdefault(case.outcome.observation, []).append(case)
    return {observation: tuple(cases) for observation, cases in index.items()}


def matching_cases(observation):
    # observation と一致するケースをすべて返します。
    return _cases_by_observation().get(observation, ())


@dataclass(frozen=True)
class Game:
    # 1ゲームぶんの入力です。 seats は座席順 (コード入力順) のプレイヤー名です。
    seats: tuple
    observation: Observation


def assignment_of(seats, roles):
    # 「誰が何色か」を、プレイヤー名でソートした ((player, role), ...) で表します。
    return tuple(sorted(zip(seats, roles), key=lambda pair: pair[0]))


@dataclass(frozen=True)
class GameResult:
    game: Game
    # この game の観測と一致するケースのうち、全ゲーム共通の割り当てに残ったものです。
    cases: tuple
    # この game 単体で一致したケースと割り当ての個数です。
    matched_case_count: int
    assignment_count: int


@dataclass(frozen=True)
class Deduction:
    games: tuple
    # 全ゲームの観測と矛盾しない割り当てです。
    assignments: tuple

    @property
    def consistent(self):
        return bool(self.assignments)

    @property
    def players(self):
        return tuple(sorted(self.games[0].game.seats))

    def role_candidates(self):
        candidates = {player: set() for player in self.players}
        for assignment in self.assignments:
            for player, role in assignment:
                candidates[player].add(role)
        return {player: tuple(role for role in Role if role in roles) for player, roles in candidates.items()}

    def black_candidates(self):
        return tuple(player for player, roles in self.role_candidates().items() if Role.BLACK in roles)

    @property
    def relies_on_empty_stock_model(self):
        return any(case.outcome.hit_empty_stock for result in self.games for case in result.cases)


def validate_games(games):
    if not games:
        raise ValueError('ゲームが1つもありません。')
    players = None
    for number, game in enumerate(games, start=1):
        if len(game.seats) != SEAT_COUNT or len(set(game.seats)) != SEAT_COUNT:
            raise ValueError(f'ゲーム{number}: seats には異なる {SEAT_COUNT} 人を指定してください。')
        if players is None:
            players = set(game.seats)
        elif set(game.seats) != players:
            raise ValueError(f'ゲーム{number}: seats のプレイヤーがゲーム1と一致しません。')


def deduce(games):
    # 各ゲームで一致する割り当て (誰が何色か) を求め、割り当て全体で積集合をとります。
    # プレイヤーごとに色の候補を積集合すると、組み合わせとしてありえない割り当てが残るためです。
    games = tuple(games)
    validate_games(games)

    per_game = []
    surviving = None
    for game in games:
        cases = matching_cases(game.observation)
        assignments = {assignment_of(game.seats, case.roles) for case in cases}
        per_game.append((game, cases, assignments))
        surviving = assignments if surviving is None else surviving & assignments

    results = tuple(
        GameResult(
            game=game,
            cases=tuple(case for case in cases if assignment_of(game.seats, case.roles) in surviving),
            matched_case_count=len(cases),
            assignment_count=len(assignments),
        )
        for game, cases, assignments in per_game
    )
    return Deduction(results, tuple(sorted(surviving, key=_assignment_sort_key)))


def _assignment_sort_key(assignment):
    order = list(Role)
    return tuple((player, order.index(role)) for player, role in assignment)
