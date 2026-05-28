"""Pokemon Red / Blue (USA) memory reader.

All RAM addresses come from the *pokered* decomp project
(https://github.com/pret/pokered).  This module targets the
USA Rev-A ROM but most offsets are identical for Rev-0 and Blue.

Gen 1 text uses a custom character encoding (0x50 = terminator,
0x80..0x99 = uppercase A-Z, etc.).  Money is stored as 3-byte BCD.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import struct
import os

from pokemon_agent.emulator import Emulator
from pokemon_agent.memory.reader import GameMemoryReader


# ===================================================================
# RAM addresses (WRAM)
# ===================================================================

# -- Player --
ADDR_PLAYER_NAME   = 0xD158   # 11 bytes
ADDR_RIVAL_NAME    = 0xD34A   # 11 bytes
ADDR_MONEY         = 0xD347   # 3 bytes BCD
ADDR_BADGES        = 0xD356   # 1 byte bitmask

# -- Position --
ADDR_MAP_ID        = 0xD35E   # current map number (wCurMap)
ADDR_MAP_Y         = 0xD361   # player Y on map  (wYCoord)
ADDR_MAP_X         = 0xD362   # player X on map  (wXCoord)
ADDR_MAP_BANK      = 0xD35E   # same byte is map id
ADDR_FACING        = 0xC109   # sprite facing   (wSpritePlayerStateData1FacingDirection: 0=down,4=up,8=left,0xC=right)
ADDR_SPRITE_YPIXELS = 0xC104  # wSpritePlayerStateData1YPixels — player sprite Y screen pixel pos
ADDR_SPRITE_XPIXELS = 0xC106  # wSpritePlayerStateData1XPixels — player sprite X screen pixel pos
# -- Tile collision (Gen 1 WRAM) --
ADDR_TILE_STANDING_ON = 0xD365  # wTilePlayerStandingOn
ADDR_TILE_IN_FRONT    = 0xD366  # wTileInFrontOfPlayer
ADDR_CUR_MAP_TILESET  = 0xD367  # wCurMapTileset
ADDR_CUR_MAP_HEIGHT    = 0xD368  # wCurMapHeight
ADDR_CUR_MAP_WIDTH     = 0xD369  # wCurMapWidth
ADDR_CUR_MAP_DATA_PTR  = 0xD36A  # wCurMapDataPtr (2 bytes LE)
ADDR_CUR_MAP_TEXT_PTR  = 0xD36C  # wCurMapTextPtr (2 bytes LE)
ADDR_OVERWORLD_MAP_BASE = 0xC4A0  # wOverworldMap (block ID buffer in WRAM, with 3-block border for map connections)
# wTileMap at 0xC3A0 — screen-relative tile buffer (20 columns x 18 rows).
# Gen 1's CheckTilePassable reads from this buffer, NOT from wOverworldMap.
# Screen positions (tile coords): player center at (8,9), front at (8,7),
# behind at (8,11), left at (6,9), right at (10,9).
ADDR_W_TILE_MAP     = 0xC3A0  # wTileMap — screen tilemap buffer
ADDR_TILESET_BLOCKS_PTR = 0xD529  # wTilesetBlocksPtr (2 bytes LE) — pointer to block→4-tile decomposition table
ADDR_TILESET_GFX_PTR   = 0xD52B  # wTilesetGfxPtr (2 bytes LE)
ADDR_TILESET_COLL_PTR  = 0xD52D  # wTilesetCollisionPtr (2 bytes LE — UNRELIABLE, use COLLISION_TABLE_LOOKUP instead)
# wTilesetTalkingOverTiles at 0xD52F (3 bytes)
# Next: wGrassTile, then PC items at 0xD53A+
# -- Warp data (WRAM bank 0) --
ADDR_NUM_WARPS          = 0xD3AB  # wNumberOfWarps (1 byte)
ADDR_WARP_ENTRIES       = 0xD3AC  # wWarpEntries (MAX_WARP_EVENTS*4 = 128 bytes); each entry: Y, X, warp_id, map_id
# Note: 0xD367 (wPlayerDirection) retains the direction from map entry; 
# 0xC109 is the live sprite state that updates as the player moves.

# -- Party --
ADDR_PARTY_COUNT   = 0xD163
ADDR_PARTY_SPECIES = 0xD164   # 6 bytes + terminator
ADDR_PARTY_DATA    = 0xD16B   # 44 bytes per slot × 6
ADDR_PARTY_OT      = 0xD273   # 11 bytes per OT × 6
ADDR_PARTY_NICKS   = 0xD2B5   # 11 bytes per nick × 6

PARTY_MON_SIZE     = 44

# -- Bag --
ADDR_BAG_COUNT     = 0xD31D
ADDR_BAG_ITEMS     = 0xD31E   # pairs (item_id, qty)

# -- PC items --
ADDR_PC_COUNT      = 0xD53A
ADDR_PC_ITEMS      = 0xD53B

# -- Battle --
ADDR_BATTLE_TYPE   = 0xD057   # 0=none, 1=wild, 2=trainer
ADDR_ENEMY_COUNT   = 0xD89C
ADDR_ENEMY_SPECIES = 0xD89D
ADDR_ENEMY_DATA    = 0xD8A4   # 44 bytes per mon
ADDR_TRAINER_CLASS = 0xD05C   # wTrainerClass — 0 if no trainer engaged, >0 for trainer battles
ADDR_TRAINER_NAME  = 0xD0B2   # wTrainerName — 11 bytes, trainer's sprite name
ADDR_MENU_CURSOR_X = 0xCC24   # wMenuCursorX: 0=left, 1=right
ADDR_MENU_CURSOR_Y = 0xCC25   # wMenuCursorY: 0=top, 1=bottom
ADDR_MENU_CURSOR_POS = 0xCC26 # wMenuCursorPosition: linear index for 2D menus; battle 2x2: 0=FIGHT,1=PKMN,2=ITEM,3=RUN

# -- Dialog --
ADDR_TEXT_BOX_ID   = 0xD125   # wTextBoxID
ADDR_FONT_LOADED   = 0xD730   # wFontLoaded — was mistakenly used as JOY_IGNORE (see below)
ADDR_JOY_IGNORE    = 0xCCB7   # wJoyIgnore — bit5=joypad disabled during text/dialog
ADDR_TEXT_PROGRESS  = 0xC4F2  # approximate; nonzero when text printing
ADDR_STRING_BUFFER  = 0xCF4B  # wStringBuffer — decoded text ready for display (96+ bytes)
MAX_TEXT_LEN        = 96

# -- Gen-1 input gate debug (HRAM mirrors at fixed I/O ports) --
ADDR_HJOY_INPUT    = 0xFF00   # hJoyInput — raw I/O port (read during VBlank IRQ)
ADDR_HJOY_HELD      = 0xFF5A   # hJoyHeld — held keys this frame
ADDR_HJOY_PRESSED   = 0xFF59   # hJoyPressed — newly pressed keys (1-frame flag)
ADDR_HJOY_RELEASED  = 0xFF58   # hJoyReleased — newly released keys

# -- Input/Script state (WRAM) --
ADDR_JOY_IGNORE_EXT = 0xCCB7   # wJoyIgnore — same as ADDR_JOY_IGNORE (0xCCB7)
ADDR_STATUS_FLAGS4  = 0xD7F7   # wStatusFlags4 — BIT_BATTLE_OVER, BIT_INIT_SCRIPTED_MOVEMENT
ADDR_STATUS_FLAGS5  = 0xD7F8   # wStatusFlags5 — BIT_DISABLE_JOYPAD, BIT_SCRIPTED_MOVEMENT_STATE
ADDR_STATUS_FLAGS7  = 0xD7FA   # wStatusFlags7 — BIT_USE_CUR_MAP_SCRIPT, BIT_TRAINER_BATTLE, BIT_FORCED_WARP
ADDR_SIMULATED_JOYPAD_STATES_INDEX = 0xD6E7  # wSimulatedJoypadStatesIndex — scripted walk queue
ADDR_MOVEMENT_FLAGS = 0xD3F5   # wMovementFlags — standing on warp/door, spinning, etc.
ADDR_MAP_SCRIPT_FLAGS = 0xD657  # wCurrentMapScriptFlags

# -- Battle cleanup debug --
ADDR_IS_IN_BATTLE  = 0xD057   # wBattleType — 0=none, 1=wild, 2=trainer (also ADDR_BATTLE_TYPE)
ADDR_BATTLE_RESULT = 0xD7C7   # wBattleResult — outcome after battle ends
ADDR_CUR_OPPONENT   = 0xD6D5   # wCurOpponent — species ID of current enemy
ADDR_FORCE_EVOLUTION = 0xD757  # wForceEvolution — evolution pending flag

# -- Text engine --
ADDR_FONT_LOADED_EXT = 0xD730  # wFontLoaded — font/text engine active flags (was wrongly used as JOY_IGNORE)
ADDR_TEXT_BOX_ID_EXT = 0xD125  # wTextBoxID — text box tile ID (redundant with ADDR_TEXT_BOX_ID)

# -- Overworld player movement --
ADDR_WALK_COUNTER   = 0xD35C   # wWalkCounter — steps in current walk animation

# -- Pokedex --
ADDR_DEX_OWNED     = 0xD2F7   # 19 bytes (152 bits, only 151 used)
ADDR_DEX_SEEN      = 0xD30A

# -- Play time --
ADDR_PLAYTIME_H    = 0xDA40   # 2 bytes (little-endian hours)
ADDR_PLAYTIME_M    = 0xDA42   # 1 byte minutes
ADDR_PLAYTIME_S    = 0xDA43   # 1 byte seconds
ADDR_PLAYTIME_F    = 0xDA44   # 1 byte frames

# -- Event / story flags --
ADDR_EVENT_FLAGS   = 0xD747   # large bitfield (wEventFlags)
ADDR_OAK_PARCEL    = 0xD74E   # bit 1 = has parcel
ADDR_POKEDEX_FLAG  = 0xD74B   # bit 5 = has pokedex
ADDR_TOWN_MAP_FLAG = 0xD5F3   # bit 0 = has town map


# ===================================================================
# Gen-1 character encoding table
# ===================================================================

def _build_encoding_table() -> Dict[int, str]:
    """Build the Gen-1 text encoding lookup."""
    t: Dict[int, str] = {}
    # uppercase A-Z: 0x80..0x99
    for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        t[0x80 + i] = c
    # lowercase a-z: 0xA0..0xB9
    for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
        t[0xA0 + i] = c
    # digits 0-9: 0xF6..0xFF
    for i, c in enumerate("0123456789"):
        t[0xF6 + i] = c
    # punctuation / specials
    t[0x7F] = " "
    t[0xE0] = "'"
    t[0xE1] = "P" # PK
    t[0xE2] = "M" # MN
    t[0xE3] = "-"
    t[0xE6] = "?"
    t[0xE7] = "!"
    t[0xE8] = "."
    t[0xF0] = "¥"
    t[0xF1] = "×"
    t[0xF3] = "/"
    t[0xF4] = ","
    t[0xF5] = "♀"
    # terminator / newline (handled externally; map for safety)
    t[0x50] = ""
    t[0x4F] = "\n"
    t[0x51] = "\n"
    t[0x55] = "\n"
    return t

GEN1_ENCODING: Dict[int, str] = _build_encoding_table()


# ===================================================================
# Name tables
# ===================================================================

SPECIES_NAMES: Dict[int, str] = {
    0: "MissingNo.",
    1: "Bulbasaur", 2: "Ivysaur", 3: "Venusaur",
    4: "Charmander", 5: "Charmeleon", 6: "Charizard",
    7: "Squirtle", 8: "Wartortle", 9: "Blastoise",
    10: "Caterpie", 11: "Metapod", 12: "Butterfree",
    13: "Weedle", 14: "Kakuna", 15: "Beedrill",
    16: "Pidgey", 17: "Pidgeotto", 18: "Pidgeot",
    19: "Rattata", 20: "Raticate",
    21: "Spearow", 22: "Fearow",
    23: "Ekans", 24: "Arbok",
    25: "Pikachu", 26: "Raichu",
    27: "Sandshrew", 28: "Sandslash",
    29: "Nidoran♀", 30: "Nidorina", 31: "Nidoqueen",
    32: "Nidoran♂", 33: "Nidorino", 34: "Nidoking",
    35: "Clefairy", 36: "Clefable",
    37: "Vulpix", 38: "Ninetales",
    39: "Jigglypuff", 40: "Wigglytuff",
    41: "Zubat", 42: "Golbat",
    43: "Oddish", 44: "Gloom", 45: "Vileplume",
    46: "Paras", 47: "Parasect",
    48: "Venonat", 49: "Venomoth",
    50: "Diglett", 51: "Dugtrio",
    52: "Meowth", 53: "Persian",
    54: "Psyduck", 55: "Golduck",
    56: "Mankey", 57: "Primeape",
    58: "Growlithe", 59: "Arcanine",
    60: "Poliwag", 61: "Poliwhirl", 62: "Poliwrath",
    63: "Abra", 64: "Kadabra", 65: "Alakazam",
    66: "Machop", 67: "Machoke", 68: "Machamp",
    69: "Bellsprout", 70: "Weepinbell", 71: "Victreebel",
    72: "Tentacool", 73: "Tentacruel",
    74: "Geodude", 75: "Graveler", 76: "Golem",
    77: "Ponyta", 78: "Rapidash",
    79: "Slowpoke", 80: "Slowbro",
    81: "Magnemite", 82: "Magneton",
    83: "Farfetch'd",
    84: "Doduo", 85: "Dodrio",
    86: "Seel", 87: "Dewgong",
    88: "Grimer", 89: "Muk",
    90: "Shellder", 91: "Cloyster",
    92: "Gastly", 93: "Haunter", 94: "Gengar",
    95: "Onix",
    96: "Drowzee", 97: "Hypno",
    98: "Krabby", 99: "Kingler",
    100: "Voltorb", 101: "Electrode",
    102: "Exeggcute", 103: "Exeggutor",
    104: "Cubone", 105: "Marowak",
    106: "Hitmonlee", 107: "Hitmonchan",
    108: "Lickitung",
    109: "Koffing", 110: "Weezing",
    111: "Rhyhorn", 112: "Rhydon",
    113: "Chansey",
    114: "Tangela",
    115: "Kangaskhan",
    116: "Horsea", 117: "Seadra",
    118: "Goldeen", 119: "Seaking",
    120: "Staryu", 121: "Starmie",
    122: "Mr. Mime",
    123: "Scyther",
    124: "Jynx",
    125: "Electabuzz",
    126: "Magmar",
    127: "Pinsir",
    128: "Tauros",
    129: "Magikarp", 130: "Gyarados",
    131: "Lapras",
    132: "Ditto",
    133: "Eevee", 134: "Vaporeon", 135: "Jolteon", 136: "Flareon",
    137: "Porygon",
    138: "Omanyte", 139: "Omastar",
    140: "Kabuto", 141: "Kabutops",
    142: "Aerodactyl",
    143: "Snorlax",
    144: "Articuno", 145: "Zapdos", 146: "Moltres",
    147: "Dratini", 148: "Dragonair", 149: "Dragonite",
    150: "Mewtwo",
    151: "Mew",
    # Gen I internal species index (used in RAM party struct byte 0):
    177: "Squirtle",  # internal_index=0xB1, national_dex=7
}

    # --- Gen I Internal Species Index ---
    # The party struct at wPartyMon1Species (0xD16B) stores the Gen I internal
    # species index, NOT the National Pokédex number.  For Squirtle (National
    # Dex #7), the internal index is 0xB1 (177).  This differs from the pret/
    # pokered constants where SQUIRTLE=7, because different ROM revisions
    # use different internal tables.  The SPECIES_NAMES dict above maps both
    # National Dex numbers (1-151) and known internal indices (>151) to
    # display names.  When reading the species byte from party data, the
    # internal index is used directly as the lookup key; if not found, the
    # display falls back to the National Dex name if available.
    #
    # For battle enemy species parsing, the raw byte at ADDR_ENEMY_SPECIES
    # (0xD89D) also uses the Gen I internal index.  GEN1_INTERNAL_SPECIES
    # below maps internal index → species name, derived from the pret/pokered
    # pokemon_constants.asm.  Only entries with an explicit const in that file
    # are valid species; gaps (const_skip) are unassigned indices.

# Gen I internal species table from pret/pokered/constants/pokemon_constants.asm.
# Internal ID → display-friendly species name.
# Only entries with explicit `const` are valid species; const_skip gaps are absent.
GEN1_INTERNAL_SPECIES: Dict[int, str] = {
    0: "NO_MON",
    1: "RHYDON", 2: "KANGASKHAN", 3: "NIDORAN_M", 4: "CLEFAIRY",
    5: "SPEAROW", 6: "VOLTORB", 7: "NIDOKING", 8: "SLOWBRO",
    9: "IVYSAUR", 10: "EXEGGUTOR", 11: "LICKITUNG", 12: "EXEGGCUTE",
    13: "GRIMER", 14: "GENGAR", 15: "NIDORAN_F", 16: "NIDOQUEEN",
    17: "CUBONE", 18: "RHYHORN", 19: "LAPRAS", 20: "ARCANINE",
    21: "MEW", 22: "GYARADOS", 23: "SHELLDER", 24: "TENTACOOL",
    25: "GASTLY", 26: "SCYTHER", 27: "STARYU", 28: "BLASTOISE",
    29: "PINSIR", 30: "TANGELA",
    33: "GROWLITHE", 34: "ONIX", 35: "FEAROW", 36: "PIDGEY",
    37: "SLOWPOKE", 38: "KADABRA", 39: "GRAVELER", 40: "CHANSEY",
    41: "MACHOKE", 42: "MR_MIME", 43: "HITMONLEE", 44: "HITMONCHAN",
    45: "ARBOK", 46: "PARASECT", 47: "PSYDUCK", 48: "DROWZEE",
    49: "GOLEM",
    51: "MAGMAR",
    53: "ELECTABUZZ", 54: "MAGNETON", 55: "KOFFING",
    57: "MANKEY", 58: "SEEL", 59: "DIGLETT", 60: "TAUROS",
    64: "FARFETCHD", 65: "VENONAT", 66: "DRAGONITE",
    70: "DODUO", 71: "POLIWAG", 72: "JYNX",
    73: "MOLTRES", 74: "ARTICUNO", 75: "ZAPDOS",
    76: "DITTO", 77: "MEOWTH", 78: "KRABBY",
    82: "VULPIX", 83: "NINETALES",
    84: "PIKACHU", 85: "RAICHU",
    88: "DRATINI", 89: "DRAGONAIR", 90: "KABUTO", 91: "KABUTOPS",
    92: "HORSEA", 93: "SEADRA",
    96: "SANDSHREW", 97: "SANDSLASH",
    98: "OMANYTE", 99: "OMASTAR",
    100: "JIGGLYPUFF", 101: "WIGGLYTUFF",
    102: "EEVEE", 103: "FLAREON", 104: "JOLTEON", 105: "VAPOREON",
    106: "MACHOP", 107: "ZUBAT", 108: "EKANS", 109: "PARAS",
    110: "POLIWHIRL", 111: "POLIWRATH",
    112: "WEEDLE", 113: "KAKUNA", 114: "BEEDRILL",
    116: "DODRIO", 117: "PRIMEAPE", 118: "DUGTRIO",
    119: "VENOMOTH", 120: "DEWGONG",
    123: "CATERPIE", 124: "METAPOD", 125: "BUTTERFREE",
    126: "MACHAMP",
    128: "GOLDUCK", 129: "HYPNO", 130: "GOLBAT",
    131: "MEWTWO", 132: "SNORLAX", 133: "MAGIKARP",
    136: "MUK",
    138: "KINGLER", 139: "CLOYSTER",
    141: "ELECTRODE", 142: "CLEFABLE", 143: "WEEZING",
    144: "PERSIAN", 145: "MAROWAK",
    147: "HAUNTER", 148: "ABRA", 149: "ALAKAZAM",
    150: "PIDGEOTTO", 151: "PIDGEOT", 152: "STARMIE",
    153: "WEEDLE", 154: "VENUSAUR", 155: "TENTACRUEL",
    157: "GOLDEEN", 158: "SEAKING",
    163: "PONYTA", 164: "RAPIDASH",
    165: "RATTATA", 166: "RATICATE",
    167: "NIDORINO", 168: "NIDORINA",
    169: "GEODUDE", 170: "PORYGON", 171: "AERODACTYL",
    173: "MAGNEMITE",
    176: "CHARMANDER", 177: "SQUIRTLE",
    178: "CHARMELEON", 179: "WARTORTLE", 180: "CHARIZARD",
    182: "FOSSIL_KABUTOPS", 183: "FOSSIL_AERODACTYL",
    184: "MON_GHOST",
    185: "ODDISH", 186: "GLOOM", 187: "VILEPLUME",
    188: "BELLSPROUT", 189: "WEEPINBELL", 190: "VICTREEBEL",
}

# Wild encounter data per map.
# Maps map_id → set of internal species IDs possible in grass encounters.
# Source: pret/pokered/data/wild/maps/*.asm
# Only maps we currently traverse are included; extend as needed.
# Viridian Forest (map_id=51) — Red version encounters:
#   WEEDLE(112), KAKUNA(113), METAPOD(124), CATERPIE(123), PIKACHU(84)
# Route 1 (map_id=12): PIDGEY(36), RATTATA(165)
# Route 22 (map_id=33): PIDGEY(36), RATTATA(165), NIDORAN_M(3), NIDORAN_F(15), SPEAROW(5), MANKEY(57)
MAP_WILD_ENCOUNTERS: Dict[int, set[int]] = {
    51: {112, 113, 123, 124, 84},     # Viridian Forest
    12: {36, 165},                      # Route 1
    # Add more maps as they become reachable
}

# Chinese (zh-cn) names for Gen1 internal species IDs.
# Source: 52poke wiki — 宝可梦列表（按第一世代内部编号）
# Only real Pokémon have Chinese names; special entries (NO_MON, FOSSIL_*, MON_GHOST)
# are excluded and fall back to English.
GEN1_INTERNAL_SPECIES_ZH: Dict[int, str] = {
    1: "钻角犀兽", 2: "袋兽", 3: "尼多朗", 4: "皮皮", 5: "烈雀",
    6: "霹靂電球", 7: "尼多王", 8: "呆壳兽", 9: "妙蛙草", 10: "椰蛋树",
    11: "大舌头", 12: "蛋蛋", 13: "臭泥", 14: "耿鬼", 15: "尼多兰",
    16: "尼多后", 17: "卡拉卡拉", 18: "独角犀牛", 19: "拉普拉斯", 20: "风速狗",
    21: "梦幻", 22: "暴鲤龙", 23: "大舌贝", 24: "玛瑙水母", 25: "鬼斯",
    26: "飞天螳螂", 27: "海星星", 28: "水箭龟", 29: "凯罗斯", 30: "蔓藤怪",
    33: "卡蒂狗", 34: "大岩蛇", 35: "大嘴雀", 36: "波波", 37: "呆呆兽",
    38: "勇基拉", 39: "隆隆石", 40: "吉利蛋", 41: "豪力", 42: "魔墙人偶",
    43: "飞腿郎", 44: "快拳郎", 45: "阿柏怪", 46: "派拉斯特", 47: "可达鸭",
    48: "催眠貘", 49: "隆隆岩", 51: "鸭嘴火兽", 53: "电击兽",
    54: "三合一磁怪", 55: "瓦斯弹", 57: "猴怪", 58: "小海狮", 59: "地鼠",
    60: "肯泰罗", 64: "大葱鸭", 65: "毛球", 66: "快龙", 70: "嘟嘟",
    71: "蚊香蝌蚪", 72: "迷唇姐", 73: "火焰鸟", 74: "急冻鸟", 75: "闪电鸟",
    76: "百变怪", 77: "喵喵", 78: "大钳蟹", 82: "六尾", 83: "九尾",
    84: "皮卡丘", 85: "雷丘", 88: "迷你龙", 89: "哈克龙", 90: "化石盔",
    91: "镰刀盔", 92: "墨海马", 93: "海刺龙", 96: "穿山鼠", 97: "穿山王",
    98: "菊石兽", 99: "多刺菊石兽", 100: "胖丁", 101: "胖可丁",
    102: "伊布", 103: "火伊布", 104: "雷伊布", 105: "水伊布",
    106: "腕力", 107: "超音蝠", 108: "阿柏蛇", 109: "派拉斯",
    110: "蚊香君", 111: "蚊香泳士", 112: "独角虫", 113: "铁壳蛹",
    114: "大针蜂", 116: "嘟嘟利", 117: "火暴猴", 118: "三地鼠",
    119: "摩鲁蛾", 120: "白海狮", 123: "绿毛虫", 124: "铁甲蛹",
    125: "巴大蝶", 126: "怪力", 128: "哥达鸭", 129: "引梦貘人",
    130: "大嘴蝠", 131: "超梦", 132: "卡比兽", 133: "鲤鱼王",
    136: "臭臭泥", 138: "巨钳蟹", 139: "刺甲贝", 141: "顽皮雷弹",
    142: "皮可西", 143: "双弹瓦斯", 144: "猫老大", 145: "嘎啦嘎啦",
    147: "鬼斯通", 148: "凯西", 149: "胡地", 150: "比比鸟",
    151: "大比鸟", 152: "宝石海星", 153: "独角虫", 154: "妙蛙花",
    155: "毒刺水母", 157: "角金鱼", 158: "金鱼王", 163: "小火马",
    164: "烈焰马", 165: "小拉达", 166: "拉达", 167: "尼多力诺",
    168: "尼多娜", 169: "小拳石", 170: "多边兽", 171: "化石翼龙",
    173: "小磁怪", 176: "小火龙", 177: "杰尼龟", 178: "火恐龙",
    179: "卡咪龟", 180: "喷火龙", 185: "走路草", 186: "臭臭花",
    187: "霸王花", 188: "喇叭芽", 189: "口呆花", 190: "大食花",
}

# Dex number overrides for non-standard internal species IDs.
# Standard Gen1 species (1-151) have internal_id == dex_no.
# Some emulator/ROM reads may report unusual internal IDs that map to
# standard Pokémon; this dict provides the correct dex_no for those cases.
GEN1_INTERNAL_SPECIES_DEX: Dict[int, int] = {
    153: 13,  # raw 0x99 → Weedle / #013
}

MOVE_NAMES: Dict[int, str] = {
    0: "(none)",
    1: "Pound", 2: "Karate Chop", 3: "Double Slap", 4: "Comet Punch",
    5: "Mega Punch", 6: "Pay Day", 7: "Fire Punch", 8: "Ice Punch",
    9: "Thunder Punch", 10: "Scratch", 11: "Vice Grip", 12: "Guillotine",
    13: "Razor Wind", 14: "Swords Dance", 15: "Cut", 16: "Gust",
    17: "Wing Attack", 18: "Whirlwind", 19: "Fly", 20: "Bind",
    21: "Slam", 22: "Vine Whip", 23: "Stomp", 24: "Double Kick",
    25: "Mega Kick", 26: "Jump Kick", 27: "Rolling Kick", 28: "Sand Attack",
    29: "Headbutt", 30: "Horn Attack", 31: "Fury Attack", 32: "Horn Drill",
    33: "Tackle", 34: "Body Slam", 35: "Wrap", 36: "Take Down",
    37: "Thrash", 38: "Double-Edge", 39: "Tail Whip", 40: "Poison Sting",
    41: "Twineedle", 42: "Pin Missile", 43: "Leer", 44: "Bite",
    45: "Growl", 46: "Roar", 47: "Sing", 48: "Supersonic",
    49: "Sonic Boom", 50: "Disable", 51: "Acid", 52: "Ember",
    53: "Flamethrower", 54: "Mist", 55: "Water Gun", 56: "Hydro Pump",
    57: "Surf", 58: "Ice Beam", 59: "Blizzard", 60: "Psybeam",
    61: "Bubble Beam", 62: "Aurora Beam", 63: "Hyper Beam", 64: "Peck",
    65: "Drill Peck", 66: "Submission", 67: "Low Kick", 68: "Counter",
    69: "Seismic Toss", 70: "Strength", 71: "Absorb", 72: "Mega Drain",
    73: "Leech Seed", 74: "Growth", 75: "Razor Leaf", 76: "Solar Beam",
    77: "Poison Powder", 78: "Stun Spore", 79: "Sleep Powder",
    80: "Petal Dance", 81: "String Shot", 82: "Dragon Rage",
    83: "Fire Spin", 84: "Thunder Shock", 85: "Thunderbolt",
    86: "Thunder Wave", 87: "Thunder", 88: "Rock Throw",
    89: "Earthquake", 90: "Fissure", 91: "Dig", 92: "Toxic",
    93: "Confusion", 94: "Psychic", 95: "Hypnosis", 96: "Meditate",
    97: "Agility", 98: "Quick Attack", 99: "Rage", 100: "Teleport",
    101: "Night Shade", 102: "Mimic", 103: "Screech", 104: "Double Team",
    105: "Recover", 106: "Harden", 107: "Minimize", 108: "Smokescreen",
    109: "Confuse Ray", 110: "Withdraw", 111: "Defense Curl",
    112: "Barrier", 113: "Light Screen", 114: "Haze", 115: "Reflect",
    116: "Focus Energy", 117: "Bide", 118: "Metronome",
    119: "Mirror Move", 120: "Self-Destruct", 121: "Egg Bomb",
    122: "Lick", 123: "Smog", 124: "Sludge", 125: "Bone Club",
    126: "Fire Blast", 127: "Waterfall", 128: "Clamp", 129: "Swift",
    130: "Skull Bash", 131: "Spike Cannon", 132: "Constrict",
    133: "Amnesia", 134: "Kinesis", 135: "Soft-Boiled",
    136: "High Jump Kick", 137: "Glare", 138: "Dream Eater",
    139: "Poison Gas", 140: "Barrage", 141: "Leech Life",
    142: "Lovely Kiss", 143: "Sky Attack", 144: "Transform",
    145: "Bubble", 146: "Dizzy Punch", 147: "Spore",
    148: "Flash", 149: "Psywave", 150: "Splash", 151: "Acid Armor",
    152: "Crabhammer", 153: "Explosion", 154: "Fury Swipes",
    155: "Bonemerang", 156: "Rest", 157: "Rock Slide",
    158: "Hyper Fang", 159: "Sharpen", 160: "Conversion",
    161: "Tri Attack", 162: "Super Fang", 163: "Slash",
    164: "Substitute", 165: "Struggle",
}

TYPE_NAMES: Dict[int, str] = {
    0: "Normal", 1: "Fighting", 2: "Flying", 3: "Poison",
    4: "Ground", 5: "Rock", 6: "Bug", 7: "Ghost",
    # 8 unused
    20: "Fire", 21: "Water", 22: "Grass", 23: "Electric",
    24: "Ice", 25: "Psychic", 26: "Dragon",
}

ITEM_NAMES: Dict[int, str] = {
    0: "(none)",
    1: "Master Ball", 2: "Ultra Ball", 3: "Great Ball", 4: "Poke Ball",
    5: "Town Map", 6: "Bicycle", 7: "?????", 8: "Safari Ball",
    9: "Pokedex", 10: "Moon Stone", 11: "Antidote", 12: "Burn Heal",
    13: "Ice Heal", 14: "Awakening", 15: "Parlyz Heal", 16: "Full Restore",
    17: "Max Potion", 18: "Hyper Potion", 19: "Super Potion", 20: "Potion",
    21: "Boulder Badge", 22: "Cascade Badge", 23: "Thunder Badge",
    24: "Rainbow Badge", 25: "Soul Badge", 26: "Marsh Badge",
    27: "Volcano Badge", 28: "Earth Badge",
    29: "Escape Rope", 30: "Repel", 31: "Old Amber",
    32: "Fire Stone", 33: "Thunder Stone", 34: "Water Stone",
    35: "HP Up", 36: "Protein", 37: "Iron", 38: "Carbos",
    39: "Calcium", 40: "Rare Candy",
    41: "Dome Fossil", 42: "Helix Fossil", 43: "Secret Key",
    44: "?????", 45: "Bike Voucher", 46: "X Accuracy",
    47: "Leaf Stone", 48: "Card Key", 49: "Nugget",
    50: "PP Up", 51: "Poke Doll", 52: "Full Heal",
    53: "Revive", 54: "Max Revive", 55: "Guard Spec.",
    56: "Super Repel", 57: "Max Repel", 58: "Dire Hit",
    59: "Coin", 60: "Fresh Water", 61: "Soda Pop", 62: "Lemonade",
    63: "S.S. Ticket", 64: "Gold Teeth", 65: "X Attack",
    66: "X Defend", 67: "X Speed", 68: "X Special",
    69: "Coin Case", 70: "Oak's Parcel", 71: "Itemfinder",
    72: "Silph Scope", 73: "Poke Flute", 74: "Lift Key",
    75: "Exp. All", 76: "Old Rod", 77: "Good Rod", 78: "Super Rod",
    79: "PP Up", 80: "Ether", 81: "Max Ether", 82: "Elixir",
    83: "Max Elixir",
    196: "HM01", 197: "HM02", 198: "HM03", 199: "HM04", 200: "HM05",
    201: "TM01", 202: "TM02", 203: "TM03", 204: "TM04", 205: "TM05",
    206: "TM06", 207: "TM07", 208: "TM08", 209: "TM09", 210: "TM10",
    211: "TM11", 212: "TM12", 213: "TM13", 214: "TM14", 215: "TM15",
    216: "TM16", 217: "TM17", 218: "TM18", 219: "TM19", 220: "TM20",
    221: "TM21", 222: "TM22", 223: "TM23", 224: "TM24", 225: "TM25",
    226: "TM26", 227: "TM27", 228: "TM28", 229: "TM29", 230: "TM30",
    231: "TM31", 232: "TM32", 233: "TM33", 234: "TM34", 235: "TM35",
    236: "TM36", 237: "TM37", 238: "TM38", 239: "TM39", 240: "TM40",
    241: "TM41", 242: "TM42", 243: "TM43", 244: "TM44", 245: "TM45",
    246: "TM46", 247: "TM47", 248: "TM48", 249: "TM49", 250: "TM50",
}

# fmt: off
MAP_NAMES: Dict[int, str] = {
    0: "Pallet Town", 1: "Viridian City", 2: "Pewter City",
    3: "Cerulean City", 4: "Lavender Town", 5: "Vermilion City",
    6: "Celadon City", 7: "Fuchsia City", 8: "Cinnabar Island",
    9: "Indigo Plateau", 10: "Saffron City", 11: "???",
    12: "Route 1", 13: "Route 2", 14: "Route 3", 15: "Route 4",
    16: "Route 5", 17: "Route 6", 18: "Route 7", 19: "Route 8",
    20: "Route 9", 21: "Route 10", 22: "Route 11", 23: "Route 12",
    24: "Route 13", 25: "Route 14", 26: "Route 15", 27: "Route 16",
    28: "Route 17", 29: "Route 18", 30: "Route 19", 31: "Route 20",
    32: "Route 21", 33: "Route 22", 34: "Route 23", 35: "Route 24",
    36: "Route 25",
    37: "Red's House 1F", 38: "Red's House 2F",
    39: "Blue's House", 40: "Oak's Lab",
    41: "Viridian Pokecenter", 42: "Viridian Mart",
    43: "Viridian School", 44: "Viridian House",
    45: "Viridian Gym",
    46: "Digletts Cave (Route 2)", 47: "Viridian Forest Gate (S)",
    48: "Route 2 Trade House", 49: "Route 2 Gate (N)",
    50: "Viridian Forest South Gate",
    51: "Viridian Forest",
    52: "Pewter Museum 2F",
    53: "Pewter Gym", 54: "Pewter House", 55: "Pewter Mart",
    56: "Pewter Pokecenter",
    57: "Mt Moon 1F", 58: "Mt Moon B1F", 59: "Mt Moon B2F",
    60: "Cerulean House (trashed)", 61: "Cerulean House 2",
    62: "Cerulean Pokecenter", 63: "Cerulean Gym",
    64: "Cerulean Bike Shop", 65: "Cerulean Mart",
    66: "Mt Moon Pokecenter",
    67: "???", 68: "Route 5 Gate", 69: "Underground Path (5-6) Entrance",
    70: "Daycare",
    71: "Route 6 Gate", 72: "Underground Path (5-6) Exit",
    73: "???", 74: "Route 7 Gate",
    75: "Underground Path (7-8) Entrance",
    76: "???",
    77: "Route 8 Gate", 78: "Underground Path (7-8) Exit",
    79: "Rock Tunnel Pokecenter",
    80: "Rock Tunnel 1F", 81: "Power Plant",
    82: "Route 11 Gate 1F", 83: "Digletts Cave (Route 11)",
    84: "Route 11 Gate 2F",
    85: "Route 12 Gate 1F", 86: "Bill's House",
    87: "Vermilion Pokecenter", 88: "Pokemon Fan Club",
    89: "Vermilion Mart", 90: "Vermilion Gym",
    91: "Vermilion House (old rod)", 92: "Vermilion Dock",
    93: "S.S. Anne Exterior", 94: "S.S. Anne 1F Rooms",
    95: "S.S. Anne 2F", 96: "S.S. Anne 2F Rooms",
    97: "S.S. Anne B1F Rooms", 98: "S.S. Anne Bow",
    99: "S.S. Anne Kitchen",  100: "S.S. Anne Captains Room",
    101: "S.S. Anne 1F", 102: "S.S. Anne B1F",
    103: "???",
    104: "???",
    105: "???",
    106: "???",
    107: "???",
    108: "Lavender Pokecenter", 109: "Pokemon Tower 1F",
    110: "Pokemon Tower 2F", 111: "Pokemon Tower 3F",
    112: "Pokemon Tower 4F", 113: "Pokemon Tower 5F",
    114: "Pokemon Tower 6F", 115: "Pokemon Tower 7F",
    116: "Lavender House 1", 117: "Lavender Mart",
    118: "Lavender House 2",
    119: "Celadon Dept Store 1F", 120: "Celadon Dept Store 2F",
    121: "Celadon Dept Store 3F", 122: "Celadon Dept Store 4F",
    123: "Celadon Dept Store Roof", 124: "Celadon Dept Store Elevator",
    125: "Celadon Mansion 1F", 126: "Celadon Mansion 2F",
    127: "Celadon Mansion 3F", 128: "Celadon Mansion Roof",
    129: "Celadon Pokecenter", 130: "Celadon Gym",
    131: "Game Corner", 132: "Celadon Dept Store 5F",
    133: "Game Corner Prize Room",
    134: "Celadon Diner", 135: "Celadon House",
    136: "Celadon Hotel",
    137: "Fuchsia Pokecenter", 138: "Fuchsia Mart",
    139: "Fuchsia House 1", 140: "Fuchsia House 2",
    141: "Safari Zone Gate", 142: "Fuchsia Gym",
    143: "Fuchsia Meeting Room",
    144: "Seafoam Islands B1F", 145: "Seafoam Islands B2F",
    146: "Seafoam Islands B3F", 147: "Seafoam Islands B4F",
    148: "Vermilion House 2 (good rod)",
    149: "Fuchsia House 3 (good rod)", 150: "Mansion 1F",
    151: "Cinnabar Gym", 152: "Cinnabar Lab",
    153: "Cinnabar Lab Trade Room", 154: "Cinnabar Lab Metronome Room",
    155: "Cinnabar Lab Fossil Room",
    156: "Cinnabar Pokecenter", 157: "Cinnabar Mart",
    158: "???",
    159: "Indigo Plateau Lobby", 160: "Copycats House 1F",
    161: "Copycats House 2F",
    162: "Fighting Dojo", 163: "Saffron Gym",
    164: "Saffron House", 165: "Saffron Mart",
    166: "Silph Co 1F", 167: "Silph Co 2F", 168: "Silph Co 3F",
    169: "Silph Co 4F", 170: "Silph Co 5F", 171: "Silph Co 6F",
    172: "Silph Co 7F", 173: "Silph Co 8F", 174: "Silph Co 9F",
    175: "Silph Co 10F", 176: "Silph Co 11F",
    177: "Saffron Pokecenter",
    178: "Mr Psychics House",
    179: "Route 15 Gate 1F", 180: "Route 15 Gate 2F",
    181: "Route 16 Gate 1F", 182: "Route 16 Gate 2F",
    183: "Route 16 Fly House",
    184: "Route 12 House (super rod)",
    185: "Route 18 Gate 1F", 186: "Route 18 Gate 2F",
    187: "Seafoam Islands 1F",
    188: "Route 22 Gate",
    189: "Victory Road 1F",
    190: "Route 12 Gate 2F",
    191: "Vermilion House 3 (diary)",
    192: "Digletts Cave",
    193: "Victory Road 2F",
    194: "Rocket Hideout B1F", 195: "Rocket Hideout B2F",
    196: "Rocket Hideout B3F", 197: "Rocket Hideout B4F",
    198: "Rocket Hideout Elevator",
    199: "???", 200: "???", 201: "???",
    202: "Silph Co Elevator",
    203: "???", 204: "???",
    205: "Trade Center", 206: "Colosseum",
    207: "???", 208: "???",
    209: "Lorelei Room", 210: "Bruno Room",
    211: "Agatha Room", 212: "Lance Room",
    213: "Hall of Fame",
    214: "Underground Path (N-S)", 215: "Champions Room",
    216: "Underground Path (W-E)",
    217: "Cerulean Cave 1F", 218: "Cerulean Cave 2F",
    219: "Cerulean Cave B1F",
    220: "Name Raters House",
    221: "Cerulean House 3",
    222: "???",
    223: "Rock Tunnel B1F",
    224: "Safari Zone East", 225: "Safari Zone North",
    226: "Safari Zone West", 227: "Safari Zone Center",
    228: "Safari Zone Rest House 1", 229: "Safari Zone Secret House",
    230: "Safari Zone Rest House 2", 231: "Safari Zone Rest House 3",
    232: "Safari Zone Rest House 4",
    233: "Unknown Dungeon 2",  # alternate ID
    234: "Unknown Dungeon 3",
    235: "???",
    236: "Pokemon Mansion 2F", 237: "Pokemon Mansion 3F",
    238: "Pokemon Mansion B1F",
    239: "Safari Zone Gate 2",
    240: "Victory Road 3F",
    241: "???",
    242: "???",
    243: "Fighting Dojo 2",
    244: "Indigo Plateau 2",
    245: "???", 246: "???", 247: "???",
    248: "Cerulean Cave 3F",
}
# fmt: on

_STATUS_TABLE = {
    0: "OK",
    # lower 3 bits = sleep counter (1-7 = asleep)
    # bit 3 = poison, bit 4 = burn, bit 5 = freeze, bit 6 = paralysis
}

FACING_NAMES: Dict[int, str] = {
    0x00: "down",
    0x04: "up",
    0x08: "left",
    0x0C: "right",
}

# Gen 1 tileset IDs (from pokered/constants/tileset_constants.asm)
TILESET_NAMES: Dict[int, str] = {
    0: "OVERWORLD",
    1: "REDS_HOUSE",
    2: "MART",
    3: "FOREST",
    4: "POKECENTER",
    5: "GYM",
    6: "HOUSE",
    7: "GATE",
    8: "PORT",
    9: "LAB",
    10: "LOBBY",
    11: "SHIP",
    12: "SHIP_PORT",
    13: "CAVE",
    14: "CEMETERY",
    15: "INTERIOR",
    16: "PLATEAU",
}

# Collision passable-tile list addresses in ROM bank 0 (always-mapped 0x0000-0x3FFF).
# Key = tileset_id, value = GB address of the $ff-terminated passable tile list.
# Extracted from pokered/data/tilesets/collision_tile_ids.asm by scanning the
# compiled PokemonRed.gb ROM.
# NOTE: 0x0000 sentinel means "no collision table found for this tileset".
TILESET_COLLISION_ADDR: Dict[int, int] = {
    0: 0x1735,   # OVERWORLD
    1: 0x1749,   # REDS_HOUSE
    2: 0x1753,   # MART          (Mart_Coll, shared with Pokecenter)
    3: 0x1765,   # FOREST        (Forest_Coll)
    4: 0x1753,   # POKECENTER    (Pokecenter_Coll, shared with Mart)
    5: 0x1759,   # GYM           (Gym_Coll, shared with Dojo)
    6: 0x1775,   # HOUSE
    7: 0x177F,   # GATE          (Gate_Coll, shared with ForestGate/Museum)
    8: 0x1795,   # PORT          (ShipPort_Coll)
    9: 0x17CA,   # LAB
   10: 0x17B8,   # LOBBY
   11: 0x178A,   # SHIP
   12: 0x1795,   # SHIP_PORT     (ShipPort_Coll, same as PORT)
   13: 0x17AC,   # CAVE          (Cavern_Coll)
   14: 0x179A,   # CEMETERY
   15: 0x17A2,   # INTERIOR
   16: 0x17F0,   # PLATEAU
}

BADGE_NAMES = [
    "Boulder", "Cascade", "Thunder", "Rainbow",
    "Soul", "Marsh", "Volcano", "Earth",
]


# ===================================================================
# Reader implementation
# ===================================================================

class RedBlueMemoryReader(GameMemoryReader):
    """Memory reader for *Pokemon Red* and *Pokemon Blue* (USA).

    Parameters
    ----------
    emulator : Emulator
        A loaded PyBoyEmulator running a Red/Blue ROM.
    """

    @property
    def game_name(self) -> str:
        return "Pokemon Red/Blue (USA)"

    # -- helpers --

    def _decode_text(self, addr: int, max_len: int = 11) -> str:
        """Decode a Gen-1 encoded string from RAM."""
        return self.read_string(addr, max_len, GEN1_ENCODING, terminator=0x50)

    def _decode_status(self, status_byte: int) -> str:
        """Return a human-readable status string."""
        if status_byte == 0:
            return "OK"
        parts = []
        sleep = status_byte & 0x07
        if sleep:
            parts.append(f"SLP({sleep})")
        if status_byte & 0x08:
            parts.append("PSN")
        if status_byte & 0x10:
            parts.append("BRN")
        if status_byte & 0x20:
            parts.append("FRZ")
        if status_byte & 0x40:
            parts.append("PAR")
        return "/".join(parts) if parts else "OK"

    def _read_pokemon(self, base: int, nick_addr: int) -> Dict[str, Any]:
        """Parse a 44-byte party Pokemon structure at *base*.

        Layout (offsets from base):
          0:  species (1)
          1:  current HP (2, big-endian)
          3:  level (box level, sometimes called 'box level')
          4:  status condition (1)
          5:  type 1 (1)
          6:  type 2 (1)
          7:  catch rate / held item (1)
          8:  move 1 (1)
          9:  move 2 (1)
          10: move 3 (1)
          11: move 4 (1)
          12: OT ID (2, big-endian)
          14: experience (3, big-endian)
          17: HP EV (2, big-endian)
          19: Attack EV (2)
          21: Defense EV (2)
          23: Speed EV (2)
          25: Special EV (2)
          27: IV data (2)
          29: PP move 1 (1)
          30: PP move 2 (1)
          31: PP move 3 (1)
          32: PP move 4 (1)
          ---- party-exclusive fields ----
          33: level (1, actual party level)
          34: max HP (2, big-endian)
          36: attack (2, big-endian)
          38: defense (2, big-endian)
          40: speed (2, big-endian)
          42: special (2, big-endian)
        """
        data = self.emu.read_range(base, PARTY_MON_SIZE)
        species_id = data[0]
        species_name = SPECIES_NAMES.get(species_id, f"???({species_id})")
        nickname = self._decode_text(nick_addr, 11)

        moves = []
        for i in range(4):
            mid = data[8 + i]
            if mid != 0:
                moves.append({
                    "id": mid,
                    "name": MOVE_NAMES.get(mid, f"???({mid})"),
                    "pp": data[29 + i] & 0x3F,
                    "pp_up": (data[29 + i] >> 6) & 0x03,
                })

        return {
            "raw_species_id": species_id,
            "species_id": species_id,
            'species': species_name,
            'species_zh': GEN1_INTERNAL_SPECIES_ZH.get(species_id),
            "nickname": nickname,
            "level": data[33],
            "hp": (data[1] << 8) | data[2],
            "max_hp": (data[34] << 8) | data[35],
            "status": self._decode_status(data[4]),
            "types": [
                TYPE_NAMES.get(data[5], f"???({data[5]})"),
                TYPE_NAMES.get(data[6], f"???({data[6]})"),
            ],
            "moves": moves,
            "stats": {
                "attack":  (data[36] << 8) | data[37],
                "defense": (data[38] << 8) | data[39],
                "speed":   (data[40] << 8) | data[41],
                "special": (data[42] << 8) | data[43],
            },
            "ot_id": (data[12] << 8) | data[13],
            "experience": (data[14] << 16) | (data[15] << 8) | data[16],
        }

    # -- public interface ---------------------------------------------------

    def read_player(self) -> Dict[str, Any]:
        """Read player info: name, money, badges, position, facing, play time."""
        name = self._decode_text(ADDR_PLAYER_NAME, 11)
        rival = self._decode_text(ADDR_RIVAL_NAME, 11)
        money = self.read_bcd(ADDR_MONEY, 3)

        badge_byte = self.emu.read_u8(ADDR_BADGES)
        badge_list = [BADGE_NAMES[i] for i in range(8) if badge_byte & (1 << i)]

        map_y = self.emu.read_u8(ADDR_MAP_Y)
        map_x = self.emu.read_u8(ADDR_MAP_X)
        facing_byte = self.emu.read_u8(ADDR_FACING)
        facing = FACING_NAMES.get(facing_byte, f"unknown(0x{facing_byte:02X})")

        hours = self.emu.read_u16(ADDR_PLAYTIME_H)
        minutes = self.emu.read_u8(ADDR_PLAYTIME_M)
        seconds = self.emu.read_u8(ADDR_PLAYTIME_S)

        return {
            "name": name,
            "rival_name": rival,
            "money": money,
            "badges": badge_list,
            "badge_count": len(badge_list),
            "position": {"y": map_y, "x": map_x},
            "facing": facing,
            "play_time": f"{hours}:{minutes:02d}:{seconds:02d}",
        }

    def read_party(self) -> List[Dict[str, Any]]:
        """Read the player's party (up to 6 Pokemon)."""
        count = self.emu.read_u8(ADDR_PARTY_COUNT)
        count = min(count, 6)
        party: List[Dict[str, Any]] = []
        for i in range(count):
            base = ADDR_PARTY_DATA + i * PARTY_MON_SIZE
            nick_addr = ADDR_PARTY_NICKS + i * 11
            party.append(self._read_pokemon(base, nick_addr))
        return party

    def read_bag(self) -> List[Dict[str, Any]]:
        """Read bag item list."""
        count = self.emu.read_u8(ADDR_BAG_COUNT)
        count = min(count, 20)  # bag max 20 items in Gen 1
        items: List[Dict[str, Any]] = []
        for i in range(count):
            item_id = self.emu.read_u8(ADDR_BAG_ITEMS + i * 2)
            qty = self.emu.read_u8(ADDR_BAG_ITEMS + i * 2 + 1)
            if item_id == 0xFF:  # terminator
                break
            items.append({
                "id": item_id,
                "item": ITEM_NAMES.get(item_id, f"???({item_id})"),
                "quantity": qty,
            })
        return items

    def read_battle(self) -> Dict[str, Any]:
        """Read battle state (whether in battle & enemy info).

        Distinguishes two phases:
          - "intro_or_text" — wild-intro text is still displayed; cursor
            / enemy data may be transitional and is marked untrusted.
          - "main_menu"     — the four-option battle menu (FIGHT/PKMN/ITEM
            /RUN) is confirmed visible; cursor & enemy data are trusted.

        Phase detection uses ``wJoyIgnore`` bit 5 (dialog active) as the
        primary indicator and ``wTextBoxID`` as a secondary check: values
        0 or 1 correspond to the main battle menu; higher values indicate
        other text boxes (intro, item, etc.) or stale state.

        Output fields:
          - ``in_battle`` (bool): whether any battle is active
          - ``type`` (str): legacy field, ``"wild"``/``"trainer"``/``"none"``
          - ``kind`` (str): ``"wild_battle"``/``"trainer_battle"``/``"unknown"``/``"none"``
          - ``confidence`` (str): ``"high"``/``"medium"``/``"low"``
          - ``evidence`` (dict): all signals used for classification
          - ``run_allowed`` (bool/None): whether RUN option is available
          - ``trainer_class`` (int/None): wTrainerClass register, if >0
          - ``trainer_name`` (str/None): trainer name from wTrainerName
          - ``intro_text_available`` (bool/None): whether wStringBuffer
            contained intro-like text at this read
          (plus existing fields: battle_phase, enemy, cursor, etc.)
        """
        battle_type = self.emu.read_u8(ADDR_BATTLE_TYPE)
        type_name = {0: "none", 1: "wild", 2: "trainer"}.get(battle_type, f"unknown({battle_type})")

        # ---- battle_kind classifier ----
        kind: str
        confidence: str
        evidence: Dict[str, Any] = {}
        run_allowed: Optional[bool] = None
        trainer_class: Optional[int] = None
        trainer_name: Optional[str] = None
        intro_text_available: Optional[bool] = None

        if battle_type == 0:
            kind = "none"
            confidence = "high"
            evidence["battle_type_raw"] = 0
            evidence["trainer_class"] = None
            evidence["trainer_name"] = None
            evidence["intro_text_raw"] = None
        elif battle_type == 1:
            kind = "wild_battle"
            confidence = "high"
            run_allowed = True
            evidence["battle_type_raw"] = 1
            evidence["battle_type_signal"] = "wild"
        elif battle_type == 2:
            kind = "trainer_battle"
            confidence = "high"
            run_allowed = False
            evidence["battle_type_raw"] = 2
            evidence["battle_type_signal"] = "trainer"
            # Read trainer class / name for evidence (best-effort)
            try:
                tc = self.emu.read_u8(ADDR_TRAINER_CLASS)
                if tc != 0:
                    trainer_class = tc
                    evidence["trainer_class"] = tc
            except Exception:
                pass
            try:
                tn_raw = self.emu.read_range(ADDR_TRAINER_NAME, 11)
                term = tn_raw.find(b"\x50")
                if term >= 0:
                    tn_raw = tn_raw[:term]
                if tn_raw and tn_raw[0] != 0:
                    tn_decoded = "".join(GEN1_ENCODING.get(b, f"<{b:02X}>") for b in tn_raw)
                    trainer_name = tn_decoded
                    evidence["trainer_name"] = tn_decoded
            except Exception:
                pass
        else:
            kind = "unknown"
            confidence = "low"
            evidence["battle_type_raw"] = battle_type
            evidence["reason"] = "unexpected_battle_type_value"

        # Try to read wStringBuffer for intro text (best-effort, may be stale)
        if battle_type != 0:
            try:
                raw = self.emu.read_range(ADDR_STRING_BUFFER, 30)
                term_idx = raw.find(b"\x50")
                effective = raw[:term_idx] if term_idx >= 0 else raw
                if len(effective) > 2:
                    intro_text_available = True
                    evidence["intro_text_raw"] = effective.hex(" ", 1)[:60]
                else:
                    intro_text_available = False
            except Exception:
                pass

        result: Dict[str, Any] = {
            "in_battle": battle_type != 0,
            "type": type_name,
            # ---- new structured fields ----
            "kind": kind,
            "confidence": confidence,
            "evidence": evidence,
            "run_allowed": run_allowed,
            "trainer_class": trainer_class,
            "trainer_name": trainer_name,
            "intro_text_available": intro_text_available,
        }
        if battle_type != 0:
            # --- phase detection ---
            joy_ignore = self.emu.read_u8(ADDR_JOY_IGNORE)
            text_box_id = self.emu.read_u8(ADDR_TEXT_BOX_ID)
            in_dialog = bool(joy_ignore & 0x20)

            # Main battle menu is confirmed when:
            #   1. No dialog active (joy_ignore bit 5 = 0), AND
            #   2. Text box ID is 0 (no box) or 1 (main menu box).
            #   2. Larger IDs (13 etc.) indicate stale text or sub-menus.
            main_menu_visible = (not in_dialog) and (text_box_id in (0, 1))

            battle_phase = "main_menu" if main_menu_visible else "intro_or_text"
            result["battle_phase"] = battle_phase
            result["battle_menu_visible"] = main_menu_visible

            # --- raw enemy data (always read, trust gated below) ---
            enemy_species = self.emu.read_u8(ADDR_ENEMY_SPECIES)
            enemy_data = self.emu.read_range(ADDR_ENEMY_DATA, PARTY_MON_SIZE)
            enemy_level = enemy_data[33] if len(enemy_data) > 33 else enemy_data[3]
            enemy_hp = (enemy_data[1] << 8) | enemy_data[2]
            enemy_max_hp = ((enemy_data[34] << 8) | enemy_data[35]) if len(enemy_data) > 35 else 0
            enemy_status = self._decode_status(enemy_data[4])

            moves = []
            for j in range(4):
                mid = enemy_data[8 + j]
                if mid != 0:
                    moves.append(MOVE_NAMES.get(mid, f"???({mid})"))

            result["enemy"] = {
                "species_id": enemy_species,
                "species": GEN1_INTERNAL_SPECIES.get(enemy_species,
                    SPECIES_NAMES.get(enemy_species, f"???({enemy_species})")),
                "species_zh": GEN1_INTERNAL_SPECIES_ZH.get(enemy_species),
                "dex_no": enemy_species if enemy_species <= 151 else GEN1_INTERNAL_SPECIES_DEX.get(enemy_species),
                "level": enemy_level,
                "hp": enemy_hp,
                "max_hp": enemy_max_hp,
                "status": enemy_status,
                "moves": moves,
            }

            # --- raw species byte (battle-level field) ---
            result["enemy_species_raw"] = enemy_species

            # --- trust gates ---
            # enemy_species_trusted:
            #   1. Species must be in GEN1_INTERNAL_SPECIES (valid internal ID)
            #   2. If wild battle, species must be in current map's encounter table
            #   3. battle_phase must be main_menu (not intro/text)
            species_in_table = enemy_species in GEN1_INTERNAL_SPECIES
            species_in_encounter_table = True  # default: trust for trainer battles
            if battle_type == 1:  # wild battle
                current_map_id = self.emu.read_u8(ADDR_MAP_ID)
                expected = MAP_WILD_ENCOUNTERS.get(current_map_id)
                if expected is not None:
                    # We have encounter data for this map — verify species
                    species_in_encounter_table = enemy_species in expected
                else:
                    # Unknown map — cannot verify, treat as unverified
                    species_in_encounter_table = False
            species_trusted = (
                battle_phase == "main_menu"
                and species_in_table
                and species_in_encounter_table
            )
            if battle_phase == "main_menu":
                result["enemy_species_trusted"] = species_trusted
                result["enemy_hp_trusted"] = True
            else:
                result["enemy_species_trusted"] = False
                result["enemy_hp_trusted"] = False

            # --- battle cursor ---
            if battle_phase == "main_menu":
                cur_pos = self.emu.read_u8(ADDR_MENU_CURSOR_POS) & 0xFF
                if cur_pos == 0:
                    result["battle_cursor"] = "fight"
                elif cur_pos == 1:
                    result["battle_cursor"] = "item"
                elif cur_pos == 2:
                    result["battle_cursor"] = "pkmn"
                elif cur_pos == 3:
                    result["battle_cursor"] = "run"
                else:
                    result["battle_cursor"] = "unknown"
                result["battle_cursor_trusted"] = True
            else:
                result["battle_cursor"] = "unknown"
                result["battle_cursor_trusted"] = False
        return result

    def read_dialog(self) -> Dict[str, Any]:
        """Read dialogue / text box state.

        Uses wJoyIgnore as the primary indicator — bit 5 is set by the
        game engine when joypad input is disabled (during text scroll,
        NPC dialog, etc.).  wTextBoxID is unreliable because it can
        retain stale non-zero values after dialog ends (e.g. after
        Oak's intro sequence).

        Also reads wStringBuffer (0xCF4B) to capture the text currently
        displayed or being typed into the dialogue box.  The raw bytes
        and a decoded string are returned as ``text_bytes_hex`` and
        ``text``.
        """
        text_box = self.emu.read_u8(ADDR_TEXT_BOX_ID)
        joy_ignore = self.emu.read_u8(ADDR_JOY_IGNORE)

        # wJoyIgnore ($D730) bit 5 = "being used for text/menu" —
        # this is the authoritative Gen 1 engine flag for active dialog.
        # wTextBoxID (0xD125) and wStringBuffer (0xCF4B) can retain stale
        # non-zero text ("POKé BALL" from Oak's Lab, Pallet Town entrance
        # banner, etc.) after the dialog has ended, so they are **not**
        # reliable indicators of active dialog.
        #
        # The old condition (text_box != 0 OR joy_ignore & 0x20) caused
        # false positives after warps: the engine clears bit 5 on dialog
        # end but leaves text_box at the last value.  Now we use only
        # joy_ignore bit 5, which is always correct.
        in_dialog = bool(joy_ignore & 0x20)

        # Read wStringBuffer — the decoded text ready for display
        try:
            raw = self.emu.read_range(ADDR_STRING_BUFFER, MAX_TEXT_LEN)
            # Find the 0x50 terminator
            term_idx = raw.find(b"\x50")
            effective_len = term_idx if term_idx >= 0 else len(raw)
            text_bytes = raw[:effective_len]

            # If first byte is 0x00 or 0x50, the buffer is empty
            if effective_len == 0 or text_bytes[0] == 0x00:
                decoded_text = None
                text_bytes_hex = None
                decode_status = "no_dialog_text"
            else:
                text_bytes_hex = text_bytes.hex(" ", 1)
                # Decode using the Gen1 encoding table
                decoded_chars = []
                has_unknown = False
                for byte_val in text_bytes:
                    ch = GEN1_ENCODING.get(byte_val)
                    if ch is not None and ch.strip():
                        decoded_chars.append(ch)
                    elif ch == "":
                        continue  # terminator char in map
                    else:
                        decoded_chars.append(f"<{byte_val:02X}>")
                        has_unknown = True

                decoded_text = "".join(decoded_chars)

                if not decoded_text:
                    decode_status = "decoded_with_unknown_bytes"
                elif has_unknown:
                    decode_status = "decoded_with_unknown_bytes"
                else:
                    decode_status = "ok"
        except Exception:
            decoded_text = None
            text_bytes_hex = None
            decode_status = "read_failed"

        return {
            "active": in_dialog,
            "text_box_id": text_box,
            "joy_ignore": joy_ignore,
            "oaks_lab_script": None,
            "text": decoded_text,
            "text_addr": ADDR_STRING_BUFFER,
            "text_bytes_hex": text_bytes_hex,
            "text_decode_status": decode_status,
        }

    def read_gen1_input_debug(self) -> Dict[str, Any]:
        """Read Gen-1 input gate and script state fields.

        This method provides visibility into why player input may be
        blocked or why scripted movement is active. Call this instead
        of guessing when buttons have no effect.

        Key addresses (verified against pret/pokered):
          - wJoyIgnore (0xCCB7): bit5 disables joypad during text/dialog
          - wStatusFlags5 (0xD7F8): bit1=BIT_DISABLE_JOYPAD, bit0=BIT_SCRIPTED_MOVEMENT_STATE
          - wStatusFlags4 (0xD7F7): bit6=BIT_BATTLE_OVER, bit2=BIT_INIT_SCRIPTED_MOVEMENT
          - wStatusFlags7 (0xD7FA): bit0=BIT_USE_CUR_MAP_SCRIPT, bit4=BIT_FORCED_WARP
          - wSimulatedJoypadStatesIndex (0xD6E7): non-zero = scripted walk queue active
          - wMovementFlags (0xD3F5): standing on warp/door/ledge/spinning flags
          - hJoyHeld (0xFF5A): currently held keys
          - hJoyPressed (0xFF59): newly pressed keys (1-frame pulse)

        Decision table:
          A. wJoyIgnore!=0 or bit_DISABLE_JOYPAD=1 → joypad_masked; wait only
          B. wSimulatedJoypadStatesIndex!=0 or BIT_SCRIPTED_MOVEMENT=1 → scripted_input_queue; wait only
          C. wIsInBattle=0 but wBattleResult/wForceEvolution not clean → end_of_battle_cleanup_gap
          D. wFontLoaded bit0=1 and wTextBoxID non-zero → text_engine_owns_input
          E. All gates clear but xy frozen → coordinate_stale_gap

        Returns:
            dict with all raw values and decoded bit fields.
        """
        # HRAM input mirrors
        hjoy_input = self.emu.read_u8(ADDR_HJOY_INPUT)
        hjoy_held = self.emu.read_u8(ADDR_HJOY_HELD)
        hjoy_pressed = self.emu.read_u8(ADDR_HJOY_PRESSED)
        hjoy_released = self.emu.read_u8(ADDR_HJOY_RELEASED)

        # WRAM input gates
        wjoy_ignore = self.emu.read_u8(ADDR_JOY_IGNORE)       # 0xCCB7
        wfont_loaded = self.emu.read_u8(ADDR_FONT_LOADED)    # 0xD730 (was wrongly used as JOY_IGNORE)

        # Status flags
        status_flags4 = self.emu.read_u8(ADDR_STATUS_FLAGS4)  # 0xD7F7
        status_flags5 = self.emu.read_u8(ADDR_STATUS_FLAGS5) # 0xD7F8
        status_flags7 = self.emu.read_u8(ADDR_STATUS_FLAGS7) # 0xD7FA

        # Script/input queues
        sim_joypad_index = self.emu.read_u8(ADDR_SIMULATED_JOYPAD_STATES_INDEX)  # 0xD6E7
        movement_flags = self.emu.read_u8(ADDR_MOVEMENT_FLAGS)   # 0xD3F5
        map_script_flags = self.emu.read_u8(ADDR_MAP_SCRIPT_FLAGS)  # 0xD657

        # Battle cleanup
        battle_type = self.emu.read_u8(ADDR_IS_IN_BATTLE)     # 0xD057 (same as ADDR_BATTLE_TYPE)
        battle_result = self.emu.read_u8(ADDR_BATTLE_RESULT)   # 0xD7C7
        cur_opponent = self.emu.read_u8(ADDR_CUR_OPPONENT)     # 0xD6D5
        force_evolution = self.emu.read_u8(ADDR_FORCE_EVOLUTION)  # 0xD757

        # Text engine
        text_box_id = self.emu.read_u8(ADDR_TEXT_BOX_ID)      # 0xD125

        # Walk counter
        walk_counter = self.emu.read_u8(ADDR_WALK_COUNTER)     # 0xD35C

        # Decode bit fields
        bit_disable_joypad = bool(status_flags5 & 0x02)       # BIT_DISABLE_JOYPAD
        bit_scripted_movement_state = bool(status_flags5 & 0x01)  # BIT_SCRIPTED_MOVEMENT_STATE
        bit_battle_over = bool(status_flags4 & 0x40)          # BIT_BATTLE_OVER_OR_BLACKOUT
        bit_init_scripted_movement = bool(status_flags4 & 0x04)  # BIT_INIT_SCRIPTED_MOVEMENT
        bit_use_cur_map_script = bool(status_flags7 & 0x01)   # BIT_USE_CUR_MAP_SCRIPT
        bit_trainer_battle = bool(status_flags7 & 0x10)       # BIT_TRAINER_BATTLE
        bit_forced_warp = bool(status_flags7 & 0x10)          # BIT_FORCED_WARP (shared bit)

        # Movement flags decode
        standing_on_door = bool(movement_flags & 0x01)
        exiting_door = bool(movement_flags & 0x02)
        standing_on_warp = bool(movement_flags & 0x04)
        ledge_or_fishing = bool(movement_flags & 0x08)
        spinning = bool(movement_flags & 0x10)

        # HJOY key mappings (Game Boy d-pad)
        HJOY_A      = 0x01
        HJOY_B      = 0x02
        HJOY_SELECT = 0x04
        HJOY_START  = 0x08
        HJOY_RIGHT  = 0x10
        HJOY_LEFT   = 0x20
        HJOY_UP     = 0x40
        HJOY_DOWN   = 0x80

        def hjoy_key_names(val: int) -> list:
            keys = []
            if val & HJOY_A:      keys.append("A")
            if val & HJOY_B:      keys.append("B")
            if val & HJOY_SELECT: keys.append("SELECT")
            if val & HJOY_START:  keys.append("START")
            if val & HJOY_RIGHT:  keys.append("RIGHT")
            if val & HJOY_LEFT:   keys.append("LEFT")
            if val & HJOY_UP:     keys.append("UP")
            if val & HJOY_DOWN:   keys.append("DOWN")
            return keys

        # Decision gate
        if wjoy_ignore & 0x20 or bit_disable_joypad:
            gate_conclusion = "joypad_masked"
        elif sim_joypad_index != 0 or bit_scripted_movement_state:
            gate_conclusion = "scripted_input_queue"
        elif battle_type != 0 and bit_battle_over:
            gate_conclusion = "end_of_battle_cleanup_gap"
        elif wfont_loaded & 0x01 and text_box_id != 0:
            gate_conclusion = "text_engine_owns_input"
        elif sim_joypad_index == 0 and wjoy_ignore == 0 and not bit_disable_joypad and not bit_scripted_movement_state:
            if walk_counter == 0:
                gate_conclusion = "input_gates_clear_movement_idle"
            else:
                gate_conclusion = "input_gates_clear_walk_animation_active"
        else:
            gate_conclusion = "indeterminate"

        return {
            # Raw HRAM
            "hjoy_input": hjoy_input,
            "hjoy_input_keys": hjoy_key_names(hjoy_input),
            "hjoy_held": hjoy_held,
            "hjoy_held_keys": hjoy_key_names(hjoy_held),
            "hjoy_pressed": hjoy_pressed,
            "hjoy_pressed_keys": hjoy_key_names(hjoy_pressed),
            "hjoy_released": hjoy_released,
            "hjoy_released_keys": hjoy_key_names(hjoy_released),
            # Raw WRAM input gates
            "wjoy_ignore": wjoy_ignore,
            "wjoy_ignore_bit5_dialog_active": bool(wjoy_ignore & 0x20),
            "wfont_loaded": wfont_loaded,
            "wfont_loaded_bit0_font_active": bool(wfont_loaded & 0x01),
            # Status flags raw
            "status_flags4": status_flags4,
            "status_flags5": status_flags5,
            "status_flags7": status_flags7,
            # Status flags decoded
            "bit_disable_joypad": bit_disable_joypad,
            "bit_scripted_movement_state": bit_scripted_movement_state,
            "bit_battle_over": bit_battle_over,
            "bit_init_scripted_movement": bit_init_scripted_movement,
            "bit_use_cur_map_script": bit_use_cur_map_script,
            "bit_trainer_battle": bit_trainer_battle,
            "bit_forced_warp": bit_forced_warp,
            # Script/input queues
            "sim_joypad_index": sim_joypad_index,
            "movement_flags": movement_flags,
            "standing_on_door": standing_on_door,
            "exiting_door": exiting_door,
            "standing_on_warp": standing_on_warp,
            "ledge_or_fishing": ledge_or_fishing,
            "spinning": spinning,
            "map_script_flags": map_script_flags,
            # Battle cleanup
            "battle_type": battle_type,
            "battle_result": battle_result,
            "cur_opponent": cur_opponent,
            "force_evolution": force_evolution,
            # Text engine
            "text_box_id": text_box_id,
            # Movement
            "walk_counter": walk_counter,
            # Gate decision
            "gate_conclusion": gate_conclusion,
        }

    def read_map_info(self) -> Dict[str, Any]:
        """Read current map id and name."""
        map_id = self.emu.read_u8(ADDR_MAP_ID)
        return {
            "map_id": map_id,
            "map_name": MAP_NAMES.get(map_id, f"Unknown Map ({map_id})"),
        }

    def read_flags(self) -> Dict[str, Any]:
        """Read key story / event flags.

        Uses bag-item presence as the primary source for has_oaks_parcel
        rather than the EVENT_GOT_OAKS_PARCEL flag, because that flag
        only records "ever picked up the parcel", not "still carrying it".
        See pret/pokered/constants/event_constants.asm for flag layout.

        Key event flag indices (base addr ADDR_EVENT_FLAGS = 0xD747):
          EVENT_GOT_POKEDEX     = flag 37   (0xD74B bit 5)
          EVENT_OAK_GOT_PARCEL  = flag 56   (0xD74E bit 0)
          EVENT_GOT_OAKS_PARCEL = flag 57   (0xD74E bit 1)
        """
        badges = self.emu.read_u8(ADDR_BADGES)

        # Pokedex count
        owned_bits = self.read_bits(ADDR_DEX_OWNED, 19)
        seen_bits = self.read_bits(ADDR_DEX_SEEN, 19)
        dex_owned = sum(owned_bits[:151])
        dex_seen = sum(seen_bits[:151])

        # Event flags (bag-independent)
        event_flags_byte_oak = self.emu.read_u8(ADDR_OAK_PARCEL)    # 0xD74E
        event_flags_byte_dex = self.emu.read_u8(ADDR_POKEDEX_FLAG)  # 0xD74B

        event_got_oaks_parcel  = bool(event_flags_byte_oak & 0x02)  # flag 57, bit 1
        event_oak_got_parcel   = bool(event_flags_byte_oak & 0x01)  # flag 56, bit 0
        event_got_pokedex      = bool(event_flags_byte_dex & 0x20)  # flag 37, bit 5

        # Actual bag-item presence (0x46 = 70 = "Oak's Parcel")
        OAKS_PARCEL_ITEM_ID = 70
        parcel_in_bag = self._bag_contains(OAKS_PARCEL_ITEM_ID)

        # Derived state
        has_oaks_parcel  = parcel_in_bag
        parcel_delivered = event_oak_got_parcel and not parcel_in_bag
        cp06_complete    = event_got_pokedex and event_oak_got_parcel and not parcel_in_bag

        gym_leaders_defeated = [
            BADGE_NAMES[i] for i in range(8) if badges & (1 << i)
        ]

        return {
            "has_pokedex": event_got_pokedex,
            "has_oaks_parcel": has_oaks_parcel,
            "parcel_in_bag": parcel_in_bag,
            "event_got_oaks_parcel": event_got_oaks_parcel,
            "event_oak_got_parcel": event_oak_got_parcel,
            "parcel_delivered": parcel_delivered,
            "cp06_complete": cp06_complete,
            "pokedex_owned": dex_owned,
            "pokedex_seen": dex_seen,
            "badges": gym_leaders_defeated,
            "badge_count": len(gym_leaders_defeated),
        }

    # Hardcoded map_id → expected_tileset_id lookup (from Gen 1 pokered constants).
    # Verified against PokemonRed.gb map header bytes (byte 0 = tileset).
    # Covers all maps essential for forest/gate navigation.
    MAP_TILESET_LOOKUP: Dict[int, int] = {
        # Towns / Routes use OVERWORLD tileset
        0: 0,   # Pallet Town
        1: 0,   # Viridian City
        2: 0,   # Pewter City
        12: 0,  # Route 1
        13: 0,  # Route 2
        14: 0,  # Route 3
        15: 0,  # Route 4
        # Indoor buildings
        37: 1,  # REDS_HOUSE (Red's House 1F)
        38: 4,  # POKECENTER  (Red's House 2F uses Pokecenter tiles)
        39: 8,  # PORT        (Blue's House)
        40: 5,  # GYM         (Oak's Lab — header has GYM tileset)
        41: 6,  # HOUSE       (Viridian Pokecenter)
        42: 2,  # MART        (Viridian Mart)
        45: 7,  # GATE        (Viridian Gym — uses Gate tileset)
        47: 9,  # LAB         (Viridian Forest Gate South)
        49: 12, # SHIP_PORT   (Route 2 Gate North)
        50: 3,  # FOREST      (Viridian Forest South Gate — runtime outdoor tileset)
        51: 3,  # FOREST      (Viridian Forest outdoor)
        52: 10, # LOBBY       (Pewter Museum 2F)
        53: 10, # LOBBY       (Pewter Gym)
        57: 8,  # PORT        (Mt Moon 1F)
    }

    # Collision label names for each tileset ID
    _COLLISION_LABELS: Dict[int, str] = {
        0: "Overworld_Coll",
        1: "House_Coll",
        2: "Mart_Coll",
        3: "Forest_Coll",
        4: "Pokecenter_Coll",
        5: "Gym_Coll",
        6: "House_Coll",
        7: "Gate_Coll",
        8: "ShipPort_Coll",
        9: "Lab_Coll",
        10: "Lobby_Coll",
        11: "Ship_Coll",
        12: "ShipPort_Coll",
        13: "Cavern_Coll",
        14: "Cemetery_Coll",
        15: "Interior_Coll",
        16: "Plateau_Coll",
    }

    def read_forest_debug(self) -> Dict[str, Any]:
        """Read tile collision debug fields for forest/overworld navigation.

        Returns raw tile IDs from Gen 1 WRAM (wTilePlayerStandingOn,
        wTileInFrontOfPlayer) plus the front_coord, tileset info, and
        runtime collision passability.

        # collision_passable_by_runtime_table uses wTilesetCollisionPtr
        # (a pointer to a **list of passable tile IDs** terminated by $ff).
        # Gen 1's CheckTilePassable iterates this list — if tile_in_front
        # matches any entry, carry=clear (passable).  If $ff reached,
        # carry=set (blocked).  This matches the actual CheckTilePassable
        # in pokered/home/overworld.asm.
        """
        map_id = self.emu.read_u8(ADDR_MAP_ID)
        map_x = self.emu.read_u8(ADDR_MAP_X)
        map_y = self.emu.read_u8(ADDR_MAP_Y)
        facing_byte = self.emu.read_u8(ADDR_FACING)
        facing = FACING_NAMES.get(facing_byte, f"unknown(0x{facing_byte:02X})")

        tile_under = self.emu.read_u8(ADDR_TILE_STANDING_ON)
        tile_front = self.emu.read_u8(ADDR_TILE_IN_FRONT)
        tileset_id = self.emu.read_u8(ADDR_CUR_MAP_TILESET)
        map_name = MAP_NAMES.get(map_id, f"Unknown Map ({map_id})")
        tileset_name = TILESET_NAMES.get(tileset_id, f"unknown(0x{tileset_id:02X})")

        # Collision: look up passable tile list from ROM bank 0 by tileset_id.
        # This is RELIABLE (ROM bank 0 is always mapped) whereas wTilesetCollisionPtr
        # in WRAM is often stale or bank-switched.
        # Gen 1 CheckTilePassable iterates this list looking for tile_in_front.
        coll_addr = TILESET_COLLISION_ADDR.get(tileset_id, 0)
        coll_passable = None
        tile_front_coll_byte = None
        tile_under_coll_byte = None
        coll_tile_list = None
        if coll_addr and coll_addr != 0:
            try:
                max_scan = 64
                passable_tiles = []
                for off in range(max_scan):
                    tid = self.emu.read_u8(coll_addr + off)
                    if tid == 0xFF:
                        break
                    passable_tiles.append(tid)
                coll_passable = tile_front in passable_tiles
                # Raw bytes at the tile index (for comparison)
                tile_front_coll_byte = self.emu.read_u8(coll_addr + tile_front) if tile_front < max_scan else None
                tile_under_coll_byte = self.emu.read_u8(coll_addr + tile_under) if tile_under < max_scan else None
                coll_tile_list = [f"0x{t:02X}" for t in passable_tiles]
            except Exception:
                pass

        # Also read wTilesetCollisionPtr for comparison (may be stale)
        wram_coll_ptr = self.emu.read_u16(ADDR_TILESET_COLL_PTR)

        # Calculate front_coord the same way Gen 1 does screen->map
        dx, dy = 0, 0
        if facing == "down":
            dy = 1
        elif facing == "up":
            dy = -1
        elif facing == "left":
            dx = -1
        elif facing == "right":
            dx = 1
        front_coord = [map_x + dx, map_y + dy]

        # Warp data from wWarpEntries in WRAM
        num_warps = self.emu.read_u8(ADDR_NUM_WARPS)
        warp_under_player = None
        nearest_warps = []
        if num_warps and num_warps < 33:
            for i in range(num_warps):
                base = ADDR_WARP_ENTRIES + i * 4
                wy = self.emu.read_u8(base)      # Y coord of warp
                wx = self.emu.read_u8(base + 1)  # X coord of warp
                wid = self.emu.read_u8(base + 2) # warp ID (destination index)
                wmap = self.emu.read_u8(base + 3)# destination map ID
                entry = {"y": wy, "x": wx, "warp_id": wid, "dest_map_id": wmap}
                # Check if player is on this warp
                if wy == map_y and wx == map_x:
                    warp_under_player = entry
                # Check if within 2 tiles
                if abs(wy - map_y) <= 2 and abs(wx - map_x) <= 2:
                    nearest_warps.append(entry)
                # Otherwise not near enough to report

        # --- Sanity check: is map→tileset mapping consistent? ---
        expected_ts_id = self.MAP_TILESET_LOOKUP.get(map_id)
        expected_name = TILESET_NAMES.get(expected_ts_id, f"unknown({expected_ts_id})") if expected_ts_id is not None else None
        map_tileset_consistent: bool
        forest_debug_valid: bool
        gap: str | None = None

        if expected_ts_id is None:
            # Map not in our lookup table — can't judge consistency
            map_tileset_consistent = True  # unknown = not false-positive
            forest_debug_valid = True
        elif tileset_id == expected_ts_id:
            map_tileset_consistent = True
            forest_debug_valid = True
        else:
            # Tileset mismatch: likely a save/state warp transition inconsistency
            map_tileset_consistent = False
            forest_debug_valid = False
            gap = "map_tileset_parser_gap"

        # --- Adjacent tile oracle (read from wOverworldMap block buffer, decomposed to tile level) ---
        # Gen1 wOverworldMap at 0xC4A0 stores block IDs (2×2 metatiles).
        # wCurMapWidth/wCurMapHeight are in **blocks**, not tiles.
        # Player tile coords (map_x, map_y) must be halved to get block coords.
        # Each block encodes 4 tiles; read wTilesetBlocksPtr for block→tile decomposition.
        # MAP_BORDER=3 per pokered/constants/map_data_constants.asm.
        # offset = (MAP_BORDER + block_y) * (map_width_blocks + 2*MAP_BORDER) + (MAP_BORDER + block_x)
        adjacent = {}
        MAP_BORDER = 3
        walk_grid_tile_w = 0
        walk_grid_tile_h = 0
        try:
            map_width_blocks = self.emu.read_u8(ADDR_CUR_MAP_WIDTH)   # 0xD369, in blocks
            map_height_blocks = self.emu.read_u8(ADDR_CUR_MAP_HEIGHT)  # 0xD368, in blocks
            walk_grid_tile_w = map_width_blocks * 2   # 34 for Viridian Forest
            walk_grid_tile_h = map_height_blocks * 2  # 48 for Viridian Forest
            buf_width = map_width_blocks + 2 * MAP_BORDER  # = map_width_blocks + 6
            buf_base = ADDR_OVERWORLD_MAP_BASE  # 0xC4A0

            # Keep WRAM TilesetBlocksPtr for diagnostic only (stale after savestate)
            wram_blocks_ptr = self.emu.read_u16(ADDR_TILESET_BLOCKS_PTR)

            # Load block→tile decomposition from ROM Tilesets table (0xC7BE).
            # Gen 1 loads the Tilesets table at startup.  After savestate reload,
            # wTilesetBlocksPtr (0xD529) becomes stale, but the ROM data is always
            # correct.  The Tilesets table is at ROM file offset 0xC7BE, 24 entries
            # × 12 bytes, each entry: [bank(1), block_ptr(2), gfx_ptr(2), coll_ptr(2), ...].
            tileset_block_table: Optional[Dict[int, List[int]]] = None
            try:
                rom_path = getattr(self.emu, 'rom_path', None)
                if rom_path and os.path.isfile(rom_path):
                    with open(rom_path, 'rb') as _rom_f:
                        _rom_f.seek(0xC7BE + tileset_id * 12)
                        _hdr = _rom_f.read(12)
                        _bank = _hdr[0]
                        _ptr = struct.unpack('<H', _hdr[1:3])[0]
                        # Calculate file offset: bank*0x4000 + (ptr-0x4000) if ptr >= 0x4000
                        if _ptr >= 0x4000:
                            _file_off = _bank * 0x4000 + (_ptr - 0x4000)
                        else:
                            _file_off = _ptr
                        # Read the block table (each block = 4 bytes)
                        _MAX_BLOCKS = 280  # covers all Gen 1 tilesets
                        _rom_f.seek(_file_off)
                        _block_raw = _rom_f.read(_MAX_BLOCKS * 4)
                        _tbl: Dict[int, List[int]] = {}
                        for _bid in range(len(_block_raw) // 4):
                            _bo = _bid * 4
                            _tbl[_bid] = [
                                _block_raw[_bo],
                                _block_raw[_bo + 1],
                                _block_raw[_bo + 2],
                                _block_raw[_bo + 3],
                            ]
                        tileset_block_table = _tbl
            except Exception:
                tileset_block_table = None

            # Ensure passable_tiles is defined (may be unbound if coll_addr was None)
            passable_tiles_default: list = []
            if coll_tile_list:
                try:
                    passable_tiles_default = passable_tiles  # type: ignore
                except NameError:
                    pass
            local_passable_tiles = passable_tiles_default  # actual tile IDs (matches engine collision)

            def _block_at(self_obj, bx, by):
                """Read block ID at block-level coordinates (bx, by)."""
                off = (MAP_BORDER + by) * buf_width + (MAP_BORDER + bx)
                return self_obj.emu.read_u8(buf_base + off)

            def _decompose_tile(self_obj, block_id, subtile_x, subtile_y):
                """Decompose a 2×2 block into its 4 tile IDs using ROM tileset block data.
                
                Uses the ROM Tilesets table (loaded above).  Falls back to WRAM
                wTilesetBlocksPtr (stale after savestate) only for comparison.
                Each block = 4 bytes: [TL, TR, BL, BR] tile IDs.
                subtile_x=0, subtile_y=0 → TL, (1,0) → TR, (0,1) → BL, (1,1) → BR
                """
                if tileset_block_table is not None and block_id in tileset_block_table:
                    tiles = tileset_block_table[block_id]
                    tile_index = subtile_y * 2 + subtile_x
                    return tiles[tile_index]
                # Fallback: WRAM pointer (may be stale — for diagnostic only)
                if wram_blocks_ptr and wram_blocks_ptr != 0:
                    try:
                        entry = wram_blocks_ptr + block_id * 4
                        tile_index = subtile_y * 2 + subtile_x
                        return self_obj.emu.read_u8(entry + tile_index)
                    except Exception:
                        pass
                return None

            def _check_adjacent(dx, dy):
                """Check tile at (map_x+dx, map_y+dy) with full tile-level oracle."""
                tile_x = map_x + dx
                tile_y = map_y + dy
                # Bounds check against the walk grid (tile-level)
                if tile_x < 0 or tile_x >= walk_grid_tile_w or tile_y < 0 or tile_y >= walk_grid_tile_h:
                    return {
                        "coord": [tile_x, tile_y],
                        "in_bounds": False,
                        "classification": "out_of_walk_grid",
                        "passable": False,
                        "canary_allowed": False,
                    }
                # Downsample tile coords to block coords
                block_x = tile_x // 2
                block_y = tile_y // 2
                block_id = _block_at(self, block_x, block_y)
                # Subtile position within the block
                subtile_x = tile_x % 2
                subtile_y = tile_y % 2
                subtile_coord = [subtile_x, subtile_y]
                # Decompose block to actual tile ID
                actual_tile_id = _decompose_tile(self, block_id, subtile_x, subtile_y)
                # Tile-level collision passability
                tile_collision_passable = None
                if actual_tile_id is not None and local_passable_tiles:
                    tile_collision_passable = actual_tile_id in local_passable_tiles
                elif actual_tile_id is not None:
                    # Passable tiles list unavailable — conservative default
                    tile_collision_passable = False
                # Block-level heuristic (fallback only, not for canary decisions)
                block_passable_heuristic = (
                    (actual_tile_id is not None and tile_collision_passable)  # tile match
                    or (block_id in local_passable_tiles)  # block in tile list (weak heuristic)
                    or (block_id < 0x10)  # background ground
                )
                # Canary decision: ONLY tile-level passable
                canary_allowed = (tile_collision_passable is True)
                classification = (
                    "passable" if tile_collision_passable
                    else "blocked_by_tile_collision" if tile_collision_passable is False
                    else "tile_collision_unknown"
                )
                return {
                    "coord": [tile_x, tile_y],
                    "in_bounds": True,
                    "block_coord": [block_x, block_y],
                    "subtile_coord": subtile_coord,
                    "block_id": f"0x{block_id:02X}",
                    "block_id_raw": block_id,
                    "tile_id": f"0x{actual_tile_id:02X}" if actual_tile_id is not None else None,
                    "tile_id_raw": actual_tile_id,
                    "tile_collision_passable": tile_collision_passable,
                    "block_passable_heuristic": block_passable_heuristic,
                    "canary_allowed": canary_allowed,
                    "classification": classification,
                }

            directions = [
                ("up", 0, -1),
                ("down", 0, 1),
                ("left", -1, 0),
                ("right", 1, 0),
            ]
            for dname, dx, dy in directions:
                adjacent[dname] = _check_adjacent(dx, dy)
            # Override up-direction with the actual runtime tile_in_front for precision
            if adjacent.get("up", {}).get("in_bounds", False):
                adjacent["up"]["tile_in_front_raw"] = tile_front
                adjacent["up"]["tile_in_front"] = f"0x{tile_front:02X}"
                adjacent["up"]["tile_in_front_from_engine"] = True
                # Engine's collision result is the ground truth for facing direction
                adjacent["up"]["tile_collision_passable"] = coll_passable
                adjacent["up"]["tile_id_raw"] = tile_front
                adjacent["up"]["tile_id"] = f"0x{tile_front:02X}"
                adjacent["up"]["canary_allowed"] = (coll_passable is True)
                adjacent["up"]["classification"] = (
                    "passable" if coll_passable else "blocked_by_tile_collision"
                )

            # ================================================================
            # Engine screen tilemap adjacent oracle
            # Reads tiles from wTileMap (0xC3A0), the actual visible screen
            # tilemap that Gen 1's CheckTilePassable reads during movement.
            # This is the authoritative canary_allowed gate.
            #
            # Uses dynamic player_screen_tile_coord derived from the sprite's
            # actual pixel position (wSpritePlayerStateData1YPixels/XPixels),
            # NOT fixed (8,9).  The comment in the source says:
            #   "YPixels: Y screen position (in pixels, always 4 pixels above
            #    grid which makes sprites appear to be in the center of a tile)"
            # so the effective tile centre = (YPixels + 4) // 8.
            # ================================================================
            SCREEN_TILE_W = 20  # SCREEN_WIDTH (20 columns)
            ypix = self.emu.read_u8(ADDR_SPRITE_YPIXELS)
            xpix = self.emu.read_u8(ADDR_SPRITE_XPIXELS)
            player_screen_tile_coord = [(xpix // 8), (ypix + 4) // 8]
            # Adjacent offset: the player is 2 tiles tall and 2 tiles wide,
            # so the tile above/below/left/right is 2 tiles away in screen space.
            screen_adjacent_coords = {
                "up":    {"screen_coord": [player_screen_tile_coord[0], player_screen_tile_coord[1] - 2]},
                "down":  {"screen_coord": [player_screen_tile_coord[0], player_screen_tile_coord[1] + 2]},
                "left":  {"screen_coord": [player_screen_tile_coord[0] - 2, player_screen_tile_coord[1]]},
                "right": {"screen_coord": [player_screen_tile_coord[0] + 2, player_screen_tile_coord[1]]},
            }
            engine_screen_tilemap_adjacent = {}
            _passable = local_passable_tiles  # from ROM collision table (reliable)
            for dname in ["up", "down", "left", "right"]:
                info = screen_adjacent_coords[dname]
                sx, sy = info["screen_coord"]
                # Bounds: wTileMap is 20 cols × 18 rows
                if 0 <= sx < SCREEN_TILE_W and 0 <= sy < 18:
                    offset = sy * SCREEN_TILE_W + sx
                    tile_id = self.emu.read_u8(ADDR_W_TILE_MAP + offset)
                    tile_passable = tile_id in _passable if _passable else None
                    engine_screen_tilemap_adjacent[dname] = {
                        "screen_coord": [sx, sy],
                        "tile_id": f"0x{tile_id:02X}",
                        "tile_id_raw": tile_id,
                        "tile_collision_passable": tile_passable,
                        "canary_allowed": (tile_passable is True),
                    }
                else:
                    engine_screen_tilemap_adjacent[dname] = {
                        "screen_coord": [sx, sy],
                        "tile_id": None,
                        "tile_id_raw": None,
                        "tile_collision_passable": False,
                        "canary_allowed": False,
                        "classification": "out_of_screen_bounds",
                    }
            # Also override up-direction with engine's wTileInFrontOfPlayer
            # (but keep the dynamic calculation for the up entry too)
            engine_screen_tilemap_adjacent["up"]["tile_id"] = f"0x{tile_front:02X}"
            engine_screen_tilemap_adjacent["up"]["tile_id_raw"] = tile_front
            engine_screen_tilemap_adjacent["up"]["tile_collision_passable"] = coll_passable
            engine_screen_tilemap_adjacent["up"]["canary_allowed"] = (coll_passable is True)
        except Exception:
            adjacent = None
            engine_screen_tilemap_adjacent = None

        # Compute layered coordinate fields
        player_block_coord = [map_x // 2, map_y // 2] if map_x is not None else None
        coord_layers = {
            "coord_layer": "player_tile_coord",
            "player_coord": [map_x, map_y],
            "player_block_coord": player_block_coord,
            "map_blocks": [map_width_blocks, map_height_blocks] if 'map_width_blocks' in dir() and map_width_blocks else None,
            "walk_grid_tile_size": [walk_grid_tile_w, walk_grid_tile_h] if walk_grid_tile_w > 0 else None,
            "source_bst_tile_grid_size": [walk_grid_tile_w * 2, walk_grid_tile_h * 2] if walk_grid_tile_w > 0 else None,
            "viewport_buffer_border_blocks": MAP_BORDER,
            "viewport_buffer_size_blocks": [buf_width, map_height_blocks + 2 * MAP_BORDER] if 'map_height_blocks' in dir() and map_height_blocks else None,
            "tile_lookup_method": "wOverworldMap_block_buffer_tile_to_block_downsample",
            "full_map_lookup_used": False,
            "viewport_lookup_used": True,
        }

        return {
            "map": map_name,
            "map_id": map_id,
            "x": map_x,
            "y": map_y,
            "facing": facing,
            **coord_layers,
            "tile_under_player": f"0x{tile_under:02X}",
            "tile_under_player_raw": tile_under,
            "tile_in_front": f"0x{tile_front:02X}",
            "tile_in_front_raw": tile_front,
            "front_coord": front_coord,
            "tileset": tileset_name,
            "tileset_id": tileset_id,
            "collision_label": self._COLLISION_LABELS.get(tileset_id, f"unknown_collision({tileset_id})"),
            "collision_addr": f"0x{coll_addr:04X}" if coll_addr else None,
            "wram_coll_ptr": f"0x{wram_coll_ptr:04X}" if wram_coll_ptr else None,
            "coll_tile_list": coll_tile_list if coll_addr else None,
            "tile_front_coll_byte": f"0x{tile_front_coll_byte:02X}" if tile_front_coll_byte is not None else None,
            "tile_under_coll_byte": f"0x{tile_under_coll_byte:02X}" if tile_under_coll_byte is not None else None,
            "collision_passable_by_runtime_table": coll_passable,
            "num_warps": num_warps,
            "warp_under_player": warp_under_player,
            "nearest_warps": nearest_warps,
            # Raw fields for oracle sanity
            "map_id_raw": map_id,
            "map_name_from_id": map_name,
            "wCurMap_raw": map_id,
            "tileset_id_raw": tileset_id,
            "tileset_name_from_id": tileset_name,
            "map_tileset_expected_from_source": expected_name,
            "map_tileset_expected_id": expected_ts_id,
            "map_tileset_consistent": map_tileset_consistent,
            "forest_debug_valid": forest_debug_valid,
            "forest_debug_gap": gap,
            "wram_tileset_blocks_ptr": f"0x{wram_blocks_ptr:04X}" if wram_blocks_ptr else None,
            "tileset_block_table_loaded": tileset_block_table is not None,
            "map_width_blocks": map_width_blocks if 'map_width_blocks' in dir() and map_width_blocks else None,
            "map_height_blocks": map_height_blocks if 'map_height_blocks' in dir() and map_height_blocks else None,
            "player_screen_tile_coord": player_screen_tile_coord if 'player_screen_tile_coord' in dir() else None,
            "player_sprite_pixel_pos": [xpix, ypix] if 'xpix' in dir() and 'ypix' in dir() else None,
            "adjacent": adjacent,
            "oracle_source": "dynamic_player_screen_tilemap",
            "engine_screen_tilemap_adjacent": engine_screen_tilemap_adjacent,
        }

    def _bag_contains(self, item_id: int) -> bool:
        """Check if a given item_id exists anywhere in the bag."""
        count = self.emu.read_u8(ADDR_BAG_COUNT)
        count = min(count, 20)
        for i in range(count):
            raw_id = self.emu.read_u8(ADDR_BAG_ITEMS + i * 2)
            if raw_id == 0xFF:
                break
            if raw_id == item_id:
                return True
        return False


# Alias used by server.py and README examples
PokemonRedReader = RedBlueMemoryReader
