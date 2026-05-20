require('dotenv').config()

const express = require('express')
const bodyParser = require('body-parser')
const mineflayer = require('mineflayer')
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder')
const { Vec3 } = require('vec3')
const collectBlock = require('mineflayer-collectblock').plugin
const toolPlugin = require('mineflayer-tool').plugin

const BRIDGE_PORT = numberEnv('BRIDGE_PORT', 3001)
const MC_VERSION = optionalEnv('MC_VERSION')
const MC_AUTO_RECONNECT = booleanEnv('MC_AUTO_RECONNECT', true)
const MC_RECONNECT_DELAY_MS = numberEnv('MC_RECONNECT_DELAY_MS', 5000)
const ACTION_TIMEOUT_MS = numberEnv('ACTION_TIMEOUT_MS', 45000)
const RESOURCE_ACTION_TIMEOUT_MS = numberEnv('RESOURCE_ACTION_TIMEOUT_MS', 60000)
const NAVIGATION_TIMEOUT_MS = numberEnv('NAVIGATION_TIMEOUT_MS', 15000)
const MAX_BLOCK_CANDIDATES = numberEnv('MAX_BLOCK_CANDIDATES', 512)
const MAX_RESOURCE_CANDIDATES_EVALUATED = numberEnv('MAX_RESOURCE_CANDIDATES_EVALUATED', 512)
const RESOURCE_DEBUG_FULL_SCAN = booleanEnv('RESOURCE_DEBUG_FULL_SCAN', false)
const MAX_SCAN_RADIUS = numberEnv('MAX_SCAN_RADIUS', 32)
const MAX_EXCAVATION_STEPS = numberEnv('MAX_EXCAVATION_STEPS', 24)
const RESOURCE_CLOSE_RANGE_BLOCKS = numberEnv('RESOURCE_CLOSE_RANGE_BLOCKS', 6)
const CLOSE_RANGE_PATH_TIMEOUT_MS = numberEnv('CLOSE_RANGE_PATHFINDING_TIMEOUT_MS', numberEnv('CLOSE_RANGE_PATH_TIMEOUT_MS', 10000))
const ACQUIRE_TARGET_CACHE_TTL_MS = numberEnv('ACQUIRE_TARGET_CACHE_TTL_MS', 30000)
const DROP_COLLECTION_TIMEOUT_MS = numberEnv('DROP_COLLECTION_TIMEOUT_MS', 20000)
const DROP_COLLECTION_RADIUS = numberEnv('DROP_COLLECTION_RADIUS', 10)
const DROP_DIRECT_WALK_RADIUS = numberEnv('DROP_DIRECT_WALK_RADIUS', 5)
const CLOSE_DROP_PICKUP_RADIUS = numberEnv('CLOSE_DROP_PICKUP_RADIUS', 2.5)
const CLOSE_DROP_PICKUP_TIMEOUT_MS = numberEnv('CLOSE_DROP_PICKUP_TIMEOUT_MS', 8000)
const DROP_LOCAL_PATH_TIMEOUT_MS = numberEnv('DROP_LOCAL_PATH_TIMEOUT_MS', 5000)
const DROP_LOCAL_EXCAVATION_STEP_LIMIT = numberEnv('DROP_LOCAL_EXCAVATION_STEP_LIMIT', 3)
const LOCAL_EXCAVATION_STEP_LIMIT = numberEnv('LOCAL_EXCAVATION_STEP_LIMIT', 6)
const DROP_COLLECTABILITY_WINDOW = numberEnv('DROP_COLLECTABILITY_WINDOW', 8)
const MOODS = new Set(['neutral', 'happy', 'surprised', 'scared', 'focused', 'confused'])
const WOOD_BLOCK_NAMES = new Set([
  'oak_log',
  'birch_log',
  'spruce_log',
  'jungle_log',
  'acacia_log',
  'dark_oak_log',
  'mangrove_log',
  'cherry_log',
  'crimson_stem',
  'warped_stem'
])
const COLLECT_WOOD_RADIUS = 32
const COLLECT_WOOD_DEFAULT_COUNT = 4
const COLLECT_WOOD_MAX_COUNT = 16
const CRAFT_MAX_COUNT = 64
const CRAFT_TIMEOUT_MS = 30000
const MINE_STONE_DEFAULT_COUNT = 3
const MINE_STONE_MAX_COUNT = 16
const MINE_COAL_DEFAULT_COUNT = 4
const MINE_IRON_DEFAULT_COUNT = 3
const ORE_MINE_MAX_COUNT = 32
const MINE_STONE_MIN_HEALTH = 10
const SMELT_DEFAULT_COUNT = 3
const SMELT_MAX_COUNT = 64
const SMELT_IRON_MAX_COUNT = 32
const SMELT_TIMEOUT_PER_ITEM_MS = 12000
const LOOK_AROUND_DEFAULT_RADIUS = 12
const LOOK_AROUND_MAX_RADIUS = 32
const EXPLORE_DEFAULT_RADIUS = 16
const EXPLORE_MAX_RADIUS = 64
const EXPLORE_TIMEOUT_MS = 20000
const FLEE_DISTANCE = 14
const EAT_TIMEOUT_MS = 10000
const PLACE_CRAFTING_TABLE_TIMEOUT_MS = 8000
const PLACE_CRAFTING_TABLE_VERIFY_MS = 2500
const ACQUIRE_BLOCKS_DEFAULT_COUNT = 1
const ACQUIRE_BLOCKS_MAX_COUNT = 32
const ACQUIRE_BLOCKS_DEFAULT_RADIUS = 48
const ACQUIRE_BLOCKS_MIN_RADIUS = 8
const ACQUIRE_BLOCKS_MAX_RADIUS = 96
const ACQUIRE_BLOCKS_TIMEOUT_MS = 60000
const PATHFINDING_TIMEOUT_MS = numberEnv('PATHFINDING_TIMEOUT_MS', 15000)
const RESOURCE_PATHFINDING_TIMEOUT_MS = numberEnv('RESOURCE_PATHFINDING_TIMEOUT_MS', 12000)
const ACQUIRE_PATH_TIMEOUT_MS = RESOURCE_PATHFINDING_TIMEOUT_MS
const ACQUIRE_DIG_TIMEOUT_MS = 8000
const ACQUIRE_MAX_EXCAVATED_BLOCKS = 64
const ACQUIRE_MAX_STEPS = 24
const ACQUIRE_MAX_ATTEMPTS = 64
const ACQUIRE_ACCESS_MODES = new Set(['exposed', 'surface_first', 'safe_staircase'])
const PICKAXE_ITEM_NAMES = new Set([
  'wooden_pickaxe',
  'stone_pickaxe',
  'iron_pickaxe',
  'diamond_pickaxe',
  'netherite_pickaxe'
])
const PICKAXE_PRIORITY = [
  'netherite_pickaxe',
  'diamond_pickaxe',
  'iron_pickaxe',
  'stone_pickaxe',
  'wooden_pickaxe'
]
const AXE_PRIORITY = ['netherite_axe', 'diamond_axe', 'iron_axe', 'stone_axe', 'wooden_axe']
const SHOVEL_PRIORITY = ['netherite_shovel', 'diamond_shovel', 'iron_shovel', 'stone_shovel', 'wooden_shovel']
const SWORD_PRIORITY = ['netherite_sword', 'diamond_sword', 'iron_sword', 'stone_sword', 'wooden_sword', 'golden_sword']
const ARMOR_PRIORITY_BY_SLOT = {
  head:  ['netherite_helmet',     'diamond_helmet',     'iron_helmet',     'golden_helmet',     'leather_helmet',     'carved_pumpkin'],
  torso: ['netherite_chestplate', 'diamond_chestplate', 'iron_chestplate', 'golden_chestplate', 'leather_chestplate'],
  legs:  ['netherite_leggings',   'diamond_leggings',   'iron_leggings',   'golden_leggings',   'leather_leggings'],
  feet:  ['netherite_boots',      'diamond_boots',      'iron_boots',      'golden_boots',      'leather_boots'],
}
const DIAMOND_ARMOR_PIECES = [
  { name: 'diamond_chestplate', diamonds: 8, slot: 'torso' },
  { name: 'diamond_leggings',   diamonds: 7, slot: 'legs'  },
  { name: 'diamond_helmet',     diamonds: 5, slot: 'head'  },
  { name: 'diamond_boots',      diamonds: 4, slot: 'feet'  },
]
const IRON_ARMOR_PIECES = [
  { name: 'iron_chestplate', ingots: 8, slot: 'torso' },
  { name: 'iron_leggings',   ingots: 7, slot: 'legs'  },
  { name: 'iron_helmet',     ingots: 5, slot: 'head'  },
  { name: 'iron_boots',      ingots: 4, slot: 'feet'  },
]
const CRAFT_ITEM_OUTPUT_COUNTS = {
  torch: 4
}
const CRAFT_ITEM_SINGLE_COUNT = new Set([
  'shield', 'bucket', 'iron_pickaxe', 'iron_sword',
  'iron_helmet', 'iron_chestplate', 'iron_leggings', 'iron_boots', 'iron_armor'
])
const CRAFT_ITEM_REQUIREMENTS = {
  furnace: { table: true, materials: { cobblestone: 8 } },
  torch: { table: false, materials: { stick: 1 }, alternativeMaterials: [{ names: ['coal', 'charcoal'], count: 1, label: 'coal_or_charcoal' }] },
  chest: { table: true, materials: { planks: 8 } },
  shield: { table: true, materials: { iron_ingot: 1, planks: 6 } },
  bucket: { table: true, materials: { iron_ingot: 3 } },
  iron_pickaxe: { table: true, materials: { iron_ingot: 3, stick: 2 } },
  iron_sword: { table: true, materials: { iron_ingot: 2, stick: 1 } },
  iron_helmet: { table: true, materials: { iron_ingot: 5 } },
  iron_chestplate: { table: true, materials: { iron_ingot: 8 } },
  iron_leggings: { table: true, materials: { iron_ingot: 7 } },
  iron_boots: { table: true, materials: { iron_ingot: 4 } }
}
const CRAFT_ITEM_ALLOWED_ITEMS = new Set(Object.keys(CRAFT_ITEM_REQUIREMENTS).concat(['iron_armor']))
const SMELT_INPUTS = {
  raw_iron: 'iron_ingot',
  raw_gold: 'gold_ingot',
  raw_beef: 'cooked_beef',
  raw_porkchop: 'cooked_porkchop',
  raw_chicken: 'cooked_chicken',
  raw_mutton: 'cooked_mutton',
  raw_rabbit: 'cooked_rabbit',
  cod: 'cooked_cod',
  salmon: 'cooked_salmon',
  potato: 'baked_potato'
}
const SMELT_FUEL_ITEMS = new Set(['coal', 'charcoal'])
const EQUIP_TIMEOUT_MS = 5000
const PLACE_TIMEOUT_MS = 8000
const PLACE_VERIFY_MS = 2500
const PLACE_MODES = new Set(['nearby', 'floor', 'wall', 'forward', 'under_self', 'workspace'])
const PLACE_DIRECTIONS = new Set(['north', 'south', 'east', 'west', 'up', 'down', 'forward', 'back', 'left', 'right'])
const PLACE_BLOCK_ALLOWED_ITEMS = new Set([
  'dirt', 'cobblestone', 'stone', 'crafting_table', 'furnace', 'torch', 'chest', 'obsidian'
  // Planks matched by _planks suffix; beds matched by _bed suffix
])
const WATER_MODES = new Set(['nearby', 'downward_safety', 'portal_casting', 'mlg'])
const LAVA_SAFE_MODES = new Set(['portal_casting', 'controlled_source'])
const LAVA_MIN_SAFE_DISTANCE = 3
const BED_ITEM_NAMES = new Set([
  'white_bed', 'orange_bed', 'magenta_bed', 'light_blue_bed', 'yellow_bed', 'lime_bed',
  'pink_bed', 'gray_bed', 'light_gray_bed', 'cyan_bed', 'purple_bed', 'blue_bed',
  'brown_bed', 'green_bed', 'red_bed', 'black_bed'
])
const WOOL_COLORS = ['white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink', 'gray', 'light_gray', 'cyan', 'purple', 'blue', 'brown', 'green', 'red', 'black']
const SLEEP_NIGHT_THRESHOLD          = 12300   // timeOfDay >= this → dark enough to sleep
const BED_BOMB_SAFE_DISTANCE         = 8       // blocks to retreat before activating bed bomb
const SLEEP_TIMEOUT_MS               = 35000   // night skip can take up to ~30 s
const LAVA_POOL_SEARCH_RADIUS_DEFAULT = 48
const LAVA_POOL_SEARCH_RADIUS_MAX    = 128
const WATER_COLLECT_RADIUS           = 32
const LAVA_COLLECT_RADIUS            = 24
const OBSIDIAN_DIG_TIMEOUT_MS        = 12000
const PORTAL_WAIT_TIMEOUT_MS         = 15000
const CAST_PORTAL_MAX_STEPS          = 32
const BARTER_WAIT_MS                 = 8000
const BARTER_SEARCH_RADIUS           = 16
const NETHER_FORTRESS_SEARCH_RADIUS  = 96
const NETHER_NAVIGATE_TIMEOUT_MS     = 20000
const COLLECT_BLAZE_ROD_DEFAULT_COUNT = 6
const COLLECT_BLAZE_ROD_MAX_COUNT    = 12
const NETHER_RETREAT_DISTANCE        = 20
const EYE_THROW_WAIT_MS              = 2500
const STRONGHOLD_STEP_DISTANCE       = 64
const STRONGHOLD_SCAN_RADIUS         = 32
const STRONGHOLD_STAIRCASE_MAX_STEPS = 48
const END_PORTAL_SEARCH_RADIUS       = 128
const ACTIVATE_PORTAL_TIMEOUT_MS     = 8000
const END_PORTAL_WAIT_MS             = 5000
const END_SAFE_LANDING_RADIUS        = 32
const END_CRYSTAL_SCAN_RADIUS        = 128
const END_CRYSTAL_DANGER_RADIUS      = 8
const END_CRYSTAL_LOW_REACH_Y        = 8
const END_CRYSTAL_MAX_PILLAR_HEIGHT  = 12
const END_PHASE_TIMEOUT_MS           = 12000
const END_DRAGON_ATTACK_MS           = 9000
const END_DRAGON_BOW_RANGE           = 96
const END_PERCH_RADIUS               = 18
const END_EXIT_PORTAL_RADIUS         = 96
const ENDERMAN_AVOID_RADIUS          = 12
const END_VOID_MIN_Y                 = 4
const DEATH_ITEM_DESPAWN_SECONDS     = 300
const DEATH_RECENT_SECONDS           = 300
const RESPAWN_RECENT_SECONDS         = 60
const DEATH_RECOVERY_MAX_FAILURES    = 2
const DEATH_RECOVERY_PICKUP_RADIUS   = 16
// Portal frame layout (14 blocks, corners included): [dx, dy, refDx, refDy, faceX, faceY, faceZ]
// Oriented in XY plane (portal faces ±Z); bot stands at z-1.
const PORTAL_FRAME_OFFSETS = [
  [0, 0, 0, -1, 0, 1, 0], [1, 0, 0, -1, 0, 1, 0], [2, 0, 0, -1, 0, 1, 0], [3, 0, 0, -1, 0, 1, 0],
  [0, 1, 0, -1, 0, 1, 0], [0, 2, 0, -1, 0, 1, 0], [0, 3, 0, -1, 0, 1, 0],
  [3, 1, 0, -1, 0, 1, 0], [3, 2, 0, -1, 0, 1, 0], [3, 3, 0, -1, 0, 1, 0],
  [0, 4, 0, -1, 0, 1, 0], [3, 4, 0, -1, 0, 1, 0],
  [1, 4, -1, 0, 1, 0, 0], [2, 4, -1, 0, 1, 0, 0],
]
const BOAT_ITEM_NAMES = new Set([
  'oak_boat', 'birch_boat', 'spruce_boat', 'jungle_boat', 'acacia_boat', 'dark_oak_boat',
  'mangrove_boat', 'cherry_boat', 'bamboo_raft'
])
const MOVEMENT_PATH_TIMEOUT_MS  = 20000
const STAIRCASE_DIG_TIMEOUT_MS  = 8000
const STAIRCASE_STEP_TIMEOUT_MS = 8000
const PILLAR_STEP_TIMEOUT_MS    = 3000
const BRIDGE_STEP_TIMEOUT_MS    = 3000
const WORKSPACE_PATH_TIMEOUT_MS = 20000
const WORKSPACE_DEFAULT_RADIUS  = 16
const WORKSPACE_MAX_RADIUS      = 64
const WORKSPACE_PURPOSES        = new Set(['crafting', 'smelting', 'storage', 'general'])
const STATION_USE_RADIUS        = 6
const STATION_SCAN_RADIUS       = 24
const STATION_APPROACH_RADIUS   = 3
const STATION_BLOCK_TYPES       = new Set(['crafting_table', 'furnace', 'chest'])
const STATION_NUISANCE_BLOCK_NAMES = new Set([
  'short_grass', 'grass', 'tall_grass', 'fern', 'large_fern',
  'dead_bush', 'moss_carpet', 'vine', 'lily_pad', 'seagrass', 'kelp', 'kelp_plant',
  'oak_leaves', 'spruce_leaves', 'birch_leaves', 'jungle_leaves',
  'acacia_leaves', 'dark_oak_leaves', 'mangrove_leaves', 'cherry_leaves',
  'azalea_leaves', 'flowering_azalea_leaves',
])
const STATION_NUISANCE_MAX_DIG  = 3
const PILLAR_MAX_HEIGHT         = 16
const BRIDGE_MAX_LENGTH         = 32
const STAIRCASE_MAX_STEPS       = 32
const STAIRCASE_DIRS = new Set([
  'north', 'south', 'east', 'west',
  'up_to_surface', 'down', 'toward_target', 'down_to_target'
])
const BRIDGE_DIRS = new Set(['forward', 'north', 'south', 'east', 'west'])
const PLACE_IN_DIR_DIRS = new Set([
  'north', 'south', 'east', 'west', 'forward', 'back', 'left', 'right', 'up', 'down'
])
const PILLAR_BLOCK_NAMES  = ['cobblestone', 'dirt', 'stone', 'cobbled_deepslate']
const BRIDGE_BLOCK_NAMES  = ['cobblestone', 'dirt', 'stone', 'cobbled_deepslate']
const CONTAINER_TIMEOUT_MS = 10000
const CHEST_BLOCK_NAMES   = ['chest', 'trapped_chest', 'barrel']
const EQUIP_ARMOR_MODES   = new Set(['best', 'gold', 'iron', 'diamond', 'netherite', 'leather'])
const LOOT_PRIORITIES     = new Set(['fortress', 'stronghold', 'village', 'general'])
const DROP_CRITICAL_ITEMS = new Set([
  'diamond', 'diamond_pickaxe', 'diamond_sword', 'diamond_helmet', 'diamond_chestplate',
  'diamond_leggings', 'diamond_boots', 'ender_pearl', 'blaze_rod', 'blaze_powder',
  'ender_eye', 'iron_pickaxe', 'iron_sword', 'netherite_ingot', 'totem_of_undying',
  'enchanted_book', 'elytra', 'flint_and_steel', 'water_bucket', 'lava_bucket',
  'crafting_table', 'furnace'
])
const DEPOSIT_BLOCKED_ITEMS = new Set([
  'diamond', 'diamond_pickaxe', 'diamond_sword', 'ender_pearl', 'blaze_rod',
  'blaze_powder', 'ender_eye', 'iron_pickaxe', 'iron_sword', 'wooden_pickaxe',
  'stone_pickaxe', 'crafting_table', 'furnace', 'water_bucket', 'lava_bucket',
  'bow', 'flint_and_steel', 'shield'
])
const LOOT_TAKE_SETS = {
  fortress: new Set([
    'blaze_rod', 'iron_ingot', 'gold_ingot', 'saddle', 'bow', 'arrow',
    'iron_helmet', 'iron_chestplate', 'iron_leggings', 'iron_boots',
    'golden_helmet', 'golden_chestplate', 'golden_leggings', 'golden_boots',
    'apple', 'bread', 'golden_apple', 'enchanted_golden_apple', 'iron_sword', 'iron_pickaxe'
  ]),
  stronghold: new Set([
    'iron_ingot', 'gold_ingot', 'obsidian', 'ender_pearl', 'ender_eye',
    'iron_pickaxe', 'iron_sword', 'diamond', 'apple', 'bread', 'golden_apple',
    'bow', 'arrow', 'enchanted_book', 'iron_chestplate', 'iron_leggings', 'iron_helmet', 'iron_boots'
  ]),
  village: new Set([
    'bread', 'apple', 'iron_ingot', 'gold_ingot', 'emerald', 'carrot',
    'potato', 'cooked_beef', 'cooked_porkchop', 'wheat', 'saddle',
    'iron_pickaxe', 'iron_sword', 'iron_chestplate'
  ]),
  general: new Set([
    'diamond', 'iron_ingot', 'gold_ingot', 'ender_pearl', 'blaze_rod', 'obsidian',
    'iron_sword', 'iron_pickaxe', 'bow', 'arrow', 'golden_apple', 'enchanted_golden_apple',
    'apple', 'bread', 'cooked_beef', 'cooked_porkchop', 'saddle',
    'iron_chestplate', 'iron_leggings', 'iron_helmet', 'iron_boots',
    'golden_helmet', 'golden_chestplate', 'golden_leggings', 'golden_boots',
    'enchanted_book', 'experience_bottle', 'flint_and_steel'
  ])
}
const PASSIVE_MOB_NAMES = new Set([
  'cow', 'pig', 'sheep', 'chicken', 'rabbit', 'horse', 'donkey', 'mule', 'llama',
  'mooshroom', 'squid', 'bat', 'cod', 'salmon', 'tropical_fish', 'pufferfish',
  'turtle', 'dolphin', 'fox', 'bee', 'axolotl', 'goat', 'frog', 'tadpole',
  'allay', 'sniffer', 'armadillo', 'camel'
])
const FOOD_MOB_NAMES = new Set(['cow', 'pig', 'sheep', 'chicken', 'rabbit'])
const SCAN_EXTRA_BLOCKS = new Set([
  'nether_bricks', 'nether_brick_fence', 'nether_brick_stairs',
  'end_portal_frame', 'stone_bricks', 'mossy_stone_bricks', 'cracked_stone_bricks',
  'mossy_cobblestone', 'spawner',
  'hay_block', 'dirt_path', 'carved_pumpkin',
  'dark_oak_planks', 'dark_oak_log',
  'prismarine', 'prismarine_bricks', 'dark_prismarine', 'sea_lantern',
  'purpur_block', 'purpur_pillar', 'end_stone_bricks',
  'blackstone', 'basalt', 'polished_blackstone_bricks', 'gilded_blackstone',
  'sandstone', 'orange_terracotta', 'blue_terracotta',
  'netherrack', 'soul_sand', 'soul_soil', 'glowstone', 'shroomlight',
  'crying_obsidian', 'magma_block', 'obsidian'
])
const STRUCTURE_INDICATOR_BLOCKS = {
  nether_fortress:  ['nether_bricks', 'nether_brick_fence', 'nether_brick_stairs'],
  stronghold:       ['end_portal_frame', 'stone_bricks', 'mossy_stone_bricks', 'cracked_stone_bricks'],
  village:          ['hay_block', 'dirt_path', 'carved_pumpkin'],
  dungeon:          ['spawner', 'mossy_cobblestone'],
  desert_temple:    ['orange_terracotta', 'blue_terracotta'],
  woodland_mansion: ['dark_oak_planks', 'dark_oak_log'],
  ocean_monument:   ['prismarine', 'prismarine_bricks', 'sea_lantern'],
  end_city:         ['purpur_block', 'purpur_pillar', 'end_stone_bricks'],
  bastion_remnant:  ['blackstone', 'polished_blackstone_bricks', 'gilded_blackstone'],
}
const VALID_WAYPOINT_KINDS = new Set([
  'home', 'workspace', 'surface', 'crafting_area', 'furnace_area', 'furnace', 'mine_entrance', 'last_surface',
  'nether_portal_overworld', 'nether_portal_nether', 'fortress',
  'blaze_spawner', 'stronghold', 'end_portal_room', 'death_location', 'lava_pool', 'general'
])
const ACQUIRE_ALLOWED_TARGETS = new Set([
  ...WOOD_BLOCK_NAMES,
  'stone',
  'cobblestone',
  'deepslate',
  'coal_ore',
  'deepslate_coal_ore',
  'iron_ore',
  'deepslate_iron_ore',
  'copper_ore',
  'deepslate_copper_ore',
  'dirt',
  'grass_block',
  'sand',
  'gravel'
])
const ACQUIRE_DROPS = {
  stone: ['cobblestone'],
  cobblestone: ['cobblestone'],
  deepslate: ['cobbled_deepslate'],
  coal_ore: ['coal'],
  deepslate_coal_ore: ['coal'],
  iron_ore: ['raw_iron'],
  deepslate_iron_ore: ['raw_iron'],
  copper_ore: ['raw_copper'],
  deepslate_copper_ore: ['raw_copper'],
  grass_block: ['dirt']
}
const SOFT_EXPOSURE_BLOCK_NAMES = new Set([
  'dirt',
  'grass_block',
  'podzol',
  'mycelium',
  'coarse_dirt',
  'rooted_dirt',
  'snow',
  'snow_block'
])
// Blocks that are safe to tunnel through as access paths (not soft, but not protected or dangerous).
const HARD_EXCAVATE_BLOCK_NAMES = new Set([
  'stone', 'granite', 'diorite', 'andesite', 'tuff', 'calcite',
  'deepslate', 'cobbled_deepslate', 'smooth_basalt', 'basalt',
  'netherrack', 'blackstone', 'gravel', 'sand', 'sandstone',
])
const DROP_LOCAL_EXCAVATION_BLOCK_NAMES = new Set([
  'stone',
  'cobblestone',
  'dirt',
  'gravel',
  'moss_block',
  'andesite',
  'diorite',
  'granite',
  'deepslate'
])
const NEVER_MINE_BLOCK_NAMES = new Set([
  'crafting_table',
  'chest',
  'trapped_chest',
  'barrel',
  'furnace',
  'blast_furnace',
  'smoker',
  'bed',
  'white_bed',
  'orange_bed',
  'magenta_bed',
  'light_blue_bed',
  'yellow_bed',
  'lime_bed',
  'pink_bed',
  'gray_bed',
  'light_gray_bed',
  'cyan_bed',
  'purple_bed',
  'blue_bed',
  'brown_bed',
  'green_bed',
  'red_bed',
  'black_bed'
])
const MINE_FACE_OFFSETS = [
  new Vec3(1, 0, 0),
  new Vec3(-1, 0, 0),
  new Vec3(0, 1, 0),
  new Vec3(0, -1, 0),
  new Vec3(0, 0, 1),
  new Vec3(0, 0, -1)
]
const HOSTILE_ENTITY_NAMES = new Set([
  // Overworld
  'zombie', 'skeleton', 'creeper', 'spider', 'cave_spider', 'enderman', 'witch',
  'drowned', 'husk', 'stray', 'slime', 'phantom', 'pillager', 'ravager',
  'vindicator', 'evoker', 'vex', 'silverfish', 'endermite', 'guardian', 'elder_guardian',
  // Nether
  'blaze', 'ghast', 'wither_skeleton', 'piglin_brute', 'hoglin', 'zoglin', 'magma_cube',
  // End / other
  'shulker', 'warden'
])
const COMBAT_TIMEOUT_MS       = 15000
const ATTACK_DURATION_MS      = 8000
const KITE_DURATION_MS        = 10000
const BOW_CHARGE_MS           = 1200
const SHIELD_HOLD_MS          = 3000
const PEARL_TIMEOUT_MS        = 5000
const CREEPER_DANGER_RADIUS   = 5
const LOW_HEALTH_THRESHOLD    = 8
const COMBAT_RETREAT_DISTANCE = 18
const ENDER_PEARL_MODES       = new Set(['forward', 'escape', 'across_gap', 'toward_target'])
const FOOD_ITEM_NAMES = new Set([
  'apple',
  'bread',
  'cooked_beef',
  'cooked_porkchop',
  'cooked_chicken',
  'cooked_mutton',
  'cooked_rabbit',
  'baked_potato',
  'carrot',
  'beef',
  'porkchop',
  'chicken',
  'mutton'
])
const LOG_TO_PLANK = {
  oak_log: 'oak_planks',
  birch_log: 'birch_planks',
  spruce_log: 'spruce_planks',
  jungle_log: 'jungle_planks',
  acacia_log: 'acacia_planks',
  dark_oak_log: 'dark_oak_planks',
  mangrove_log: 'mangrove_planks',
  cherry_log: 'cherry_planks',
  crimson_stem: 'crimson_planks',
  warped_stem: 'warped_planks'
}
const PLANK_ITEM_NAMES = new Set(Object.values(LOG_TO_PLANK))
const PLACEMENT_OFFSETS = [
  new Vec3(1, 0, 0),
  new Vec3(-1, 0, 0),
  new Vec3(0, 0, 1),
  new Vec3(0, 0, -1),
  new Vec3(1, 0, 1),
  new Vec3(1, 0, -1),
  new Vec3(-1, 0, 1),
  new Vec3(-1, 0, -1)
]
const ACTIONS = new Set([
  'status',
  'say',
  'look_around',
  'explore_nearby',
  'look_at_player',
  'follow_player',
  'come_here',
  'stop',
  'jump',
  'set_vtuber_mood',
  'acquire_blocks',
  'navigate_to_block_type',
  'collect_wood',
  'craft_planks',
  'craft_sticks',
  'craft_crafting_table',
  'place_crafting_table',
  'craft_item',
  'craft_furnace',
  'craft_torches',
  'craft_chest',
  'craft_shield',
  'craft_bucket',
  'craft_iron_pickaxe',
  'craft_iron_sword',
  'craft_iron_armor',
  'place_block',
  'place_water',
  'place_lava',
  'place_bed',
  'place_boat',
  'place_chest',
  'place_furnace',
  'place_torch',
  'craft_wooden_pickaxe',
  'mine_stone',
  'mine_coal',
  'mine_iron_ore',
  'craft_stone_pickaxe',
  'craft_blaze_powder',
  'craft_diamond_pickaxe',
  'craft_diamond_sword',
  'craft_diamond_armor',
  'equip_best_armor',
  'equip_best_tool',
  'equip_best_weapon',
  'find_safe_workspace',
  'setup_workspace',
  'approach_station',
  'dig_staircase',
  'return_to_surface',
  'pillar_up',
  'bridge_gap',
  'place_block_in_direction',
  'mlg_water_bucket',
  'enter_boat',
  'exit_boat',
  'set_sneak',
  'set_sprint',
  'recover_position',
  'check_inventory',
  'check_time_of_day',
  'check_light_level',
  'check_biome',
  'scan_for_hostiles',
  'scan_for_passive_mobs',
  'scan_for_chests',
  'scan_for_specific_block',
  'debug_find_blocks',
  'debug_collect_drops',
  'scan_for_liquids',
  'scan_for_structures',
  'scan_workspace',
  'drop_item',
  'equip_armor',
  'equip_tool',
  'select_hotbar_slot',
  'open_chest',
  'loot_chest',
  'deposit_items',
  'withdraw_items',
  'mark_waypoint',
  'list_waypoints',
  'return_to_waypoint',
  'return_to_position',
  'set_home_position',
  'recover_death_items',
  'abandon_death_recovery',
  'return_to_spawn_or_home',
  'attack_mob',
  'attack_nearest_hostile',
  'retreat_from_combat',
  'block_with_shield',
  'shoot_bow',
  'charge_bow',
  'deflect_ghast_fireball',
  'kite_mob',
  'throw_ender_pearl',
  'kill_passive_mob',
  'kill_blaze',
  'kill_enderman',
  'flee',
  'eat_food',
  'craft_bed',
  'sleep_if_possible',
  'set_spawn_with_bed',
  'use_bed_bomb',
  'avoid_bed_explosion',
  'find_lava_pool',
  'collect_water',
  'collect_lava',
  'collect_obsidian',
  'smelt_item',
  'smelt_iron',
  'build_nether_portal',
  'cast_nether_portal',
  'craft_flint_and_steel',
  'light_nether_portal',
  'enter_nether',
  'return_to_portal',
  'equip_gold_armor',
  'avoid_opening_chests_near_piglins',
  'barter_with_piglins',
  'find_nether_fortress',
  'navigate_nether_safely',
  'collect_blaze_rods',
  'retreat_from_nether_danger',
  'leave_nether',
  'craft_eyes_of_ender',
  'throw_eye_of_ender',
  'locate_stronghold_step',
  'dig_staircase_to_stronghold',
  'scan_for_end_portal_room',
  'activate_end_portal',
  'enter_end',
  'end_safe_landing',
  'equip_pumpkin_head',
  'look_down_around_endermen',
  'scan_end_crystals',
  'destroy_end_crystal',
  'destroy_caged_end_crystal',
  'destroy_nearby_end_crystals',
  'attack_perched_dragon',
  'attack_dragon_with_bow',
  'dragon_phase_crystals',
  'dragon_phase_circle',
  'dragon_phase_perch',
  'fight_dragon_phase',
  'return_to_overworld_via_end_portal',
])

const ACTION_STATUS_PRIORITY = {
  planned: 0,
  stub: 1,
  partial: 2,
  implemented: 3
}

const NODE_ACTIONS_HIDDEN_FROM_LLM = new Set([
  'set_vtuber_mood',
  'use_bed_bomb',
  'avoid_bed_explosion'
])

const ACTION_ROADMAP_METADATA = [
  { name: 'craft_item', status: 'planned', category: 'crafting' },
  { name: 'craft_furnace', status: 'planned', category: 'crafting' },
  { name: 'craft_torches', status: 'planned', category: 'crafting' },
  { name: 'craft_chest', status: 'planned', category: 'crafting' },
  { name: 'craft_shield', status: 'planned', category: 'crafting' },
  { name: 'craft_bucket', status: 'planned', category: 'crafting' },
  { name: 'craft_iron_pickaxe', status: 'planned', category: 'crafting' },
  { name: 'craft_iron_sword', status: 'planned', category: 'crafting' },
  { name: 'craft_iron_armor', status: 'planned', category: 'crafting' },
  { name: 'craft_bow', status: 'planned', category: 'crafting' },
  { name: 'craft_arrows', status: 'planned', category: 'crafting' },
  { name: 'craft_boat', status: 'planned', category: 'crafting' },
  { name: 'mine_coal', status: 'planned', category: 'resource' },
  { name: 'mine_iron_ore', status: 'planned', category: 'resource' },
  { name: 'mine_diamond_ore', status: 'planned', category: 'resource' },
  { name: 'mine_redstone', status: 'planned', category: 'resource' },
  { name: 'mine_gold_ore', status: 'planned', category: 'resource' },
  { name: 'mine_gravel', status: 'planned', category: 'resource' },
  { name: 'collect_flint', status: 'planned', category: 'resource' },
  { name: 'collect_sand', status: 'planned', category: 'resource' },
  { name: 'collect_food', status: 'planned', category: 'resource' },
  { name: 'smelt_item', status: 'planned', category: 'smelting' },
  { name: 'smelt_iron', status: 'planned', category: 'smelting' },
  { name: 'smelt_food', status: 'planned', category: 'smelting' },
  { name: 'smelt_gold', status: 'planned', category: 'smelting' },
  { name: 'build_emergency_shelter', status: 'planned', category: 'survival' },
  { name: 'avoid_hazard', status: 'planned', category: 'survival' },
  { name: 'escape_liquid', status: 'planned', category: 'survival' },
  { name: 'handle_stuck', status: 'planned', category: 'survival' },
  { name: 'find_bastion_or_piglins', status: 'planned', category: 'nether_progression' },
  { name: 'collect_ender_pearls', status: 'planned', category: 'nether_progression' },
  { name: 'finish_dragon_fight', status: 'planned', category: 'end_fight' }
]

function actionCategory(name) {
  if ([
    'status', 'say', 'look_around', 'explore_nearby', 'look_at_player', 'follow_player',
    'come_here', 'stop', 'jump', 'set_vtuber_mood', 'recover_position',
    'return_to_surface', 'mark_waypoint', 'list_waypoints', 'return_to_waypoint',
    'return_to_position', 'set_home_position',
    'navigate_to_block_type', 'acquire_blocks'
  ].includes(name)) return 'core_control'
  if (name.startsWith('craft_')) return 'crafting'
  if (name.startsWith('place_')) return 'placement'
  if (name.startsWith('scan_') || name.startsWith('check_')) return 'sensing'
  if (name.startsWith('equip_')) return 'equipment'
  if (name.startsWith('attack_') || name.startsWith('kill_') || [
    'retreat_from_combat', 'block_with_shield', 'shoot_bow', 'charge_bow',
    'deflect_ghast_fireball', 'kite_mob', 'throw_ender_pearl'
  ].includes(name)) return 'combat'
  if ([
    'find_safe_workspace', 'setup_workspace', 'approach_station', 'dig_staircase', 'pillar_up', 'bridge_gap',
    'place_block_in_direction', 'mlg_water_bucket', 'enter_boat', 'exit_boat',
    'set_sneak', 'set_sprint'
  ].includes(name)) return 'movement'
  if ([
    'collect_wood', 'mine_stone', 'collect_water', 'collect_lava', 'collect_obsidian'
  ].includes(name)) return 'resource'
  if ([
    'drop_item', 'select_hotbar_slot', 'open_chest', 'loot_chest', 'deposit_items',
    'withdraw_items'
  ].includes(name)) return 'inventory'
  if ([
    'recover_death_items', 'abandon_death_recovery', 'return_to_spawn_or_home'
  ].includes(name)) return 'death_recovery'
  if ([
    'flee', 'eat_food', 'sleep_if_possible', 'set_spawn_with_bed',
    'use_bed_bomb', 'avoid_bed_explosion'
  ].includes(name)) return 'survival'
  if ([
    'find_lava_pool', 'build_nether_portal', 'cast_nether_portal',
    'craft_flint_and_steel', 'light_nether_portal', 'enter_nether', 'return_to_portal'
  ].includes(name)) return 'nether_portal'
  if ([
    'equip_gold_armor', 'avoid_opening_chests_near_piglins', 'barter_with_piglins',
    'find_nether_fortress', 'navigate_nether_safely', 'collect_blaze_rods',
    'retreat_from_nether_danger', 'leave_nether'
  ].includes(name)) return 'nether_progression'
  if ([
    'craft_eyes_of_ender', 'throw_eye_of_ender', 'locate_stronghold_step',
    'dig_staircase_to_stronghold', 'scan_for_end_portal_room',
    'activate_end_portal', 'enter_end'
  ].includes(name)) return 'stronghold_end'
  if ([
    'end_safe_landing', 'equip_pumpkin_head', 'look_down_around_endermen',
    'scan_end_crystals', 'destroy_end_crystal', 'destroy_caged_end_crystal',
    'destroy_nearby_end_crystals', 'attack_perched_dragon', 'attack_dragon_with_bow',
    'dragon_phase_crystals', 'dragon_phase_circle', 'dragon_phase_perch',
    'fight_dragon_phase', 'return_to_overworld_via_end_portal'
  ].includes(name)) return 'end_fight'
  return 'core'
}

function buildActionsMetadata() {
  const definitions = [
    ...Array.from(ACTIONS).map(name => ({
      name,
      status: 'implemented',
      category: actionCategory(name),
      implemented: true,
      exposes_to_llm: !NODE_ACTIONS_HIDDEN_FROM_LLM.has(name)
    })),
    ...ACTION_ROADMAP_METADATA.map(action => ({
      ...action,
      implemented: false,
      exposes_to_llm: false
    }))
  ]

  const counts = new Map()
  const merged = new Map()

  for (const definition of definitions) {
    const name = definition.name
    if (!name) continue
    counts.set(name, (counts.get(name) || 0) + 1)
    const status = ACTION_STATUS_PRIORITY[definition.status] === undefined ? 'planned' : definition.status
    const normalized = {
      name,
      status,
      category: definition.category || 'uncategorized',
      implemented: status === 'implemented' || status === 'partial',
      exposes_to_llm: Boolean(definition.exposes_to_llm) && (status === 'implemented' || status === 'partial'),
      args_schema: actionArgsSchemaForMetadata(name)
    }
    const existing = merged.get(name)
    if (!existing || ACTION_STATUS_PRIORITY[normalized.status] > ACTION_STATUS_PRIORITY[existing.status]) {
      merged.set(name, normalized)
    } else if (existing && existing.category === 'core' && normalized.category !== 'core') {
      merged.set(name, { ...existing, category: normalized.category })
    }
  }

  const actions = Array.from(merged.values()).sort((a, b) => a.name.localeCompare(b.name))
  const summary = { total: actions.length, implemented: 0, partial: 0, stub: 0, planned: 0 }
  for (const action of actions) {
    summary[action.status] = (summary[action.status] || 0) + 1
  }
  const duplicates_removed = Array.from(counts.entries())
    .filter(([, count]) => count > 1)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name))

  return { ok: true, summary, actions, duplicates_removed }
}

const TOP_LEVEL_ACTION_REQUEST_KEYS = new Set(['action', 'args', 'speech', 'reason'])
const NO_ARG_HARMLESS_KEYS = new Set(['count'])
const ACTION_ARG_SCHEMAS = createActionArgSchemas()

function createActionArgSchemas() {
  const schemas = {}
  const noArgActions = [
    'status', 'stop', 'jump',
    'craft_furnace', 'craft_chest', 'craft_shield', 'craft_bucket',
    'craft_iron_pickaxe', 'craft_iron_sword', 'craft_iron_armor',
    'craft_diamond_pickaxe', 'craft_diamond_sword', 'craft_diamond_armor',
    'craft_blaze_powder', 'craft_wooden_pickaxe', 'craft_stone_pickaxe',
    'place_crafting_table', 'place_chest', 'place_bed',
    'place_boat', 'place_torch', 'equip_best_armor', 'equip_best_weapon',
    'eat_food', 'flee', 'recover_position', 'check_inventory',
    'check_time_of_day', 'check_light_level', 'check_biome',
    'scan_workspace', 'open_chest', 'list_waypoints', 'recover_death_items',
    'abandon_death_recovery', 'return_to_spawn_or_home', 'mlg_water_bucket',
    'enter_boat', 'exit_boat', 'attack_nearest_hostile', 'retreat_from_combat',
    'block_with_shield', 'charge_bow', 'deflect_ghast_fireball', 'kite_mob',
    'kill_blaze', 'kill_enderman', 'craft_bed', 'sleep_if_possible',
    'set_spawn_with_bed', 'use_bed_bomb', 'avoid_bed_explosion',
    'collect_water', 'collect_lava', 'build_nether_portal', 'cast_nether_portal',
    'craft_flint_and_steel', 'light_nether_portal', 'enter_nether',
    'return_to_portal', 'equip_gold_armor', 'avoid_opening_chests_near_piglins',
    'retreat_from_nether_danger', 'leave_nether', 'throw_eye_of_ender',
    'locate_stronghold_step', 'dig_staircase_to_stronghold',
    'scan_for_end_portal_room', 'activate_end_portal', 'enter_end',
    'end_safe_landing', 'equip_pumpkin_head', 'look_down_around_endermen',
    'scan_end_crystals', 'destroy_end_crystal', 'destroy_caged_end_crystal',
    'destroy_nearby_end_crystals', 'attack_perched_dragon',
    'attack_dragon_with_bow', 'dragon_phase_crystals', 'dragon_phase_circle',
    'dragon_phase_perch', 'fight_dragon_phase', 'return_to_overworld_via_end_portal'
  ]
  for (const action of noArgActions) defineNoArgSchema(schemas, action)

  defineSchema(schemas, 'place_furnace', {
    allowedKeys: ['radius', 'allowPrepareArea'],
    defaults: { radius: 4, allowPrepareArea: true },
    clamp: { radius: { min: 1, max: 8, integer: true } },
    booleans: ['allowPrepareArea'],
  })

  defineSchema(schemas, 'look_around', {
    allowedKeys: ['radius'],
    defaults: { radius: LOOK_AROUND_DEFAULT_RADIUS },
    ignoreKeys: ['count'],
    clamp: { radius: { min: 8, max: LOOK_AROUND_MAX_RADIUS, integer: true } }
  })
  defineSchema(schemas, 'say', {
    allowedKeys: ['message'],
    required: ['message'],
    strings: { message: { max: 240, nonEmpty: true, rejectSlash: true } }
  })
  defineSchema(schemas, 'set_vtuber_mood', {
    allowedKeys: ['mood'],
    required: ['mood'],
    enums: { mood: Array.from(MOODS) }
  })
  for (const action of ['look_at_player', 'follow_player', 'come_here']) {
    defineSchema(schemas, action, {
      allowedKeys: ['username'],
      strings: { username: { max: 32, nonEmpty: true } }
    })
  }

  defineCountSchema(schemas, 'collect_wood', COLLECT_WOOD_DEFAULT_COUNT, 1, COLLECT_WOOD_MAX_COUNT)
  defineCountSchema(schemas, 'mine_stone', MINE_STONE_DEFAULT_COUNT, 1, MINE_STONE_MAX_COUNT)
  defineSchema(schemas, 'mine_coal', {
    allowedKeys: ['count', 'radius', 'allowExcavate', 'accessMode'],
    defaults: {
      count: MINE_COAL_DEFAULT_COUNT,
      radius: ACQUIRE_BLOCKS_DEFAULT_RADIUS,
      allowExcavate: true,
      accessMode: 'safe_staircase'
    },
    clamp: {
      count: { min: 1, max: ORE_MINE_MAX_COUNT, integer: true },
      radius: { min: ACQUIRE_BLOCKS_MIN_RADIUS, max: ACQUIRE_BLOCKS_MAX_RADIUS, integer: true }
    },
    enums: { accessMode: Array.from(ACQUIRE_ACCESS_MODES) }
  })
  defineCountSchema(schemas, 'mine_iron_ore', MINE_IRON_DEFAULT_COUNT, 1, ORE_MINE_MAX_COUNT)
  defineCountSchema(schemas, 'collect_obsidian', 1, 1, 14)
  defineCountSchema(schemas, 'craft_planks', 4, 1, CRAFT_MAX_COUNT)
  defineCountSchema(schemas, 'craft_sticks', 1, 1, CRAFT_MAX_COUNT)
  defineCountSchema(schemas, 'craft_crafting_table', 1, 1, CRAFT_MAX_COUNT)
  defineCountSchema(schemas, 'craft_torches', 4, 1, CRAFT_MAX_COUNT)
  defineCountSchema(schemas, 'craft_eyes_of_ender', 1, 1, 12)
  defineCountSchema(schemas, 'smelt_iron', SMELT_DEFAULT_COUNT, 1, SMELT_IRON_MAX_COUNT)
  defineCountSchema(schemas, 'barter_with_piglins', 1, 1, 16)
  defineCountSchema(schemas, 'collect_blaze_rods', COLLECT_BLAZE_ROD_DEFAULT_COUNT, 1, COLLECT_BLAZE_ROD_MAX_COUNT)

  defineRadiusSchema(schemas, 'explore_nearby', EXPLORE_DEFAULT_RADIUS, 8, EXPLORE_MAX_RADIUS)
  defineSchema(schemas, 'find_safe_workspace', {
    allowedKeys: ['radius', 'purpose'],
    defaults: { radius: WORKSPACE_DEFAULT_RADIUS },
    clamp: { radius: { min: 8, max: WORKSPACE_MAX_RADIUS, integer: true } },
    enums: { purpose: Array.from(WORKSPACE_PURPOSES) }
  })
  defineSchema(schemas, 'setup_workspace', {
    allowedKeys: ['need_crafting_table', 'need_furnace', 'need_chest', 'radius'],
    defaults: { need_crafting_table: true, need_furnace: false, need_chest: false, radius: WORKSPACE_DEFAULT_RADIUS },
    clamp: { radius: { min: 8, max: WORKSPACE_MAX_RADIUS, integer: true } },
    booleans: ['need_crafting_table', 'need_furnace', 'need_chest']
  })
  defineSchema(schemas, 'approach_station', {
    allowedKeys: ['station', 'radius'],
    defaults: { radius: STATION_APPROACH_RADIUS },
    required: ['station'],
    clamp: { radius: { min: 2, max: STATION_USE_RADIUS, integer: true } },
    enums: { station: Array.from(STATION_BLOCK_TYPES) }
  })
  defineRadiusSchema(schemas, 'scan_for_hostiles', 16, 8, 64)
  defineRadiusSchema(schemas, 'scan_for_passive_mobs', 16, 8, 64)
  defineRadiusSchema(schemas, 'scan_for_chests', 16, 8, 64)
  defineRadiusSchema(schemas, 'scan_for_liquids', 16, 8, 64)
  defineRadiusSchema(schemas, 'scan_for_structures', 32, 16, 128)
  defineRadiusSchema(schemas, 'find_lava_pool', LAVA_POOL_SEARCH_RADIUS_DEFAULT, 16, LAVA_POOL_SEARCH_RADIUS_MAX)
  defineRadiusSchema(schemas, 'find_nether_fortress', NETHER_FORTRESS_SEARCH_RADIUS, 32, NETHER_FORTRESS_SEARCH_RADIUS)

  defineSchema(schemas, 'navigate_to_block_type', {
    allowedKeys: ['targets', 'radius'],
    defaults: { radius: ACQUIRE_BLOCKS_DEFAULT_RADIUS },
    required: ['targets'],
    clamp: { radius: { min: ACQUIRE_BLOCKS_MIN_RADIUS, max: ACQUIRE_BLOCKS_MAX_RADIUS, integer: true } },
    targets: { field: 'targets', allowed: ACQUIRE_ALLOWED_TARGETS, nonEmpty: true }
  })
  defineSchema(schemas, 'acquire_blocks', {
    allowedKeys: ['targets', 'count', 'radius', 'allowExcavate', 'accessMode'],
    defaults: { count: ACQUIRE_BLOCKS_DEFAULT_COUNT, radius: ACQUIRE_BLOCKS_DEFAULT_RADIUS, allowExcavate: false, accessMode: 'surface_first' },
    required: ['targets'],
    clamp: {
      count: { min: 1, max: ACQUIRE_BLOCKS_MAX_COUNT, integer: true },
      radius: { min: ACQUIRE_BLOCKS_MIN_RADIUS, max: ACQUIRE_BLOCKS_MAX_RADIUS, integer: true }
    },
    booleans: ['allowExcavate'],
    enums: { accessMode: Array.from(ACQUIRE_ACCESS_MODES) },
    targets: { field: 'targets', allowed: ACQUIRE_ALLOWED_TARGETS, nonEmpty: true }
  })
  defineSchema(schemas, 'scan_for_specific_block', {
    allowedKeys: ['targets', 'radius'],
    defaults: { radius: 32 },
    required: ['targets'],
    clamp: { radius: { min: 8, max: 96, integer: true } },
    targets: { field: 'targets', nonEmpty: true, maxItems: 6 }
  })
  defineSchema(schemas, 'debug_find_blocks', {
    allowedKeys: ['targets', 'radius'],
    defaults: { radius: ACQUIRE_BLOCKS_DEFAULT_RADIUS },
    required: ['targets'],
    clamp: { radius: { min: 8, max: MAX_SCAN_RADIUS, integer: true } },
    targets: { field: 'targets', nonEmpty: true, maxItems: 8 }
  })
  defineSchema(schemas, 'debug_collect_drops', {
    allowedKeys: ['radius', 'targetItems'],
    defaults: { radius: 8, targetItems: ['coal', 'raw_iron', 'cobblestone', 'stone'] },
    clamp: { radius: { min: 2, max: 32, integer: true } }
  })

  defineSchema(schemas, 'craft_item', {
    allowedKeys: ['item', 'count'],
    defaults: { count: 1 },
    required: ['item'],
    clamp: { count: { min: 1, max: CRAFT_MAX_COUNT, integer: true } },
    enums: { item: Array.from(CRAFT_ITEM_ALLOWED_ITEMS) },
    singleCountItems: CRAFT_ITEM_SINGLE_COUNT
  })
  defineSchema(schemas, 'smelt_item', {
    allowedKeys: ['input', 'fuel', 'count'],
    defaults: { count: 1 },
    required: ['input'],
    clamp: { count: { min: 1, max: SMELT_MAX_COUNT, integer: true } },
    enums: { input: Object.keys(SMELT_INPUTS) },
    fuelField: 'fuel'
  })

  defineSchema(schemas, 'place_block', {
    allowedKeys: ['item', 'mode', 'direction'],
    defaults: { mode: 'nearby' },
    required: ['item'],
    enums: { mode: Array.from(PLACE_MODES), direction: Array.from(PLACE_DIRECTIONS) },
    nullableEnums: ['direction'],
    itemValidator: 'place_item'
  })
  defineSchema(schemas, 'place_block_in_direction', {
    allowedKeys: ['item', 'direction'],
    defaults: { direction: 'forward' },
    required: ['item'],
    enums: { direction: Array.from(PLACE_IN_DIR_DIRS) },
    itemValidator: 'place_or_pillar_item'
  })
  defineSchema(schemas, 'place_water', {
    allowedKeys: ['mode', 'direction'],
    defaults: { mode: 'nearby' },
    enums: { mode: Array.from(WATER_MODES), direction: Array.from(PLACE_DIRECTIONS) },
    nullableEnums: ['direction']
  })
  defineSchema(schemas, 'place_lava', {
    allowedKeys: ['mode', 'direction'],
    defaults: { mode: 'controlled_source' },
    enums: { mode: Array.from(LAVA_SAFE_MODES), direction: Array.from(PLACE_DIRECTIONS) },
    nullableEnums: ['direction']
  })
  defineSchema(schemas, 'dig_staircase', {
    allowedKeys: ['direction', 'max_steps'],
    defaults: { direction: 'down', max_steps: STAIRCASE_MAX_STEPS },
    clamp: { max_steps: { min: 1, max: STAIRCASE_MAX_STEPS, integer: true } },
    enums: { direction: Array.from(STAIRCASE_DIRS) }
  })
  defineSchema(schemas, 'pillar_up', {
    allowedKeys: ['height', 'block'],
    defaults: { height: 3 },
    clamp: { height: { min: 1, max: PILLAR_MAX_HEIGHT, integer: true } },
    strings: { block: { max: 64, nonEmpty: true } }
  })
  defineSchema(schemas, 'bridge_gap', {
    allowedKeys: ['direction', 'length', 'block'],
    defaults: { direction: 'forward', length: 3 },
    clamp: { length: { min: 1, max: BRIDGE_MAX_LENGTH, integer: true } },
    enums: { direction: Array.from(BRIDGE_DIRS) },
    strings: { block: { max: 64, nonEmpty: true } }
  })
  defineSchema(schemas, 'set_sneak', { allowedKeys: ['enabled'], required: ['enabled'], booleans: ['enabled'] })
  defineSchema(schemas, 'set_sprint', { allowedKeys: ['enabled'], required: ['enabled'], booleans: ['enabled'] })

  defineSchema(schemas, 'mark_waypoint', {
    allowedKeys: ['label', 'kind'],
    required: ['label'],
    strings: { label: { max: 64, nonEmpty: true } },
    enums: { kind: Array.from(VALID_WAYPOINT_KINDS) }
  })
  defineSchema(schemas, 'return_to_waypoint', {
    allowedKeys: ['label', 'kind'],
    required: ['label'],
    strings: { label: { max: 64, nonEmpty: true } },
    enums: { kind: Array.from(VALID_WAYPOINT_KINDS) }
  })
  defineSchema(schemas, 'return_to_position', {
    allowedKeys: ['x', 'y', 'z', 'dimension', 'radius'],
    required: ['x', 'y', 'z'],
    defaults: { radius: 3 },
    clamp: {
      x: { min: -30000000, max: 30000000 },
      y: { min: -64, max: 320 },
      z: { min: -30000000, max: 30000000 },
      radius: { min: 1, max: 16, integer: true },
    },
    enums: { dimension: ['overworld', 'the_nether', 'the_end', 'minecraft:overworld', 'minecraft:the_nether', 'minecraft:the_end'] }
  })
  defineNoArgSchema(schemas, 'set_home_position')
  defineSchema(schemas, 'drop_item', {
    allowedKeys: ['item', 'count', 'force'],
    required: ['item'],
    clamp: { count: { min: 1, max: 64, integer: true } },
    booleans: ['force'],
    strings: { item: { max: 64, nonEmpty: true } }
  })
  defineSchema(schemas, 'equip_tool', {
    allowedKeys: ['block', 'tool'],
    strings: { block: { max: 64, nonEmpty: true }, tool: { max: 64, nonEmpty: true } }
  })
  defineSchema(schemas, 'equip_best_tool', {
    allowedKeys: ['block'],
    ignoreKeys: ['count'],
    strings: { block: { max: 64, nonEmpty: true } }
  })
  defineSchema(schemas, 'equip_armor', {
    allowedKeys: ['mode', 'item'],
    enums: { mode: Array.from(EQUIP_ARMOR_MODES) },
    strings: { item: { max: 64, nonEmpty: true } }
  })
  defineSchema(schemas, 'select_hotbar_slot', {
    allowedKeys: ['slot'],
    defaults: { slot: 0 },
    clamp: { slot: { min: 0, max: 8, integer: true } }
  })
  defineSchema(schemas, 'loot_chest', {
    allowedKeys: ['priority'],
    defaults: { priority: 'general' },
    enums: { priority: Array.from(LOOT_PRIORITIES) }
  })
  defineSchema(schemas, 'deposit_items', { allowedKeys: ['items'], required: ['items'], itemListField: 'items' })
  defineSchema(schemas, 'withdraw_items', { allowedKeys: ['items'], required: ['items'], itemListField: 'items' })

  defineSchema(schemas, 'attack_mob', {
    allowedKeys: ['mob_type', 'radius'],
    clamp: { radius: { min: 4, max: 64, integer: true } },
    strings: { mob_type: { max: 64, nonEmpty: true } }
  })
  defineSchema(schemas, 'shoot_bow', { allowedKeys: ['target'], strings: { target: { max: 64, nonEmpty: true } } })
  defineSchema(schemas, 'throw_ender_pearl', {
    allowedKeys: ['mode'],
    defaults: { mode: 'forward' },
    enums: { mode: Array.from(ENDER_PEARL_MODES) }
  })
  defineSchema(schemas, 'kill_passive_mob', {
    allowedKeys: ['target'],
    enums: { target: Array.from(FOOD_MOB_NAMES) }
  })
  defineSchema(schemas, 'navigate_nether_safely', {
    allowedKeys: ['direction'],
    enums: { direction: ['north', 'south', 'east', 'west'] }
  })
  for (const action of ACTIONS) {
    if (!schemas[action]) defineNoArgSchema(schemas, action)
  }

  return schemas
}

function defineSchema(schemas, action, schema) {
  schemas[action] = {
    allowedKeys: [],
    defaults: {},
    passthrough: false,
    ...schema
  }
}

function defineNoArgSchema(schemas, action) {
  defineSchema(schemas, action, { allowedKeys: [], noArg: true, ignoreKeys: ['count'] })
}

function defineCountSchema(schemas, action, defaultCount, min, max) {
  defineSchema(schemas, action, {
    allowedKeys: ['count'],
    defaults: { count: defaultCount },
    clamp: { count: { min, max, integer: true } }
  })
}

function defineRadiusSchema(schemas, action, defaultRadius, min, max) {
  defineSchema(schemas, action, {
    allowedKeys: ['radius'],
    defaults: { radius: defaultRadius },
    clamp: { radius: { min, max, integer: true } }
  })
}

function actionArgsSchemaForMetadata(name) {
  const schema = ACTION_ARG_SCHEMAS[name]
  if (!schema) return {}
  return compactArgSchema(schema)
}

function compactArgSchema(schema) {
  const result = {
    allowedKeys: schema.allowedKeys || [],
    defaults: schema.defaults || {}
  }
  if (schema.noArg) result.noArg = true
  if (schema.clamp) result.clamp = schema.clamp
  if (schema.enums) result.enums = schema.enums
  if (schema.required) result.required = schema.required
  if (schema.ignoreKeys) result.ignoreKeys = schema.ignoreKeys
  return result
}

let defaultMovements = null

const botOptions = {
  host: process.env.MC_HOST || 'localhost',
  port: numberEnv('MC_PORT', 25565),
  username: process.env.MC_USERNAME || 'AI_VTuber'
}

if (MC_VERSION) {
  botOptions.version = MC_VERSION
}

let bot = null
let reconnectTimer = null
let reconnectAttempts = 0
let isConnecting = false
let shuttingDown = false
let lastKickReason = null
let lastDisconnectReason = null
let lastError = null
let lastActionStartedAt = null
let currentActionName = null
let actionRunning = false
let lastPathGoal = null
let lastPathCancelReason = null
const _lastAcquireTargetByAction = new Map()

function connectBot() {
  if (shuttingDown || isConnecting || (bot && bot.player)) {
    return
  }

  isConnecting = true
  try {
    const instance = mineflayer.createBot(botOptions)
    bot = instance
    attachBotPlugins(instance)
    attachBotEventHandlers(instance)
  } catch (error) {
    isConnecting = false
    bot = null
    lastError = formatErrorForStatus(error)
    console.error('[Mineflayer] failed to create bot:', error)
    scheduleReconnect('createBot_error')
  }
}

function attachBotPlugins(instance) {
  instance.loadPlugin(pathfinder)
  instance.loadPlugin(toolPlugin)
  instance.loadPlugin(collectBlock)
}

function attachBotEventHandlers(instance) {
  instance.on('login', () => {
    if (bot !== instance) return
    reconnectAttempts = 0
    isConnecting = false
    console.log(`Mineflayer logged in as ${instance.username}`)
  })

  instance.on('spawn', () => {
    if (bot !== instance) return
    const now = Date.now()
    if (lastDeath && now - lastDeath.ts <= RESPAWN_RECENT_SECONDS * 1000) {
      lastRespawnAt = now
    }
    defaultMovements = new Movements(instance)
    instance.pathfinder.setMovements(defaultMovements)
    instance.collectBlock.movements = defaultMovements
    console.log('Mineflayer bot spawned')
    try {
      instance.chat('AI VTuber online!')
    } catch (error) {
      lastError = formatErrorForStatus(error)
    }
  })

  instance.on('kicked', (reason) => {
    if (bot !== instance) return
    lastKickReason = safeReason(reason)
    console.log('Mineflayer bot kicked:', reason)
    scheduleReconnect('kicked')
  })

  instance.on('error', (error) => {
    if (bot !== instance) return
    lastError = formatErrorForStatus(error)
    console.log('Mineflayer error:', error)
  })

  instance.on('end', (reason) => {
    if (bot !== instance) return
    if (bot === instance) {
      bot = null
    }
    isConnecting = false
    lastDisconnectReason = safeReason(reason) || 'end'
    console.log('Mineflayer bot disconnected', reason || '')
    safeStopMovement(instance)
    scheduleReconnect('end')
  })

  instance.on('entityHurt', (entity) => {
    if (bot !== instance) return
    if (entity === instance.entity) {
      lastDeathCause = inferRecentDamageCause()
    }
  })

  instance.on('message', (message) => {
    if (bot !== instance) return
    const text = message ? message.toString() : ''
    if (!text || !instance.username || !text.includes(instance.username)) return
    const lowered = text.toLowerCase()
    if (
      lowered.includes('died') ||
      lowered.includes('slain') ||
      lowered.includes('shot') ||
      lowered.includes('fell') ||
      lowered.includes('burned') ||
      lowered.includes('lava') ||
      lowered.includes('blew up') ||
      lowered.includes('void')
    ) {
      lastDeathCause = text
    }
  })

  instance.on('death', () => {
    if (bot !== instance) return
    if (!instance.entity) return
    const pos = instance.entity.position
    const dimension = (instance.game && instance.game.dimension) ? String(instance.game.dimension) : 'overworld'
    const inventory = inventoryJson()
    const cause = lastDeathCause || inferRecentDamageCause()
    lastDeath = {
      x: Math.floor(pos.x),
      y: Math.floor(pos.y),
      z: Math.floor(pos.z),
      dimension,
      ts: Date.now(),
      cause,
      inventory,
      recovery_attempts: 0,
      recovery_failures: 0,
      abandoned: false
    }
    deathRecoveryFailures = 0
    deathRecoveryAbandonedAt = null
    waypointStore.set('death_location', { label: 'death_location', kind: 'death_location', ...lastDeath })
    console.log(`[Death] at x=${lastDeath.x} y=${lastDeath.y} z=${lastDeath.z} dim=${dimension} cause=${cause || 'unknown'}`)
  })
}

function scheduleReconnect(reason) {
  if (shuttingDown || !MC_AUTO_RECONNECT || reconnectTimer) {
    return
  }

  reconnectAttempts += 1
  console.log(`[Mineflayer] reconnect scheduled in ${MC_RECONNECT_DELAY_MS}ms reason=${reason} attempt=${reconnectAttempts}`)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectBot()
  }, MC_RECONNECT_DELAY_MS)
}

function safeReason(reason) {
  if (reason === undefined || reason === null) return null
  if (typeof reason === 'string') return reason
  try {
    return JSON.stringify(reason)
  } catch (_error) {
    return String(reason)
  }
}

function formatErrorForStatus(error) {
  if (!error) return null
  return {
    name: error.name || 'Error',
    message: error.message || String(error),
    code: error.code || null
  }
}

function safeStopMovement(instance) {
  try {
    if (instance && instance.pathfinder) instance.pathfinder.setGoal(null)
  } catch (_error) {}
  try {
    if (instance && typeof instance.clearControlStates === 'function') instance.clearControlStates()
  } catch (_error) {}
}

// In-memory waypoint store (label → waypoint object). Python persists these in SQLite.
const waypointStore = new Map()
// Last recorded death location for this session.
let lastDeath = null
let lastRespawnAt = null
let lastDeathCause = null
let deathRecoveryFailures = 0
let deathRecoveryAbandonedAt = null
connectBot()

const app = express()
app.use(bodyParser.json({ limit: '10kb' }))

app.get('/status', (_req, res) => {
  res.json(getStatus())
})

app.get('/actions', (_req, res) => {
  res.json({ ok: true, actions: Array.from(ACTIONS).sort() })
})

// Returns deduplicated structured metadata for all known actions.
// Python uses this to intersect with the action catalog:
//   - implemented=true  → action is ready; catalog may expose it to the LLM.
//   - implemented=false → action exists in roadmap but has no Node handler yet.
app.get('/actions_metadata', (_req, res) => {
  res.json(buildActionsMetadata())
})

app.post('/action', async (req, res) => {
  try {
    const result = await executeAction(req.body)
    res.status(result.ok ? 200 : 400).json(result)
  } catch (error) {
    console.log('Action failed:', error)
    res.status(500).json({
      ok: false,
      action: actionName(req.body),
      result: {},
      error: 'Action failed.'
    })
  }
})

app.use((error, _req, res, next) => {
  if (!error) {
    next()
    return
  }

  res.status(400).json({
    ok: false,
    result: {},
    error: 'Invalid JSON request body.'
  })
})

app.listen(BRIDGE_PORT, () => {
  console.log(`Mineflayer bridge listening on port ${BRIDGE_PORT}`)
})

setInterval(() => {
  console.log(`[Mineflayer] heartbeat connected=${Boolean(bot && bot.player)} entityReady=${Boolean(bot && bot.entity)} currentAction=${currentActionName || 'none'} elapsedMs=${lastActionStartedAt ? Date.now() - lastActionStartedAt : 0}`)
}, 5000)

process.on('uncaughtException', (error) => {
  lastError = formatErrorForStatus(error)
  console.error('[Mineflayer] uncaughtException:', error)
})

process.on('unhandledRejection', (reason) => {
  lastError = formatErrorForStatus(reason instanceof Error ? reason : new Error(String(reason)))
  console.error('[Mineflayer] unhandledRejection:', reason)
})

process.on('SIGINT', () => {
  shuttingDown = true
  safeStopMovement(bot)
  process.exit(0)
})

process.on('SIGTERM', () => {
  shuttingDown = true
  safeStopMovement(bot)
  process.exit(0)
})

function numberEnv(name, fallback) {
  const raw = process.env[name]
  if (!raw) {
    return fallback
  }

  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : fallback
}

function booleanEnv(name, fallback) {
  const raw = process.env[name]
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    return fallback
  }

  return !['0', 'false', 'no', 'off'].includes(String(raw).trim().toLowerCase())
}

function optionalEnv(name) {
  const raw = process.env[name]
  if (!raw || raw.trim() === '') {
    return null
  }

  return raw.trim()
}

function actionName(request) {
  if (!request || typeof request !== 'object' || typeof request.action !== 'string') {
    return 'unknown'
  }

  return request.action
}

function isBotConnected() {
  return Boolean(bot && bot.player && bot.entity)
}

function disconnectedActionResult(action) {
  return {
    ok: false,
    action,
    failure_type: 'bot_disconnected',
    result: {
      failure_type: 'bot_disconnected',
      stop_reason: reconnectTimer ? 'reconnecting' : 'disconnected',
      repeatable_now: true,
      reconnectAttempts,
      lastKickReason,
      lastDisconnectReason,
      lastError,
      diagnostics: bridgeDiagnostics()
    },
    error: 'Bot is disconnected/reconnecting'
  }
}

function bridgeDiagnostics() {
  return {
    lastKickReason,
    lastDisconnectReason,
    lastError,
    reconnectAttempts,
    lastActionStartedAt,
    currentActionName,
    currentActionElapsedMs: lastActionStartedAt ? Date.now() - lastActionStartedAt : null,
    lastPathGoal,
    lastPathCancelReason
  }
}

function ok(action, result = {}) {
  return { ok: true, action, result, error: null }
}

function fail(action, error, result = {}) {
  const enriched = { ...(result || {}) }
  enriched.failure_type = enriched.failure_type || inferFailureType(error)
  enriched.stop_reason = enriched.stop_reason || inferStopReason(error, enriched.failure_type)
  enriched.suggested_next_action = enriched.suggested_next_action || suggestedActionForFailure(enriched.failure_type, enriched.stop_reason)
  if (enriched.can_retry === undefined) enriched.can_retry = canRetryFailure(enriched.failure_type)
  enriched.needed = enriched.needed || neededForFailure(enriched.failure_type, enriched.stop_reason)
  enriched.position = enriched.position || currentPositionJson()
  enriched.diagnostics = enriched.diagnostics || {}
  if (enriched.failure_type === 'navigation_cancelled') {
    if (enriched.repeatable_now === undefined) enriched.repeatable_now = true
    if (!enriched.failed_because) enriched.failed_because = [{ kind: 'path_goal_changed', action, recoverable: true }]
  }
  return { ok: false, action, result: enriched, error }
}

function actionTimeoutFailure(action, timeoutMs) {
  return fail(action, `Timed out ${action} after ${timeoutMs}ms.`, {
    failure_type: 'action_timeout',
    stop_reason: 'action_timeout',
    repeatable_now: true,
    can_retry: true,
    failed_because: [{ kind: 'action_timeout', action, timeout_ms: timeoutMs }],
    diagnostics: {
      timeout_ms: timeoutMs,
      currentActionName,
      currentActionElapsedMs: lastActionStartedAt ? Date.now() - lastActionStartedAt : null
    }
  })
}

function isGoalChangedError(error) {
  const text = String(error || '').toLowerCase()
  return text.includes('goal was changed')
}

function inferFailureType(error) {
  const text = String(error || '').toLowerCase()
  if (text.includes('goal was changed')) return 'navigation_cancelled'
  if (text.includes('unsupported action')) return 'unsupported_action'
  if (text.includes('unsupported action') || text.includes('unknown args') || text.includes('requires args') || text.includes('must be')) {
    return 'invalid_args'
  }
  if (text.includes('path') && (text.includes('timed out') || text.includes('timeout'))) return 'navigation_failed'
  if (text.includes('action_timeout')) return 'action_timeout'
  if (text.includes('timed out') || text.includes('timeout')) return 'path_timeout'
  if (text.includes('health too low') || text.includes('too dangerous') || text.includes('unsafe')) return 'danger_detected'
  if (text.includes('no safe') && text.includes('placement')) return 'no_safe_workspace'
  if (text.includes('no safe') || text.includes('cramped') || text.includes('headroom')) return 'no_safe_workspace'
  if (text.includes('no crafting table') || text.includes('no furnace') || text.includes('station')) return 'missing_station'
  if (text.includes('crafting table')) return 'missing_crafting_table'
  if (text.includes('furnace')) return 'missing_furnace'
  if (text.includes('missing materials')) return 'missing_materials'
  if (text.includes('missing tool') || text.includes('no pickaxe')) return 'missing_tool'
  if (text.includes('unreachable') || text.includes('not accessible')) return 'target_unreachable'
  if (text.includes('not ready') || text.includes('not spawned')) return 'not_ready'
  if (text.includes('no ') || text.includes('missing')) return 'missing_materials'
  return 'action_failed'
}

function inferStopReason(error, failureType) {
  const text = String(error || '').toLowerCase()
  if (failureType === 'navigation_cancelled') return 'path_goal_changed'
  if (failureType === 'no_safe_workspace') return 'area_cramped'
  if (failureType === 'missing_station' && text.includes('crafting table')) return 'no_crafting_table_nearby'
  if (failureType === 'missing_station' && text.includes('furnace')) return 'no_furnace_nearby'
  if (failureType === 'missing_crafting_table') return 'no_crafting_table_nearby'
  if (failureType === 'missing_furnace') return 'no_furnace_nearby'
  if (failureType === 'missing_materials') return 'missing_required_item'
  if (failureType === 'missing_tool') return 'missing_required_tool'
  if (failureType === 'danger_detected') return 'unsafe_placement_area'
  if (failureType === 'path_timeout' || failureType === 'navigation_failed') return 'path_timeout'
  if (failureType === 'action_timeout') return 'action_timeout'
  if (failureType === 'target_unreachable') return 'targets_found_but_not_accessible'
  if (failureType === 'unsupported_action') return 'unsupported_action'
  if (failureType === 'invalid_args') return 'invalid_args'
  if (text.includes('liquid')) return 'unsafe_placement_area'
  return 'action_failed'
}

function suggestedActionForFailure(failureType, stopReason) {
  if (failureType === 'no_safe_workspace' || stopReason === 'area_cramped') return 'find_safe_workspace'
  if (failureType === 'missing_station' || stopReason === 'no_crafting_table_nearby' || stopReason === 'no_furnace_nearby') {
    return 'return_to_workspace'
  }
  if (failureType === 'missing_crafting_table' || stopReason === 'no_crafting_table_nearby') {
    return firstInventoryItemByNames(['crafting_table']) ? 'find_safe_workspace' : 'craft_crafting_table'
  }
  if (failureType === 'missing_furnace' || stopReason === 'no_furnace_nearby') {
    return firstInventoryItemByNames(['furnace']) ? 'find_safe_workspace' : 'craft_furnace'
  }
  if (failureType === 'danger_detected') return 'avoid_hazard'
  if (failureType === 'path_timeout' || failureType === 'navigation_failed' || failureType === 'target_unreachable') return 'navigate_to_block_type'
  if (failureType === 'action_timeout') return 'status'
  if (failureType === 'missing_tool' || failureType === 'missing_materials') return 'status'
  return null
}

function canRetryFailure(failureType) {
  return !['unsupported_action', 'invalid_args', 'not_ready'].includes(failureType)
}

function neededForFailure(failureType, stopReason) {
  if (failureType === 'no_safe_workspace' || stopReason === 'area_cramped') {
    return 'safe open area with solid floor and 2-block head clearance'
  }
  if (failureType === 'missing_station' && stopReason === 'no_crafting_table_nearby') return 'nearby crafting_table'
  if (failureType === 'missing_station' && stopReason === 'no_furnace_nearby') return 'nearby furnace'
  if (failureType === 'missing_crafting_table') return 'nearby crafting_table'
  if (failureType === 'missing_furnace') return 'nearby furnace'
  if (failureType === 'missing_tool') return 'required tool in inventory'
  if (failureType === 'missing_materials') return 'required item or materials in inventory'
  if (failureType === 'danger_detected') return 'safe area away from hazards'
  return null
}

function currentPositionJson() {
  return bot && bot.entity ? positionJson(bot.entity.position) : null
}

function getStatus() {
  if (!bot) {
    return {
      ok: false,
      connected: false,
      username: botOptions.username || null,
      entityReady: false,
      position: null,
      dimension: null,
      time: null,
      health: null,
      food: null,
      onGround: null,
      inWater: null,
      inLava: null,
      inventory: [],
      nearbyPlayers: [],
      nearbyEntities: [],
      nearbyBlockCounts: {},
      nearbyBlocks: { crafting_table: null, furnace: null, chest: null },
      stationFacts: null,
      ...bridgeDiagnostics(),
      lastDeath: lastDeath || null,
      last_death: lastDeath || null,
      respawned_recently: false,
      death_recovery: deathRecoveryState()
    }
  }

  return {
    ok: true,
    connected: Boolean(bot.player),
    username: bot.username || null,
    entityReady: Boolean(bot.entity),
    position: bot.entity ? positionJson(bot.entity.position) : null,
    dimension: bot.game ? bot.game.dimension : null,
    time: timeJson(),
    health: typeof bot.health === 'number' ? bot.health : null,
    food: typeof bot.food === 'number' ? bot.food : null,
    onGround: bot.entity ? Boolean(bot.entity.onGround) : null,
    inWater: bot.entity ? isInNamedLiquid('water') : null,
    inLava: bot.entity ? isInNamedLiquid('lava') : null,
    inventory: inventoryJson(),
    nearbyPlayers: nearbyPlayersJson(16),
    nearbyEntities: nearbyEntitiesJson(16),
    nearbyBlockCounts: nearbyBlockCountsJson(12, 32),
    nearbyBlocks: nearbyBlocksJson(),
    stationFacts: stationFactsJson(),
    ...flatStationFactsJson(),
    ...bridgeDiagnostics(),
    lastDeath: lastDeath || null,
    last_death: lastDeath || null,
    respawned_recently: respawnedRecently(),
    death_recovery: deathRecoveryState()
  }
}

function inventoryJson() {
  if (!bot || !bot.inventory || !Array.isArray(bot.inventory.slots)) {
    return []
  }

  return bot.inventory.slots
    .filter((item) => item)
    .map((item) => ({
      name: item.name,
      displayName: item.displayName,
      count: item.count,
      slot: item.slot
    }))
}

function positionJson(position) {
  return {
    x: position.x,
    y: position.y,
    z: position.z
  }
}

function timeJson() {
  if (!bot || !bot.time) {
    return null
  }

  return {
    timeOfDay: bot.time.timeOfDay,
    day: bot.time.day,
    isDay: bot.time.isDay,
    moonPhase: bot.time.moonPhase
  }
}

function blockJson(block) {
  if (!block) {
    return null
  }

  return {
    name: block.name,
    position: positionJson(block.position),
    distance: bot && bot.entity ? bot.entity.position.distanceTo(block.position) : null
  }
}

function entityJson(entity) {
  if (!entity) {
    return null
  }

  return {
    id: entity.id,
    name: entity.name || entity.displayName || entity.type || 'unknown',
    type: entity.type || null,
    username: entity.username || null,
    hostile: isHostileEntity(entity),
    position: entity.position ? positionJson(entity.position) : null,
    distance: bot && bot.entity && entity.position ? bot.entity.position.distanceTo(entity.position) : null
  }
}

function nearbyBlocksJson() {
  return {
    crafting_table: blockJson(findNearbyCraftingTable(STATION_SCAN_RADIUS)),
    furnace: blockJson(findNearbyFurnace(STATION_SCAN_RADIUS)),
    chest: blockJson(findNearbyChest(STATION_SCAN_RADIUS))
  }
}

function stationFactsJson() {
  const craftingTable = findNearbyCraftingTable(STATION_SCAN_RADIUS)
  const furnace = findNearbyFurnace(STATION_SCAN_RADIUS)
  const chest = findNearbyChest(STATION_SCAN_RADIUS)
  return {
    usable_radius: STATION_USE_RADIUS,
    crafting_table: stationFact(craftingTable),
    furnace: stationFact(furnace),
    chest: stationFact(chest)
  }
}

function flatStationFactsJson() {
  const facts = stationFactsJson()
  return {
    has_nearby_crafting_table_usable: facts.crafting_table.usable,
    nearest_crafting_table_distance: facts.crafting_table.distance,
    nearest_crafting_table_position: facts.crafting_table.position,
    has_visible_crafting_table: facts.crafting_table.visible,
    has_nearby_furnace_usable: facts.furnace.usable,
    nearest_furnace_distance: facts.furnace.distance,
    nearest_furnace_position: facts.furnace.position,
  }
}

function stationFact(block) {
  const json = blockJson(block)
  return {
    visible: Boolean(json),
    usable: Boolean(json && typeof json.distance === 'number' && json.distance <= STATION_USE_RADIUS),
    distance: json ? json.distance : null,
    position: json ? json.position : null
  }
}

function nearbyPlayersJson(radius) {
  if (!bot || !bot.entity) {
    return []
  }

  return Object.values(bot.players)
    .filter((player) => player && player.entity && player.username !== bot.username)
    .map((player) => ({
      username: player.username,
      position: positionJson(player.entity.position),
      distance: bot.entity.position.distanceTo(player.entity.position)
    }))
    .filter((player) => player.distance <= radius)
    .sort((a, b) => a.distance - b.distance)
}

function nearbyEntitiesJson(radius) {
  if (!bot || !bot.entity || !bot.entities) {
    return []
  }

  return Object.values(bot.entities)
    .filter((entity) => entity && entity !== bot.entity && entity.position)
    .map((entity) => ({
      id: entity.id,
      name: entity.name || entity.displayName || entity.type || 'unknown',
      type: entity.type || null,
      username: entity.username || null,
      hostile: isHostileEntity(entity),
      position: positionJson(entity.position),
      distance: bot.entity.position.distanceTo(entity.position)
    }))
    .filter((entity) => entity.distance <= radius)
    .sort((a, b) => a.distance - b.distance)
    .slice(0, 24)
}

function nearbyBlockCountsJson(radius, limit) {
  if (!bot || !bot.entity) {
    return {}
  }

  const center = bot.entity.position.floored()
  const counts = new Map()

  for (let dx = -radius; dx <= radius; dx++) {
    for (let dy = -4; dy <= 6; dy++) {
      for (let dz = -radius; dz <= radius; dz++) {
        const position = center.offset(dx, dy, dz)
        if (center.distanceTo(position) > radius) {
          continue
        }

        const block = bot.blockAt(position)
        if (!block || block.name === 'air') {
          continue
        }

        counts.set(block.name, (counts.get(block.name) || 0) + 1)
      }
    }
  }

  return Object.fromEntries(
    Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
  )
}

async function executeAction(request) {
  const validation = validateActionRequest(request)
  if (!validation.ok) {
    return fail(actionName(request), validation.error, {
      unsupportedArgKeys: validation.unsupportedArgKeys || [],
      receivedArgs: validation.receivedArgs || {}
    })
  }

  if (!isBotConnected()) {
    return disconnectedActionResult(validation.action)
  }

  if (actionRunning) {
    return fail(validation.action, 'Bot is busy with another action.', {
      failure_type: 'body_busy',
      stop_reason: 'body_busy',
      repeatable_now: false,
      can_retry: true,
      failed_because: [{ kind: 'body_busy', action: currentActionName, recoverable: true }]
    })
  }

  const result = await withActionTimeout(
    validation.action,
    () => executeNormalizedAction(validation.action, validation.args),
    timeoutForAction(validation.action)
  )
  return attachArgDiagnostics(result, validation)
}

async function withActionTimeout(action, fn, timeoutMs) {
  const previousActionName = currentActionName
  const previousActionStartedAt = lastActionStartedAt
  currentActionName = action
  lastActionStartedAt = Date.now()
  actionRunning = true

  stopMovement()
  await yieldToEventLoop()

  let timedOut = false
  let timeoutId = null
  const timeout = new Promise((resolve) => {
    timeoutId = setTimeout(() => {
      timedOut = true
      stopMovement()
      resolve(actionTimeoutFailure(action, timeoutMs))
    }, timeoutMs)
  })

  try {
    return await Promise.race([Promise.resolve().then(fn), timeout])
  } catch (error) {
    if (isGoalChangedError(error)) {
      lastPathCancelReason = 'path_goal_changed'
      return fail(action, errorMessage(error), {
        failure_type: 'navigation_cancelled',
        stop_reason: 'path_goal_changed',
        repeatable_now: true,
        failed_because: [{ kind: 'path_goal_changed', action, recoverable: true }]
      })
    }
    stopMovement()
    return fail(action, errorMessage(error), {
      failure_type: isPathTimeoutError(error) ? 'navigation_failed' : undefined,
      stop_reason: isPathTimeoutError(error) ? 'path_timeout' : undefined,
      repeatable_now: true
    })
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
    stopMovement()
    await delay(150)
    actionRunning = false
    currentActionName = previousActionName
    lastActionStartedAt = previousActionStartedAt
  }
}

function timeoutForAction(action) {
  if (['navigate_to_block_type', 'explore_nearby', 'return_to_workspace', 'return_to_known_position'].includes(action)) {
    return NAVIGATION_TIMEOUT_MS
  }
  if (['collect_wood', 'acquire_blocks', 'mine_stone', 'mine_coal', 'mine_iron_ore'].includes(action)) {
    return RESOURCE_ACTION_TIMEOUT_MS
  }
  return ACTION_TIMEOUT_MS
}

async function executeNormalizedAction(action, args) {
  if (action === 'status') {
    return ok(action, getStatus())
  }

  if (action === 'set_vtuber_mood') {
    return ok(action, { mood: args.mood, accepted: true })
  }

  const readyError = requireReadyBot()
  if (readyError) {
    return fail(action, readyError)
  }

  switch (action) {
    case 'say':
      bot.chat(args.message)
      return ok(action, { message: args.message })

    case 'look_around':
      return await lookAround(args.radius)

    case 'explore_nearby':
      return await exploreNearby(args.radius)

    case 'look_at_player':
      return await lookAtPlayer(args.username)

    case 'follow_player':
      return followPlayer(args.username)

    case 'come_here':
      return comeHere(args.username)

    case 'stop':
      stopMovement()
      return ok(action, { stopped: true })

    case 'jump':
      shortJump()
      return ok(action, { jumped: true })

    case 'acquire_blocks':
      return await acquireBlocksAction(args)

    case 'navigate_to_block_type':
      return await navigateToBlockType(args)

    case 'collect_wood':
      return await collectWood(args.count)

    case 'craft_planks':
      return await craftPlanks(args.count)

    case 'craft_sticks':
      return await craftSticks(args.count)

    case 'craft_crafting_table':
      return await craftCraftingTable(args.count)

    case 'place_crafting_table':
      return await placeCraftingTable()

    case 'craft_item':
      return await craftItem(args.item, args.count)

    case 'craft_furnace':
      return await craftFurnace()

    case 'craft_torches':
      return await craftTorches(args.count)

    case 'craft_chest':
      return await craftChest()

    case 'craft_shield':
      return await craftShield()

    case 'craft_bucket':
      return await craftBucket()

    case 'craft_iron_pickaxe':
      return await craftIronPickaxe()

    case 'craft_iron_sword':
      return await craftIronSword()

    case 'craft_iron_armor':
      return await craftIronArmor()

    case 'place_block':
      return await placeBlock(args)

    case 'place_water':
      return await placeWater(args.mode)

    case 'place_lava':
      return await placeLava(args.mode)

    case 'place_bed':
      return await placeBed()

    case 'place_boat':
      return await placeBoat()

    case 'place_chest':
      return await placeChest()

    case 'place_furnace':
      return await placeFurnace(args)

    case 'place_torch':
      return await placeTorch()

    case 'craft_wooden_pickaxe':
      return await craftWoodenPickaxe()

    case 'mine_stone':
      return await mineStone(args.count)

    case 'mine_coal':
      return await mineCoal(args)

    case 'mine_iron_ore':
      return await mineIronOre(args.count)

    case 'craft_stone_pickaxe':
      return await craftStonePickaxe()

    case 'craft_blaze_powder':
      return await craftBlazePowder()

    case 'craft_diamond_pickaxe':
      return await craftDiamondPickaxe()

    case 'craft_diamond_sword':
      return await craftDiamondSword()

    case 'craft_diamond_armor':
      return await craftDiamondArmor()

    case 'equip_best_armor':
      return await equipBestArmor()

    case 'equip_best_tool':
      return await equipBestTool(args.block)

    case 'equip_best_weapon':
      return await equipBestWeapon()

    case 'find_safe_workspace':
      return await findSafeWorkspace(args.radius, args.purpose)

    case 'setup_workspace':
      return await setupWorkspace(args)

    case 'approach_station':
      return await approachStation(args.station, args.radius)

    case 'dig_staircase':
      return await digStaircase(args.direction, args.max_steps)

    case 'return_to_surface':
      return await returnToSurface()

    case 'pillar_up':
      return await pillarUp(args.height, args.block)

    case 'bridge_gap':
      return await bridgeGap(args.direction, args.length, args.block)

    case 'place_block_in_direction':
      return await placeBlockInDirection(args.item, args.direction)

    case 'mlg_water_bucket':
      return await mlgWaterBucket()

    case 'enter_boat':
      return await enterBoat()

    case 'exit_boat':
      return await exitBoat()

    case 'set_sneak':
      return setSneak(args.enabled)

    case 'set_sprint':
      return setSprint(args.enabled)

    case 'recover_position':
      return await recoverPosition()

    case 'check_inventory':
      return checkInventory()

    case 'check_time_of_day':
      return checkTimeOfDay()

    case 'check_light_level':
      return checkLightLevel()

    case 'check_biome':
      return checkBiome()

    case 'scan_for_hostiles':
      return scanForHostiles(args.radius)

    case 'scan_for_passive_mobs':
      return scanForPassiveMobs(args.radius)

    case 'scan_for_chests':
      return scanForChests(args.radius)

    case 'scan_for_specific_block':
      return scanForSpecificBlock(args.targets, args.radius)

    case 'debug_find_blocks':
      return await debugFindBlocks(args.targets, args.radius)

    case 'debug_collect_drops':
      return await debugCollectDrops(args.targetItems, args.radius)

    case 'scan_for_liquids':
      return scanForLiquids(args.radius)

    case 'scan_for_structures':
      return scanForStructures(args.radius)

    case 'scan_workspace':
      return scanWorkspace()

    case 'drop_item':
      return await dropItem(args.item, args.count, args.force)

    case 'equip_armor':
      return await equipArmorAction(args.mode)

    case 'equip_tool':
      return await equipToolAction(args.block, args.tool)

    case 'select_hotbar_slot':
      return await selectHotbarSlot(args.slot)

    case 'open_chest':
      return await openChest()

    case 'loot_chest':
      return await lootChest(args.priority)

    case 'deposit_items':
      return await depositItems(args.items)

    case 'withdraw_items':
      return await withdrawItems(args.items)

    case 'mark_waypoint':
      return markWaypoint(args.label, args.kind)

    case 'list_waypoints':
      return listWaypoints()

    case 'return_to_waypoint':
      return await returnToWaypoint(args.label)

    case 'return_to_position':
      return await returnToPosition(args.x, args.y, args.z, args.dimension, args.radius)

    case 'set_home_position':
      return setHomePosition()

    case 'recover_death_items':
      return await recoverDeathItems()

    case 'abandon_death_recovery':
      return abandonDeathRecovery()

    case 'return_to_spawn_or_home':
      return await returnToSpawnOrHome()

    case 'flee':
      return await flee()

    case 'eat_food':
      return await eatFood()

    case 'attack_mob':
      return await attackMob(args.mob_type, args.radius)

    case 'attack_nearest_hostile':
      return await attackNearestHostile()

    case 'retreat_from_combat':
      return await retreatFromCombat()

    case 'block_with_shield':
      return await blockWithShield()

    case 'shoot_bow':
      return await shootBow(args.target)

    case 'charge_bow':
      return await chargeBow()

    case 'deflect_ghast_fireball':
      return await deflectGhastFireball()

    case 'kite_mob':
      return await kiteMob()

    case 'throw_ender_pearl':
      return await throwEnderPearl(args.mode)

    case 'kill_passive_mob':
      return await killPassiveMob(args.target)

    case 'kill_blaze':
      return await killBlaze()

    case 'kill_enderman':
      return await killEnderman()

    case 'craft_bed':
      return await craftBed()

    case 'sleep_if_possible':
      return await sleepIfPossible()

    case 'set_spawn_with_bed':
      return await setSpawnWithBed()

    case 'use_bed_bomb':
      return await useBedBomb()

    case 'avoid_bed_explosion':
      return await avoidBedExplosion()

    case 'find_lava_pool':
      return await findLavaPool(args.radius)

    case 'collect_water':
      return await collectWater()

    case 'collect_lava':
      return await collectLava()

    case 'collect_obsidian':
      return await collectObsidian(args.count)

    case 'smelt_item':
      return await smeltItem(args.input, args.fuel, args.count)

    case 'smelt_iron':
      return await smeltIron(args.count)

    case 'build_nether_portal':
      return await buildNetherPortal()

    case 'cast_nether_portal':
      return await castNetherPortal()

    case 'craft_flint_and_steel':
      return await craftFlintAndSteel()

    case 'light_nether_portal':
      return await lightNetherPortal()

    case 'enter_nether':
      return await enterNether()

    case 'return_to_portal':
      return await returnToPortal()

    case 'equip_gold_armor':
      return await equipGoldArmor()

    case 'avoid_opening_chests_near_piglins':
      return avoidOpeningChestsNearPiglins()

    case 'barter_with_piglins':
      return await barterWithPiglins(args.count)

    case 'find_nether_fortress':
      return await findNetherFortress(args.radius)

    case 'navigate_nether_safely':
      return await navigateNetherSafely(args.direction)

    case 'collect_blaze_rods':
      return await collectBlazeRods(args.count)

    case 'retreat_from_nether_danger':
      return await retreatFromNetherDanger()

    case 'leave_nether':
      return await leaveNether()

    case 'craft_eyes_of_ender': return await craftEyesOfEnder(args.count)
    case 'throw_eye_of_ender': return await throwEyeOfEnder()
    case 'locate_stronghold_step': return await locateStrongholdStep()
    case 'dig_staircase_to_stronghold': return await digStaircaseToStronghold()
    case 'scan_for_end_portal_room': return await scanForEndPortalRoom()
    case 'activate_end_portal': return await activateEndPortal()
    case 'enter_end': return await enterEnd()
    case 'end_safe_landing': return await endSafeLanding()
    case 'equip_pumpkin_head': return await equipPumpkinHead()
    case 'look_down_around_endermen': return await lookDownAroundEndermen()
    case 'scan_end_crystals': return scanEndCrystals()
    case 'destroy_end_crystal': return await destroyEndCrystal()
    case 'destroy_caged_end_crystal': return await destroyCagedEndCrystal()
    case 'destroy_nearby_end_crystals': return await destroyNearbyEndCrystals()
    case 'attack_perched_dragon': return await attackPerchedDragon()
    case 'attack_dragon_with_bow': return await attackDragonWithBow()
    case 'dragon_phase_crystals': return await dragonPhaseCrystals()
    case 'dragon_phase_circle': return await dragonPhaseCircle()
    case 'dragon_phase_perch': return await dragonPhasePerch()
    case 'fight_dragon_phase': return await fightDragonPhase()
    case 'return_to_overworld_via_end_portal': return await returnToOverworldViaEndPortal()

    default:
      return fail(action, `Unsupported action: ${action}`)
  }
}

function validateActionRequest(request) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    return { ok: false, error: 'Action request must be an object.' }
  }

  const topLevelUnsupported = Object.keys(request).filter(key => !TOP_LEVEL_ACTION_REQUEST_KEYS.has(key))
  if (topLevelUnsupported.length > 0) {
    return {
      ok: false,
      error: `Action request received unsupported top-level fields: ${topLevelUnsupported.join(', ')}.`,
      unsupportedArgKeys: topLevelUnsupported,
      receivedArgs: request
    }
  }

  if (typeof request.action !== 'string' || request.action.trim() === '') {
    return { ok: false, error: 'Action request requires action as a non-empty string.' }
  }

  return normalizeActionArgs(request.action, request.args)
}

function normalizeActionArgs(action, rawArgs) {
  if (!ACTIONS.has(action)) {
    return { ok: false, error: `Unsupported action: ${action}`, receivedArgs: rawArgs || {} }
  }

  const schema = ACTION_ARG_SCHEMAS[action] || { allowedKeys: [], noArg: true, ignoreKeys: ['count'] }
  const receivedArgs = isPlainObject(rawArgs) ? { ...rawArgs } : {}
  const args = { ...(schema.defaults || {}) }
  const removedArgKeys = []
  const unsupportedArgKeys = []
  const clampedArgs = {}
  const aliases = schema.aliases || {}

  for (const [rawKey, value] of Object.entries(receivedArgs)) {
    const key = aliases[rawKey] || rawKey
    if ((schema.allowedKeys || []).includes(key)) {
      args[key] = value
      if (key !== rawKey) removedArgKeys.push(rawKey)
      continue
    }

    if (shouldIgnoreArg(schema, rawKey, value)) {
      removedArgKeys.push(rawKey)
      continue
    }

    unsupportedArgKeys.push(rawKey)
  }

  if (unsupportedArgKeys.length > 0) {
    return {
      ok: false,
      error: `Action ${action} received unsupported args: ${unsupportedArgKeys.join(', ')}.`,
      unsupportedArgKeys,
      receivedArgs
    }
  }

  const requiredError = validateRequiredArgs(action, args, schema)
  if (requiredError) return { ok: false, error: requiredError, receivedArgs }

  const clampError = applyClampRules(action, args, schema, clampedArgs)
  if (clampError) return { ok: false, error: clampError, receivedArgs }

  const enumError = validateEnumRules(action, args, schema)
  if (enumError) return { ok: false, error: enumError, receivedArgs }

  const stringError = validateStringRules(action, args, schema)
  if (stringError) return { ok: false, error: stringError, receivedArgs }

  const booleanError = validateBooleanRules(action, args, schema)
  if (booleanError) return { ok: false, error: booleanError, receivedArgs }

  const targetError = validateTargetRules(action, args, schema)
  if (targetError) return { ok: false, error: targetError, receivedArgs }

  const itemError = validateItemRules(action, args, schema)
  if (itemError) return { ok: false, error: itemError, receivedArgs }

  const listError = validateListRules(action, args, schema)
  if (listError) return { ok: false, error: listError, receivedArgs }

  if (schema.singleCountItems && schema.singleCountItems.has(args.item) && args.count !== 1) {
    return { ok: false, error: `craft_item args.count must be 1 for ${args.item}.`, receivedArgs }
  }

  if (schema.fuelField && hasOwn(args, schema.fuelField) && args[schema.fuelField] !== undefined && args[schema.fuelField] !== null) {
    const fuel = args[schema.fuelField]
    if (typeof fuel !== 'string' || fuel.trim() === '') {
      return { ok: false, error: `${action} args.${schema.fuelField} must be a non-empty string when provided.`, receivedArgs }
    }
    if (!isAllowedSmeltFuel(fuel)) {
      return { ok: false, error: `${action} fuel '${fuel}' is not allowed.`, receivedArgs }
    }
  }

  return {
    ok: true,
    action,
    args,
    removedArgKeys,
    clampedArgs,
    argsSanitized: removedArgKeys.length > 0 || Object.keys(clampedArgs).length > 0 || (rawArgs !== undefined && rawArgs !== null && !isPlainObject(rawArgs))
  }
}

function shouldIgnoreArg(schema, key, value) {
  if (!(schema.ignoreKeys || []).includes(key)) return false
  if (NO_ARG_HARMLESS_KEYS.has(key)) {
    return value === 1 || value === undefined || value === null
  }
  return true
}

function validateRequiredArgs(action, args, schema) {
  for (const key of schema.required || []) {
    if (!hasOwn(args, key) || args[key] === undefined || args[key] === null || args[key] === '') {
      return `${action} requires args.${key}.`
    }
  }
  return null
}

function applyClampRules(action, args, schema, clampedArgs) {
  for (const [key, rule] of Object.entries(schema.clamp || {})) {
    if (!hasOwn(args, key) || args[key] === undefined || args[key] === null) continue
    const value = args[key]
    if (typeof value !== 'number' || Number.isNaN(value) || (rule.integer && !Number.isInteger(value))) {
      return `${action} args.${key} must be ${rule.integer ? 'an integer' : 'a number'} when provided.`
    }
    const clamped = Math.max(rule.min, Math.min(rule.max, value))
    if (clamped !== value) {
      clampedArgs[key] = { from: value, to: clamped }
      args[key] = clamped
    }
  }
  return null
}

function validateEnumRules(action, args, schema) {
  const nullable = new Set(schema.nullableEnums || [])
  for (const [key, values] of Object.entries(schema.enums || {})) {
    if (!hasOwn(args, key) || args[key] === undefined) continue
    if (args[key] === null && nullable.has(key)) continue
    if (!values.includes(args[key])) {
      return `${action} args.${key} must be one of: ${values.join(', ')}.`
    }
  }
  return null
}

function validateStringRules(action, args, schema) {
  for (const [key, rule] of Object.entries(schema.strings || {})) {
    if (!hasOwn(args, key) || args[key] === undefined || args[key] === null) continue
    if (typeof args[key] !== 'string') return `${action} args.${key} must be a string when provided.`
    const value = args[key]
    if (rule.nonEmpty && value.trim() === '') return `${action} args.${key} must be a non-empty string when provided.`
    if (rule.max && value.length > rule.max) return `${action} args.${key} must be ${rule.max} characters or fewer.`
    if (rule.rejectSlash && value.trimStart().startsWith('/')) return `${action} args.${key} cannot start with /.`
  }
  return null
}

function validateBooleanRules(action, args, schema) {
  for (const key of schema.booleans || []) {
    if (!hasOwn(args, key) || args[key] === undefined) continue
    if (args[key] === 'true')  { args[key] = true;  continue }
    if (args[key] === 'false') { args[key] = false; continue }
    if (typeof args[key] !== 'boolean') return `${action} args.${key} must be a boolean when provided.`
  }
  return null
}

function validateTargetRules(action, args, schema) {
  if (!schema.targets) return null
  const field = schema.targets.field || 'targets'
  const targets = args[field]
  if (!Array.isArray(targets) || (schema.targets.nonEmpty && targets.length === 0)) {
    return `${action} args.${field} must be a non-empty array.`
  }
  if (targets.length > (schema.targets.maxItems || 64)) {
    return `${action} args.${field} must contain at most ${schema.targets.maxItems} entries.`
  }
  for (const target of targets) {
    if (typeof target !== 'string' || target.trim() === '') {
      return `${action} args.${field} entries must be non-empty strings.`
    }
    if (schema.targets.allowed && !schema.targets.allowed.has(target)) {
      return `${action} target is not allowed: ${target}.`
    }
  }
  return null
}

function validateItemRules(action, args, schema) {
  if (!schema.itemValidator) return null
  const item = args.item
  if (typeof item !== 'string' || item.trim() === '') return `${action} requires args.item as a non-empty string.`
  if (schema.itemValidator === 'place_item' && !isAllowedPlaceItem(item)) {
    return `${action} item '${item}' is not allowed.`
  }
  if (schema.itemValidator === 'place_or_pillar_item' && !isAllowedPlaceItem(item) && !PILLAR_BLOCK_NAMES.includes(item)) {
    return `${action} item '${item}' is not allowed.`
  }
  return null
}

function validateListRules(action, args, schema) {
  if (!schema.itemListField) return null
  const items = args[schema.itemListField]
  if (!Array.isArray(items) || items.length === 0) {
    return `${action} args.${schema.itemListField} must be a non-empty array.`
  }
  for (const item of items) {
    if (typeof item !== 'string' || item.trim() === '') {
      return `${action} args.${schema.itemListField} entries must be non-empty strings.`
    }
  }
  return null
}

function attachArgDiagnostics(response, validation) {
  if (!response || typeof response !== 'object') return response
  const debug = process.env.VTUBER_DEBUG_ARGS === '1'
  const removedArgKeys = validation.removedArgKeys || []
  const clampedArgs = validation.clampedArgs || {}
  const changed = validation.argsSanitized || removedArgKeys.length > 0 || Object.keys(clampedArgs).length > 0
  if (!changed && !debug) return response
  const result = response.result && typeof response.result === 'object' ? response.result : {}
  response.result = {
    ...result,
    args_normalized: Boolean(changed),
    removedArgKeys,
    clampedArgs
  }
  return response
}

function isPlainObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
}

function actionHasOnlyArgs(action, args) {
  const allowedArgs = {
    status: [],
    say: ['message'],
    look_around: ['radius'],
    explore_nearby: ['radius'],
    look_at_player: ['username'],
    follow_player: ['username'],
    come_here: ['username'],
    stop: [],
    jump: [],
    set_vtuber_mood: ['mood'],
    acquire_blocks: ['targets', 'count', 'radius', 'allowExcavate', 'accessMode'],
    navigate_to_block_type: ['targets', 'radius'],
    collect_wood: ['count'],
    craft_planks: ['count'],
    craft_sticks: ['count'],
    craft_crafting_table: ['count'],
    place_crafting_table: [],
    craft_item: ['item', 'count'],
    craft_furnace: [],
    craft_torches: ['count'],
    craft_chest: [],
    craft_shield: [],
    craft_bucket: [],
    craft_iron_pickaxe: [],
    craft_iron_sword: [],
    craft_iron_armor: [],
    place_block: ['item', 'mode', 'direction'],
    place_water: ['mode'],
    place_lava: ['mode'],
    place_bed: [],
    place_boat: [],
    place_chest: [],
    place_furnace: ['radius', 'allowPrepareArea'],
    place_torch: [],
    craft_wooden_pickaxe: [],
    mine_stone: ['count'],
    mine_coal: ['count'],
    mine_iron_ore: ['count'],
    craft_stone_pickaxe: [],
    craft_blaze_powder: [],
    craft_diamond_pickaxe: [],
    craft_diamond_sword: [],
    craft_diamond_armor: [],
    equip_best_armor: [],
    equip_best_tool: ['block'],
    equip_best_weapon: [],
    find_safe_workspace: ['radius', 'purpose'],
    setup_workspace: ['need_crafting_table', 'need_furnace', 'need_chest', 'radius'],
    approach_station: ['station', 'radius'],
    dig_staircase: ['direction', 'max_steps'],
    return_to_surface: [],
    pillar_up: ['height', 'block'],
    bridge_gap: ['direction', 'length', 'block'],
    place_block_in_direction: ['item', 'direction'],
    mlg_water_bucket: [],
    enter_boat: [],
    exit_boat: [],
    set_sneak: ['enabled'],
    set_sprint: ['enabled'],
    recover_position: [],
    check_inventory: [],
    check_time_of_day: [],
    check_light_level: [],
    check_biome: [],
    scan_for_hostiles: ['radius'],
    scan_for_passive_mobs: ['radius'],
    scan_for_chests: ['radius'],
    scan_for_specific_block: ['targets', 'radius'],
    scan_for_liquids: ['radius'],
    scan_for_structures: ['radius'],
    scan_workspace: [],
    drop_item: ['item', 'count', 'force'],
    equip_armor: ['mode'],
    equip_tool: ['block', 'tool'],
    select_hotbar_slot: ['slot'],
    open_chest: [],
    loot_chest: ['priority'],
    deposit_items: ['items'],
    withdraw_items: ['items'],
    mark_waypoint: ['label', 'kind'],
    list_waypoints: [],
    return_to_waypoint: ['label'],
    return_to_position: ['x', 'y', 'z', 'dimension', 'radius'],
    set_home_position: [],
    recover_death_items: [],
    abandon_death_recovery: [],
    return_to_spawn_or_home: [],
    flee: [],
    eat_food: [],
    attack_mob: ['mob_type', 'radius'],
    attack_nearest_hostile: [],
    retreat_from_combat: [],
    block_with_shield: [],
    shoot_bow: ['target'],
    charge_bow: [],
    deflect_ghast_fireball: [],
    kite_mob: [],
    throw_ender_pearl: ['mode'],
    kill_passive_mob: ['target'],
    kill_blaze: [],
    kill_enderman: [],
    craft_bed: [],
    sleep_if_possible: [],
    set_spawn_with_bed: [],
    use_bed_bomb: [],
    avoid_bed_explosion: [],
    find_lava_pool: ['radius'],
    collect_water: [],
    collect_lava: [],
    collect_obsidian: ['count'],
    smelt_item: ['input', 'fuel', 'count'],
    smelt_iron: ['count'],
    build_nether_portal: [],
    cast_nether_portal: [],
    craft_flint_and_steel: [],
    light_nether_portal: [],
    enter_nether: [],
    return_to_portal: [],
    equip_gold_armor: [],
    avoid_opening_chests_near_piglins: [],
    barter_with_piglins: ['count'],
    find_nether_fortress: ['radius'],
    navigate_nether_safely: ['direction'],
    collect_blaze_rods: ['count'],
    retreat_from_nether_danger: [],
    leave_nether: [],
    craft_eyes_of_ender: ['count'],
    throw_eye_of_ender: [],
    locate_stronghold_step: [],
    dig_staircase_to_stronghold: [],
    scan_for_end_portal_room: [],
    activate_end_portal: [],
    enter_end: [],
    end_safe_landing: [],
    equip_pumpkin_head: [],
    look_down_around_endermen: [],
    scan_end_crystals: [],
    destroy_end_crystal: [],
    destroy_caged_end_crystal: [],
    destroy_nearby_end_crystals: [],
    attack_perched_dragon: [],
    attack_dragon_with_bow: [],
    dragon_phase_crystals: [],
    dragon_phase_circle: [],
    dragon_phase_perch: [],
    fight_dragon_phase: [],
    return_to_overworld_via_end_portal: [],
  }[action]

  if (allowedArgs === undefined) return Object.keys(args).length === 0
  return Object.keys(args).every((key) => allowedArgs.includes(key))
}

function validateSay(args) {
  if (typeof args.message !== 'string' || args.message.trim() === '') {
    return { ok: false, error: 'say requires args.message as a non-empty string.' }
  }

  if (args.message.length > 240) {
    return { ok: false, error: 'say args.message must be 240 characters or fewer.' }
  }

  if (args.message.trimStart().startsWith('/')) {
    return { ok: false, error: 'Chat commands starting with / are not allowed.' }
  }

  return { ok: true }
}

function validateOptionalUsername(action, args) {
  if (!hasOwn(args, 'username')) {
    return { ok: true }
  }

  if (typeof args.username !== 'string' || args.username.trim() === '') {
    return { ok: false, error: `${action} args.username must be a non-empty string when provided.` }
  }

  if (args.username.length > 32) {
    return { ok: false, error: `${action} args.username must be 32 characters or fewer.` }
  }

  return { ok: true }
}

function validateMood(args) {
  if (!MOODS.has(args.mood)) {
    return { ok: false, error: `set_vtuber_mood args.mood must be one of: ${Array.from(MOODS).join(', ')}.` }
  }

  return { ok: true }
}

function validateCount(args, action, maxCount) {
  if (!hasOwn(args, 'count')) {
    return { ok: true }
  }

  if (!Number.isInteger(args.count)) {
    return { ok: false, error: `${action} args.count must be an integer when provided.` }
  }

  if (args.count < 1 || args.count > maxCount) {
    return { ok: false, error: `${action} args.count must be between 1 and ${maxCount}.` }
  }

  return { ok: true }
}

function validateCraftCount(action, args) {
  if (!hasOwn(args, 'count')) {
    return { ok: true }
  }

  if (!Number.isInteger(args.count)) {
    return { ok: false, error: `${action} args.count must be an integer when provided.` }
  }

  if (args.count < 1 || args.count > CRAFT_MAX_COUNT) {
    return { ok: false, error: `${action} args.count must be between 1 and ${CRAFT_MAX_COUNT}.` }
  }

  return { ok: true }
}

function validateCraftItemArgs(args) {
  const item = args.item
  if (!item || typeof item !== 'string' || item.trim() === '') {
    return { ok: false, error: 'craft_item requires args.item as a non-empty string.' }
  }
  if (!CRAFT_ITEM_ALLOWED_ITEMS.has(item)) {
    return { ok: false, error: `craft_item item '${item}' is not allowed.` }
  }
  if (hasOwn(args, 'count')) {
    const c = validateRange(args, 'craft_item', 'count', 1, CRAFT_MAX_COUNT)
    if (!c.ok) return c
    if (CRAFT_ITEM_SINGLE_COUNT.has(item) && args.count !== 1) {
      return { ok: false, error: `craft_item args.count must be 1 for ${item}.` }
    }
  }
  return { ok: true }
}

function validateSmeltItemArgs(args) {
  const input = args.input
  if (!input || typeof input !== 'string' || input.trim() === '') {
    return { ok: false, error: 'smelt_item requires args.input as a non-empty string.' }
  }
  if (!SMELT_INPUTS[input]) {
    return { ok: false, error: `smelt_item input '${input}' is not allowed.` }
  }
  if (hasOwn(args, 'count')) {
    const c = validateRange(args, 'smelt_item', 'count', 1, SMELT_MAX_COUNT)
    if (!c.ok) return c
  }
  if (hasOwn(args, 'fuel') && args.fuel !== null) {
    if (typeof args.fuel !== 'string' || args.fuel.trim() === '') {
      return { ok: false, error: 'smelt_item args.fuel must be a non-empty string when provided.' }
    }
    if (!isAllowedSmeltFuel(args.fuel)) {
      return { ok: false, error: `smelt_item fuel '${args.fuel}' is not allowed.` }
    }
  }
  return { ok: true }
}

function validateAcquireBlocks(args) {
  if (!Array.isArray(args.targets) || args.targets.length === 0) {
    return { ok: false, error: 'acquire_blocks args.targets must be a non-empty list of allowed block names.' }
  }

  for (const target of args.targets) {
    if (typeof target !== 'string' || !ACQUIRE_ALLOWED_TARGETS.has(target)) {
      return { ok: false, error: `acquire_blocks target is not allowed: ${target}` }
    }
  }

  if (hasOwn(args, 'count')) {
    const countCheck = validateRange(args, 'acquire_blocks', 'count', 1, ACQUIRE_BLOCKS_MAX_COUNT)
    if (!countCheck.ok) return countCheck
  }

  if (hasOwn(args, 'radius')) {
    const radiusCheck = validateRange(args, 'acquire_blocks', 'radius', ACQUIRE_BLOCKS_MIN_RADIUS, ACQUIRE_BLOCKS_MAX_RADIUS)
    if (!radiusCheck.ok) return radiusCheck
  }

  if (hasOwn(args, 'allowExcavate') && typeof args.allowExcavate !== 'boolean') {
    return { ok: false, error: 'acquire_blocks args.allowExcavate must be a boolean when provided.' }
  }

  if (hasOwn(args, 'accessMode') && !ACQUIRE_ACCESS_MODES.has(args.accessMode)) {
    return { ok: false, error: 'acquire_blocks args.accessMode must be surface_first or safe_staircase.' }
  }

  return { ok: true }
}

function validateNavigateToBlockType(args) {
  if (!Array.isArray(args.targets) || args.targets.length === 0) {
    return { ok: false, error: 'navigate_to_block_type args.targets must be a non-empty list of allowed block names.' }
  }

  for (const target of args.targets) {
    if (typeof target !== 'string' || !ACQUIRE_ALLOWED_TARGETS.has(target)) {
      return { ok: false, error: `navigate_to_block_type target is not allowed: ${target}` }
    }
  }

  if (hasOwn(args, 'radius')) {
    return validateRange(args, 'navigate_to_block_type', 'radius', ACQUIRE_BLOCKS_MIN_RADIUS, ACQUIRE_BLOCKS_MAX_RADIUS)
  }

  return { ok: true }
}

function validateRange(args, action, key, minValue, maxValue) {
  if (!hasOwn(args, key)) {
    return { ok: true }
  }

  if (!Number.isInteger(args[key])) {
    return { ok: false, error: `${action} args.${key} must be an integer when provided.` }
  }

  if (args[key] < minValue || args[key] > maxValue) {
    return { ok: false, error: `${action} args.${key} must be between ${minValue} and ${maxValue}.` }
  }

  return { ok: true }
}

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key)
}

function requireReadyBot() {
  if (!bot.player) {
    return 'Bot is not connected yet.'
  }

  if (!bot.entity) {
    return 'Bot has not spawned yet.'
  }

  if (!defaultMovements) {
    return 'Pathfinder movements are not ready yet.'
  }

  return null
}

function findPlayer(username) {
  const player = bot.players[username]
  if (!player || !player.entity) {
    return null
  }

  return player.entity
}

function nearestPlayer() {
  return bot.nearestEntity((entity) => entity.type === 'player' && entity.username !== bot.username)
}

function targetPlayer(username) {
  if (username) {
    return findPlayer(username)
  }

  return nearestPlayer()
}

async function lookAtPlayer(username) {
  const entity = targetPlayer(username)
  if (!entity) {
    return fail('look_at_player', username ? `Player not found: ${username}` : 'No nearby player found.')
  }

  await bot.lookAt(entity.position.offset(0, entity.height || 1.6, 0), true)
  return ok('look_at_player', { username: entity.username })
}

function followPlayer(username) {
  const entity = targetPlayer(username)
  if (!entity) {
    return fail('follow_player', username ? `Player not found: ${username}` : 'No nearby player found.')
  }

  bot.pathfinder.setGoal(new goals.GoalFollow(entity, 3), true)
  return ok('follow_player', { username: entity.username, distance: 3 })
}

function comeHere(username) {
  const entity = targetPlayer(username)
  if (!entity) {
    return fail('come_here', username ? `Player not found: ${username}` : 'No nearby player found.')
  }

  bot.pathfinder.setGoal(new goals.GoalNear(entity.position.x, entity.position.y, entity.position.z, 2))
  return ok('come_here', { username: entity.username, distance: 2 })
}

async function lookAround(requestedRadius) {
  const radius = requestedRadius === undefined ? LOOK_AROUND_DEFAULT_RADIUS : requestedRadius
  const yaw = bot.entity ? bot.entity.yaw : 0
  const pitch = 0

  await bot.look(yaw + Math.PI / 2, pitch, true)
  await delay(150)
  await bot.look(yaw + Math.PI, pitch, true)
  await delay(150)
  await bot.look(yaw + (Math.PI * 3) / 2, pitch, true)
  await delay(150)
  await bot.look(yaw, pitch, true)

  return ok('look_around', {
    radius,
    nearbyPlayers: nearbyPlayersJson(Math.min(radius, 16)),
    nearbyEntities: nearbyEntitiesJson(Math.min(radius, 16)),
    nearbyBlockCounts: nearbyBlockCountsJson(radius, 24)
  })
}

async function exploreNearby(requestedRadius) {
  const radius = requestedRadius === undefined ? EXPLORE_DEFAULT_RADIUS : requestedRadius
  const target = await findSafeExplorePosition(radius)
  if (!target) {
    return fail('explore_nearby', `No safe nearby exploration target found within radius ${radius}.`)
  }

  try {
    await gotoPositionWithTimeout(target, EXPLORE_TIMEOUT_MS)
  } catch (error) {
    return fail('explore_nearby', `Exploration path failed: ${errorMessage(error)}`)
  }

  return ok('explore_nearby', {
    radius,
    target: positionJson(target),
    position: bot.entity ? positionJson(bot.entity.position) : null
  })
}

async function flee() {
  const threat = nearestHostileEntity()
  if (!threat) {
    stopMovement()
    return ok('flee', { fled: false, reason: 'No hostile entity nearby; stopped movement.' })
  }

  const away = bot.entity.position.minus(threat.position)
  const length = Math.sqrt((away.x * away.x) + (away.z * away.z)) || 1
  const target = bot.entity.position.offset(
    (away.x / length) * FLEE_DISTANCE,
    0,
    (away.z / length) * FLEE_DISTANCE
  )

  try {
    await gotoPositionWithTimeout(target, EXPLORE_TIMEOUT_MS)
  } catch (error) {
    return fail('flee', `Flee path failed: ${errorMessage(error)}`)
  }

  return ok('flee', {
    threat: entityJson(threat),
    target: positionJson(target),
    position: bot.entity ? positionJson(bot.entity.position) : null
  })
}

async function eatFood() {
  if (typeof bot.food === 'number' && bot.food >= 20) {
    return ok('eat_food', { eaten: false, reason: 'Food bar is already full.' })
  }

  const foodItem = firstInventoryItemByNames(Array.from(FOOD_ITEM_NAMES))
  if (!foodItem) {
    return fail('eat_food', 'No supported food item found in inventory.')
  }

  try {
    await bot.equip(foodItem, 'hand')
    await consumeWithTimeout(EAT_TIMEOUT_MS)
  } catch (error) {
    return fail('eat_food', `Eating failed: ${errorMessage(error)}`)
  }

  return ok('eat_food', {
    item: foodItem.name,
    food: typeof bot.food === 'number' ? bot.food : null,
    inventory: inventoryJson()
  })
}

// ---------------------------------------------------------------------------
// Combat helpers
// ---------------------------------------------------------------------------

function isPlayer(entity) {
  return entity && (entity.type === 'player' || typeof entity.username === 'string')
}

function inventorySnapshot() {
  const snap = {}
  for (const item of inventoryJson()) {
    snap[item.name] = (snap[item.name] || 0) + item.count
  }
  return snap
}

function inventoryDiff(before) {
  const after = {}
  for (const item of inventoryJson()) {
    after[item.name] = (after[item.name] || 0) + item.count
  }
  const gained = {}
  for (const [name, count] of Object.entries(after)) {
    const diff = count - (before[name] || 0)
    if (diff > 0) gained[name] = diff
  }
  return gained
}

function refreshEntity(entity) {
  if (!entity || !bot.entities) return null
  return bot.entities[entity.id] || null
}

function waitMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function equipBestMeleeWeapon() {
  const sword = firstInventoryItemByNames(SWORD_PRIORITY)
  const axe = firstInventoryItemByNames(AXE_PRIORITY)
  const weapon = sword || axe
  if (!weapon) return Promise.resolve(null)
  return withTimeout(bot.equip(weapon, 'hand'), EQUIP_TIMEOUT_MS, `equipping ${weapon.name}`).then(() => weapon)
}

function hasBowAndArrows() {
  return Boolean(
    firstInventoryItemByNames(['bow']) &&
    firstInventoryItemByNames(['arrow', 'tipped_arrow', 'spectral_arrow'])
  )
}

function findEndCrystals(radius) {
  if (!bot.entity || !bot.entities) return []
  return Object.values(bot.entities)
    .filter((entity) => {
      if (!entity || entity === bot.entity || !entity.position) return false
      const name = String(entity.name || entity.displayName || entity.type || '').toLowerCase()
      return name.includes('crystal') && bot.entity.position.distanceTo(entity.position) <= radius
    })
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))
}

function findEnderDragon() {
  if (!bot.entity || !bot.entities) return null
  return Object.values(bot.entities)
    .filter((entity) => {
      if (!entity || entity === bot.entity || !entity.position) return false
      const name = String(entity.name || entity.displayName || entity.type || '').toLowerCase()
      return name.includes('dragon')
    })
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null
}

function findNearbyEndermen(radius) {
  if (!bot.entity || !bot.entities) return []
  return Object.values(bot.entities)
    .filter((entity) =>
      entity && entity !== bot.entity && entity.position &&
      String(entity.name || entity.displayName || entity.type || '').toLowerCase() === 'enderman' &&
      bot.entity.position.distanceTo(entity.position) <= radius
    )
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))
}

function isEndCrystalCaged(entity) {
  if (!entity || !entity.position) return 'unconfirmed'
  const bars = findIronBarsAround(entity.position, 3)
  return bars.length > 0
}

function findIronBarsAround(position, radius) {
  const bars = []
  const center = position.floored()
  for (let dx = -radius; dx <= radius; dx++) {
    for (let dy = -radius; dy <= radius; dy++) {
      for (let dz = -radius; dz <= radius; dz++) {
        const block = bot.blockAt(center.offset(dx, dy, dz))
        if (block && block.name === 'iron_bars') bars.push(block)
      }
    }
  }
  return bars
}

function endCrystalJson(entity) {
  const caged = isEndCrystalCaged(entity)
  return {
    ...entityJson(entity),
    caged,
    line_of_sight: canSeeEntitySafe(entity),
    explosion_danger: bot.entity && entity.position
      ? bot.entity.position.distanceTo(entity.position) < END_CRYSTAL_DANGER_RADIUS
      : null,
  }
}

function canSeeEntitySafe(entity) {
  if (!entity) return false
  if (typeof bot.canSeeEntity === 'function') {
    try { return Boolean(bot.canSeeEntity(entity)) } catch (_) {}
  }
  return bot.entity && entity.position && bot.entity.position.distanceTo(entity.position) <= END_DRAGON_BOW_RANGE
}

async function shootEntityWithBow(action, entity) {
  if (!bot.entity) return fail(action, 'Bot not ready.')

  const bow = firstInventoryItemByNames(['bow'])
  if (!bow) return fail(action, 'No bow in inventory.')
  const arrows = firstInventoryItemByNames(['arrow', 'tipped_arrow', 'spectral_arrow'])
  if (!arrows) return fail(action, 'No arrows in inventory.')

  try {
    await bot.lookAt(entity.position.offset(0, (entity.height || 1.0) / 2, 0), true)
    await withTimeout(bot.equip(bow, 'hand'), EQUIP_TIMEOUT_MS, 'equipping bow')
    bot.activateItem()
    await waitMs(BOW_CHARGE_MS)
    bot.deactivateItem()
    await waitMs(600)
  } catch (err) {
    try { bot.deactivateItem() } catch (_) {}
    return fail(action, `Bow shot failed: ${errorMessage(err)}`, { target: entityJson(entity) })
  }

  return ok(action, {
    shot: true,
    target: entityJson(entity),
    health: typeof bot.health === 'number' ? bot.health : null,
  })
}

function finalizeCrystalDestroy(action, target, innerResult) {
  const stillThere = Boolean(refreshEntity(target))
  return ok(action, {
    destroyed: !stillThere,
    partial_success: true,
    can_retry: stillThere,
    target: endCrystalJson(target),
    inner_result: innerResult.result,
    suggested_next_action: stillThere ? 'scan_end_crystals' : 'destroy_nearby_end_crystals',
  })
}

async function retreatFromPosition(position, distance) {
  if (!bot.entity || !position) return false
  const away = bot.entity.position.minus(position)
  const length = Math.sqrt(away.x * away.x + away.z * away.z) || 1
  const target = bot.entity.position.offset((away.x / length) * distance, 0, (away.z / length) * distance)
  try {
    await gotoPositionWithTimeout(target, 5000)
    return true
  } catch (_) {
    stopMovement()
    return false
  }
}

function horizontalDistance(a, b) {
  const dx = a.x - b.x
  const dz = a.z - b.z
  return Math.sqrt(dx * dx + dz * dz)
}

function cardinalDirectionToward(from, to) {
  const dx = to.x - from.x
  const dz = to.z - from.z
  if (Math.abs(dx) > Math.abs(dz)) return dx > 0 ? 'east' : 'west'
  return dz > 0 ? 'south' : 'north'
}

function isObsidianPlatformFloor(block) {
  return Boolean(block && block.name === 'obsidian')
}

function findNearestEndIslandStand(radius) {
  if (!bot.entity) return null
  const endStoneId = bot.registry.blocksByName.end_stone?.id
  if (!endStoneId) return null
  const blocks = bot.findBlocks({ matching: endStoneId, maxDistance: radius, count: 32 })
  return blocks
    .map((pos) => ({ block: bot.blockAt(pos), position: pos.offset(0, 1, 0) }))
    .filter((candidate) => candidate.block && isSafeStandPosition(candidate.position))
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null
}

function isDragonLikelyPerched(dragon) {
  if (!dragon || !dragon.position) return false
  const originDistance = Math.sqrt(dragon.position.x * dragon.position.x + dragon.position.z * dragon.position.z)
  return originDistance <= END_PERCH_RADIUS && dragon.position.y <= 90
}

async function handleEndSurvivalPreflight(action) {
  if (!bot.entity) return fail(action, 'Bot not ready.')

  if (bot.entity.position.y <= END_VOID_MIN_Y) {
    return fail(action, 'Bot is at void danger height in The End.', {
      suggested_next_action: 'recover_position',
    })
  }

  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) {
    const food = firstInventoryItemByNames(Array.from(FOOD_ITEM_NAMES))
    if (food) {
      const eat = await eatFood()
      return ok(action, {
        survival_action: 'eat_food',
        partial_success: eat.ok,
        inner_result: eat.result,
        suggested_next_action: 'fight_dragon_phase',
      })
    }
    return fail(action, `Health too low (${bot.health}).`, {
      suggested_next_action: 'retreat_from_combat',
    })
  }

  return null
}

// ---------------------------------------------------------------------------
// Combat actions
// ---------------------------------------------------------------------------

async function attackMob(mobType, radius) {
  if (!bot.entity) return fail('attack_mob', 'Bot not ready.')

  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) {
    return fail('attack_mob', `Health too low (${bot.health}). Use eat_food or retreat_from_combat first.`)
  }

  const safeRadius = Math.min(64, Math.max(4, Number(radius) || 24))

  let target = null
  if (mobType) {
    target = Object.values(bot.entities)
      .filter((e) =>
        e && e !== bot.entity && e.position &&
        e.name === mobType &&
        !isPlayer(e) &&
        bot.entity.position.distanceTo(e.position) <= safeRadius
      )
      .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null
  } else {
    target = nearestHostileEntity()
  }

  if (!target) {
    return fail('attack_mob', `No target${mobType ? ` '${mobType}'` : ''} found within radius ${safeRadius}.`)
  }

  try { await equipBestMeleeWeapon() } catch (_) {}

  const snap = inventorySnapshot()
  const started = Date.now()
  let killed = false

  try {
    while (Date.now() - started < ATTACK_DURATION_MS) {
      const current = refreshEntity(target)
      if (!current) { killed = true; break }

      if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break

      const dist = bot.entity.position.distanceTo(current.position)
      if (dist > 3.5) {
        bot.pathfinder.setGoal(new goals.GoalNear(current.position.x, current.position.y, current.position.z, 2), true)
        await waitMs(300)
      } else {
        bot.pathfinder.setGoal(null)
        try { await withTimeout(bot.attack(current), 1000, 'attack swing') } catch (_) {}
        await waitMs(600)
      }
    }
  } catch (err) {
    stopMovement()
    return fail('attack_mob', `Attack loop failed: ${errorMessage(err)}`)
  }

  stopMovement()
  const drops = inventoryDiff(snap)
  return ok('attack_mob', {
    target: mobType || (target.name || 'hostile'),
    killed,
    drops,
    health: typeof bot.health === 'number' ? bot.health : null,
    duration_ms: Date.now() - started,
  })
}

async function attackNearestHostile() {
  if (!bot.entity) return fail('attack_nearest_hostile', 'Bot not ready.')

  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) {
    return fail('attack_nearest_hostile', 'Health too low. Use retreat_from_combat or eat_food first.')
  }

  const hostile = nearestHostileEntity()
  if (!hostile) return fail('attack_nearest_hostile', 'No hostile entity nearby.')

  if (hostile.name === 'creeper') {
    const dist = bot.entity.position.distanceTo(hostile.position)
    if (dist < CREEPER_DANGER_RADIUS) {
      return fail('attack_nearest_hostile', `Creeper within explosion range (${dist.toFixed(1)}m). Use retreat_from_combat first.`)
    }
  }

  return attackMob(hostile.name, 32)
}

async function retreatFromCombat() {
  if (!bot.entity) return fail('retreat_from_combat', 'Bot not ready.')

  const threat = nearestHostileEntity()
  if (!threat) {
    stopMovement()
    return ok('retreat_from_combat', { retreated: false, reason: 'No hostile nearby.' })
  }

  const away = bot.entity.position.minus(threat.position)
  const length = Math.sqrt(away.x * away.x + away.z * away.z) || 1
  const retreatTarget = bot.entity.position.offset(
    (away.x / length) * COMBAT_RETREAT_DISTANCE,
    0,
    (away.z / length) * COMBAT_RETREAT_DISTANCE
  )

  try {
    await gotoPositionWithTimeout(retreatTarget, EXPLORE_TIMEOUT_MS)
  } catch (_) {}

  stopMovement()
  return ok('retreat_from_combat', {
    threat: entityJson(threat),
    position: bot.entity ? positionJson(bot.entity.position) : null,
    distance_from_threat: bot.entity ? bot.entity.position.distanceTo(threat.position) : null,
  })
}

async function blockWithShield() {
  if (!bot.entity) return fail('block_with_shield', 'Bot not ready.')

  const shield = firstInventoryItemByNames(['shield'])
  if (!shield) return fail('block_with_shield', 'No shield in inventory.')

  try {
    await withTimeout(bot.equip(shield, 'off-hand'), EQUIP_TIMEOUT_MS, 'equipping shield to offhand')
  } catch (err) {
    return fail('block_with_shield', `Could not equip shield: ${errorMessage(err)}`)
  }

  try {
    bot.activateItem(true)
    await waitMs(SHIELD_HOLD_MS)
    bot.deactivateItem()
  } catch (err) {
    try { bot.deactivateItem() } catch (_) {}
    return fail('block_with_shield', `Shield block failed: ${errorMessage(err)}`)
  }

  return ok('block_with_shield', { held_ms: SHIELD_HOLD_MS })
}

async function shootBow(targetType) {
  if (!bot.entity) return fail('shoot_bow', 'Bot not ready.')

  const bow = firstInventoryItemByNames(['bow'])
  if (!bow) return fail('shoot_bow', 'No bow in inventory.')

  const arrows = firstInventoryItemByNames(['arrow', 'tipped_arrow', 'spectral_arrow'])
  if (!arrows) return fail('shoot_bow', 'No arrows in inventory.')

  let target = null
  if (targetType) {
    target = Object.values(bot.entities)
      .filter((e) => e && e !== bot.entity && e.position && e.name === targetType && !isPlayer(e))
      .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null
  }
  if (!target) target = nearestHostileEntity()

  if (target) {
    try { await bot.lookAt(target.position.offset(0, (target.height || 1.8) / 2, 0)) } catch (_) {}
  }

  const snap = inventorySnapshot()

  try {
    await withTimeout(bot.equip(bow, 'hand'), EQUIP_TIMEOUT_MS, 'equipping bow')
    bot.activateItem()
    await waitMs(BOW_CHARGE_MS)
    bot.deactivateItem()
    await waitMs(400)
  } catch (err) {
    try { bot.deactivateItem() } catch (_) {}
    return fail('shoot_bow', `Bow shot failed: ${errorMessage(err)}`)
  }

  const drops = inventoryDiff(snap)
  return ok('shoot_bow', {
    bow: bow.name,
    target: target ? (target.name || 'entity') : null,
    drops,
    health: typeof bot.health === 'number' ? bot.health : null,
  })
}

async function chargeBow() {
  if (!bot.entity) return fail('charge_bow', 'Bot not ready.')

  const bow = firstInventoryItemByNames(['bow'])
  if (!bow) return fail('charge_bow', 'No bow in inventory.')

  try {
    await withTimeout(bot.equip(bow, 'hand'), EQUIP_TIMEOUT_MS, 'equipping bow')
    bot.activateItem()
  } catch (err) {
    return fail('charge_bow', `Could not charge bow: ${errorMessage(err)}`)
  }

  return ok('charge_bow', { charged: true, bow: bow.name })
}

async function deflectGhastFireball() {
  if (!bot.entity) return fail('deflect_ghast_fireball', 'Bot not ready.')

  const FIREBALL_NAMES = new Set(['ghast_fireball', 'fireball', 'small_fireball', 'wind_charge'])
  const fireball = Object.values(bot.entities)
    .filter((e) =>
      e && e !== bot.entity && e.position &&
      (FIREBALL_NAMES.has(e.name) || FIREBALL_NAMES.has(e.displayName)) &&
      bot.entity.position.distanceTo(e.position) <= 16
    )
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null

  if (!fireball) {
    return fail('deflect_ghast_fireball', 'No ghast fireball detected within 16 blocks.')
  }

  try {
    await bot.lookAt(fireball.position)
    await withTimeout(bot.attack(fireball), 2000, 'deflecting fireball')
  } catch (err) {
    return fail('deflect_ghast_fireball', `Failed to deflect fireball: ${errorMessage(err)}`)
  }

  return ok('deflect_ghast_fireball', { fireball: entityJson(fireball), deflected: true })
}

async function kiteMob() {
  if (!bot.entity) return fail('kite_mob', 'Bot not ready.')

  const hostile = nearestHostileEntity()
  if (!hostile) return fail('kite_mob', 'No hostile mob to kite.')

  try { await equipBestMeleeWeapon() } catch (_) {}

  const snap = inventorySnapshot()
  const started = Date.now()
  let killed = false

  try {
    while (Date.now() - started < KITE_DURATION_MS) {
      const current = refreshEntity(hostile)
      if (!current) { killed = true; break }

      if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break

      const dist = bot.entity.position.distanceTo(current.position)
      try { await bot.lookAt(current.position) } catch (_) {}

      if (dist <= 3) {
        const away = bot.entity.position.minus(current.position)
        const len = Math.sqrt(away.x * away.x + away.z * away.z) || 1
        const backPos = bot.entity.position.offset((away.x / len) * 4, 0, (away.z / len) * 4)
        bot.pathfinder.setGoal(new goals.GoalNear(backPos.x, backPos.y, backPos.z, 1), true)
        try { await withTimeout(bot.attack(current), 1000, 'kite attack') } catch (_) {}
        await waitMs(600)
      } else if (dist <= 6) {
        bot.pathfinder.setGoal(null)
        try { await withTimeout(bot.attack(current), 1000, 'kite attack') } catch (_) {}
        await waitMs(600)
      } else {
        bot.pathfinder.setGoal(new goals.GoalNear(current.position.x, current.position.y, current.position.z, 3), true)
        await waitMs(300)
      }
    }
  } catch (err) {
    stopMovement()
    return fail('kite_mob', `Kite loop failed: ${errorMessage(err)}`)
  }

  stopMovement()
  const drops = inventoryDiff(snap)
  return ok('kite_mob', {
    target: hostile.name || 'hostile',
    killed,
    drops,
    health: typeof bot.health === 'number' ? bot.health : null,
    duration_ms: Date.now() - started,
  })
}

async function throwEnderPearl(mode) {
  if (!bot.entity) return fail('throw_ender_pearl', 'Bot not ready.')

  const pearl = firstInventoryItemByNames(['ender_pearl'])
  if (!pearl) return fail('throw_ender_pearl', 'No ender pearl in inventory.')

  const safeMode = ENDER_PEARL_MODES.has(mode) ? mode : 'forward'
  const beforePos = positionJson(bot.entity.position)

  try {
    await withTimeout(bot.equip(pearl, 'hand'), EQUIP_TIMEOUT_MS, 'equipping ender pearl')
  } catch (err) {
    return fail('throw_ender_pearl', `Could not equip ender pearl: ${errorMessage(err)}`)
  }

  if (safeMode === 'escape') {
    const threat = nearestHostileEntity()
    if (threat) {
      const away = bot.entity.position.minus(threat.position)
      const len = Math.sqrt(away.x * away.x + away.z * away.z) || 1
      const lookTarget = bot.entity.position.offset((away.x / len) * 20, 4, (away.z / len) * 20)
      try { await bot.lookAt(lookTarget) } catch (_) {}
    }
  } else if (safeMode === 'toward_target') {
    const hostile = nearestHostileEntity()
    if (hostile) {
      try { await bot.lookAt(hostile.position) } catch (_) {}
    }
  }

  try {
    bot.activateItem()
    await waitMs(PEARL_TIMEOUT_MS)
  } catch (_) {}

  await waitMs(800)

  return ok('throw_ender_pearl', {
    mode: safeMode,
    before: beforePos,
    after: bot.entity ? positionJson(bot.entity.position) : null,
    health: typeof bot.health === 'number' ? bot.health : null,
  })
}

const KILLABLE_PASSIVE_MOBS = new Set(['cow', 'pig', 'sheep', 'chicken', 'rabbit'])

async function killPassiveMob(targetType) {
  if (!bot.entity) return fail('kill_passive_mob', 'Bot not ready.')

  const allowedTypes = targetType
    ? (KILLABLE_PASSIVE_MOBS.has(targetType) ? [targetType] : [targetType])
    : Array.from(KILLABLE_PASSIVE_MOBS)

  const mob = Object.values(bot.entities)
    .filter((e) =>
      e && e !== bot.entity && e.position &&
      allowedTypes.includes(e.name) &&
      !isPlayer(e) &&
      bot.entity.position.distanceTo(e.position) <= 32
    )
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null

  if (!mob) {
    return fail('kill_passive_mob', `No ${targetType || 'killable passive'} mob found within 32 blocks.`)
  }

  try { await equipBestMeleeWeapon() } catch (_) {}

  const snap = inventorySnapshot()
  const started = Date.now()
  let killed = false

  try {
    while (Date.now() - started < ATTACK_DURATION_MS) {
      const current = refreshEntity(mob)
      if (!current) { killed = true; break }

      const dist = bot.entity.position.distanceTo(current.position)
      if (dist > 3) {
        bot.pathfinder.setGoal(new goals.GoalNear(current.position.x, current.position.y, current.position.z, 2), true)
        await waitMs(300)
      } else {
        bot.pathfinder.setGoal(null)
        try { await withTimeout(bot.attack(current), 1000, 'attack passive mob') } catch (_) {}
        await waitMs(600)
      }
    }
  } catch (err) {
    stopMovement()
    return fail('kill_passive_mob', `Attack failed: ${errorMessage(err)}`)
  }

  stopMovement()
  await waitMs(600)
  const drops = inventoryDiff(snap)
  return ok('kill_passive_mob', {
    target: mob.name,
    killed,
    drops,
  })
}

async function killBlaze() {
  if (!bot.entity) return fail('kill_blaze', 'Bot not ready.')

  const blaze = Object.values(bot.entities)
    .filter((e) =>
      e && e !== bot.entity && e.position &&
      e.name === 'blaze' &&
      bot.entity.position.distanceTo(e.position) <= 32
    )
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null

  if (!blaze) return fail('kill_blaze', 'No blaze found within 32 blocks.')

  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) {
    return fail('kill_blaze', `Health too low (${bot.health}). Retreat first.`)
  }

  const bow = firstInventoryItemByNames(['bow'])
  const arrows = firstInventoryItemByNames(['arrow', 'tipped_arrow'])
  const snap = inventorySnapshot()
  const started = Date.now()
  let killed = false

  if (bow && arrows) {
    try { await withTimeout(bot.equip(bow, 'hand'), EQUIP_TIMEOUT_MS, 'equipping bow') } catch (_) {}

    while (Date.now() - started < COMBAT_TIMEOUT_MS) {
      const current = refreshEntity(blaze)
      if (!current) { killed = true; break }

      if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break

      const dist = bot.entity.position.distanceTo(current.position)
      try { await bot.lookAt(current.position.offset(0, (current.height || 1.8) / 2, 0)) } catch (_) {}

      if (dist < 6) {
        const away = bot.entity.position.minus(current.position)
        const len = Math.sqrt(away.x * away.x + away.z * away.z) || 1
        const back = bot.entity.position.offset((away.x / len) * 5, 0, (away.z / len) * 5)
        bot.pathfinder.setGoal(new goals.GoalNear(back.x, back.y, back.z, 1), true)
        await waitMs(300)
      } else if (dist <= 20) {
        bot.pathfinder.setGoal(null)
        bot.activateItem()
        await waitMs(BOW_CHARGE_MS)
        try { bot.deactivateItem() } catch (_) {}
        await waitMs(600)
      } else {
        bot.pathfinder.setGoal(new goals.GoalNear(current.position.x, current.position.y, current.position.z, 8), true)
        await waitMs(300)
      }
    }
  } else {
    try { await equipBestMeleeWeapon() } catch (_) {}

    while (Date.now() - started < COMBAT_TIMEOUT_MS) {
      const current = refreshEntity(blaze)
      if (!current) { killed = true; break }

      if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break

      const dist = bot.entity.position.distanceTo(current.position)
      if (dist > 3) {
        bot.pathfinder.setGoal(new goals.GoalNear(current.position.x, current.position.y, current.position.z, 2), true)
        await waitMs(300)
      } else {
        bot.pathfinder.setGoal(null)
        try { await withTimeout(bot.attack(current), 1000, 'melee blaze') } catch (_) {}
        await waitMs(600)
      }
    }
  }

  stopMovement()
  try { bot.deactivateItem() } catch (_) {}
  await waitMs(1000)
  const drops = inventoryDiff(snap)
  return ok('kill_blaze', {
    killed,
    blaze_rods: drops.blaze_rod || 0,
    drops,
    health: typeof bot.health === 'number' ? bot.health : null,
  })
}

async function killEnderman() {
  if (!bot.entity) return fail('kill_enderman', 'Bot not ready.')

  const enderman = Object.values(bot.entities)
    .filter((e) =>
      e && e !== bot.entity && e.position &&
      e.name === 'enderman' &&
      bot.entity.position.distanceTo(e.position) <= 32
    )
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null

  if (!enderman) return fail('kill_enderman', 'No enderman found within 32 blocks.')

  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) {
    return fail('kill_enderman', `Health too low (${bot.health}). Retreat first.`)
  }

  try { await equipBestMeleeWeapon() } catch (_) {}

  // Look at feet to avoid triggering teleport via eye contact
  try { await bot.lookAt(enderman.position) } catch (_) {}

  const snap = inventorySnapshot()
  const started = Date.now()
  let killed = false

  try {
    while (Date.now() - started < COMBAT_TIMEOUT_MS) {
      const current = refreshEntity(enderman)
      if (!current) { killed = true; break }

      if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break

      const dist = bot.entity.position.distanceTo(current.position)
      if (dist > 3) {
        bot.pathfinder.setGoal(new goals.GoalNear(current.position.x, current.position.y, current.position.z, 2), true)
        await waitMs(300)
      } else {
        bot.pathfinder.setGoal(null)
        try { await withTimeout(bot.attack(current), 1000, 'attack enderman') } catch (_) {}
        await waitMs(600)
      }
    }
  } catch (err) {
    stopMovement()
    return fail('kill_enderman', `Attack failed: ${errorMessage(err)}`)
  }

  stopMovement()
  await waitMs(1000)
  const drops = inventoryDiff(snap)
  return ok('kill_enderman', {
    killed,
    ender_pearls: drops.ender_pearl || 0,
    drops,
    health: typeof bot.health === 'number' ? bot.health : null,
  })
}

// ---------------------------------------------------------------------------
// Bed actions
// ---------------------------------------------------------------------------

function findNearbyBedBlock(radius) {
  if (!bot.entity || !bot.registry) return null
  const bedTypeIds = new Set(
    [...BED_ITEM_NAMES].map((n) => {
      const blockName = n // item name matches block name for beds
      return bot.registry.blocksByName[blockName]?.id
    }).filter(Boolean)
  )
  return bot.findBlock({ matching: (b) => bedTypeIds.has(b.type), maxDistance: radius }) || null
}

async function craftBed() {
  if (!bot.entity) return fail('craft_bed', 'Bot not ready.')

  // Find which wool color we have ≥3 of
  let woolName = null
  let plankName = null
  for (const color of WOOL_COLORS) {
    const name = `${color}_wool`
    if (countItemInInventory(name) >= 3) { woolName = name; break }
  }
  if (!woolName) {
    const allWool = WOOL_COLORS.map((c) => `${c}_wool`)
    const counts = Object.fromEntries(allWool.map((n) => [n, countItemInInventory(n)]))
    return fail('craft_bed', 'Need at least 3 wool of the same color.', { wool_counts: counts })
  }
  for (const name of PLANK_ITEM_NAMES) {
    if (countItemInInventory(name) >= 3) { plankName = name; break }
  }
  if (!plankName) {
    return fail('craft_bed', 'Need at least 3 planks of any type.')
  }

  let table = findNearbyCraftingTable(STATION_USE_RADIUS)
  if (!table) {
    return noCraftingTableFail('craft_bed')
  }

  // Navigate to table
  try {
    await gotoPositionWithTimeout(table.position, EXPLORE_TIMEOUT_MS)
  } catch (_) {}

  const woolItem = bot.inventory.items().find((i) => i.name === woolName)
  const plankItem = bot.inventory.items().find((i) => i.name === plankName)
  if (!woolItem || !plankItem) return fail('craft_bed', 'Items disappeared from inventory.')

  // Determine resulting bed item name (e.g. white_wool → white_bed)
  const color = woolName.replace('_wool', '')
  const bedName = `${color}_bed`

  const recipe = bot.recipesFor(bot.registry.itemsByName[bedName]?.id, null, 1, table)?.[0]
  if (!recipe) return fail('craft_bed', `No recipe found for ${bedName}.`)

  try {
    await craftWithTimeout(recipe, 1, table)
  } catch (err) {
    return fail('craft_bed', `Crafting failed: ${errorMessage(err)}`)
  }

  return ok('craft_bed', { bed: bedName, count: countItemInInventory(bedName) })
}

async function sleepIfPossible() {
  if (!bot.entity) return fail('sleep_if_possible', 'Bot not ready.')

  const dim = getBotDimension()
  if (!dim.includes('overworld')) {
    return fail('sleep_if_possible', `Cannot sleep in ${dim} — beds explode outside the Overworld.`)
  }

  const tod = bot.time?.timeOfDay ?? 0
  if (tod < SLEEP_NIGHT_THRESHOLD && tod > 450) {
    // timeOfDay 450 = just after sunrise; wrap-around handles midnight rollover
    return fail('sleep_if_possible', `Not night yet (timeOfDay=${tod}). Wait until ${SLEEP_NIGHT_THRESHOLD}.`)
  }

  // Find a nearby bed block or place one
  let bed = findNearbyBedBlock(6)
  if (!bed) {
    const bedItem = [...BED_ITEM_NAMES].find((n) => countItemInInventory(n) > 0)
    if (!bedItem) return fail('sleep_if_possible', 'No bed in inventory and none nearby.')
    const item = bot.inventory.items().find((i) => i.name === bedItem)
    if (!item) return fail('sleep_if_possible', 'Bed item not found in inventory.')

    const candidates = findBedPlacementCandidates()
    if (!candidates.length) return fail('sleep_if_possible', 'No valid spot to place bed.')
    const { pos, face } = candidates[0]
    const refBlock = bot.blockAt(pos.minus(face))
    if (!refBlock) return fail('sleep_if_possible', 'Cannot determine placement reference block.')

    try {
      await withTimeout(bot.equip(item, 'hand'), EQUIP_TIMEOUT_MS, 'equip bed')
      await withTimeout(bot.placeBlock(refBlock, face), PLACE_TIMEOUT_MS, 'place bed')
      await waitMs(PLACE_VERIFY_MS)
    } catch (err) {
      return fail('sleep_if_possible', `Failed to place bed: ${errorMessage(err)}`)
    }

    bed = findNearbyBedBlock(8)
    if (!bed) return fail('sleep_if_possible', 'Placed bed but could not locate block.')
  }

  try {
    await gotoPositionWithTimeout(bed.position, EXPLORE_TIMEOUT_MS)
  } catch (_) {}

  try {
    await withTimeout(bot.sleep(bed), SLEEP_TIMEOUT_MS, 'sleep')
  } catch (err) {
    return fail('sleep_if_possible', `Sleep failed: ${errorMessage(err)}`)
  }

  return ok('sleep_if_possible', { slept: true, timeOfDay: bot.time?.timeOfDay ?? null })
}

async function setSpawnWithBed() {
  if (!bot.entity) return fail('set_spawn_with_bed', 'Bot not ready.')

  const dim = getBotDimension()
  if (!dim.includes('overworld')) {
    return fail('set_spawn_with_bed', `Cannot set spawn with bed in ${dim}.`)
  }

  // Find or place a bed
  let bed = findNearbyBedBlock(8)
  if (!bed) {
    const bedItem = [...BED_ITEM_NAMES].find((n) => countItemInInventory(n) > 0)
    if (!bedItem) return fail('set_spawn_with_bed', 'No bed nearby and none in inventory.')
    const item = bot.inventory.items().find((i) => i.name === bedItem)
    if (!item) return fail('set_spawn_with_bed', 'Bed item missing from inventory.')

    const candidates = findBedPlacementCandidates()
    if (!candidates.length) return fail('set_spawn_with_bed', 'No valid spot to place bed.')
    const { pos, face } = candidates[0]
    const refBlock = bot.blockAt(pos.minus(face))
    if (!refBlock) return fail('set_spawn_with_bed', 'Cannot determine placement reference block.')

    try {
      await withTimeout(bot.equip(item, 'hand'), EQUIP_TIMEOUT_MS, 'equip bed')
      await withTimeout(bot.placeBlock(refBlock, face), PLACE_TIMEOUT_MS, 'place bed')
      await waitMs(PLACE_VERIFY_MS)
    } catch (err) {
      return fail('set_spawn_with_bed', `Failed to place bed: ${errorMessage(err)}`)
    }

    bed = findNearbyBedBlock(10)
    if (!bed) return fail('set_spawn_with_bed', 'Placed bed but could not locate block.')
  }

  try {
    await gotoPositionWithTimeout(bed.position, EXPLORE_TIMEOUT_MS)
  } catch (_) {}

  // Activate (right-click) the bed to set spawn — works even during day
  try {
    await withTimeout(bot.activateBlock(bed), 5000, 'activate bed')
  } catch (err) {
    // Activation may throw if the bot can't sleep right now; that's OK — spawn is still set
    // if the block interaction packet was accepted.
  }

  await waitMs(1000)
  const pos = bot.entity.position
  markWaypoint('spawn_bed', 'bed')

  return ok('set_spawn_with_bed', { spawn_set: true, position: positionJson(pos) })
}

async function useBedBomb() {
  if (!bot.entity) return fail('use_bed_bomb', 'Bot not ready.')

  const dim = getBotDimension()
  if (!dim.includes('the_end')) {
    return fail('use_bed_bomb', `Bed bomb only works in The End (currently in ${dim}).`)
  }

  // Require a bed in inventory
  const bedItem = [...BED_ITEM_NAMES].find((n) => countItemInInventory(n) > 0)
  if (!bedItem) return fail('use_bed_bomb', 'No bed in inventory.')
  const item = bot.inventory.items().find((i) => i.name === bedItem)
  if (!item) return fail('use_bed_bomb', 'Bed item not found in inventory.')

  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD + 4) {
    return fail('use_bed_bomb', `Health too low (${bot.health}) — bed bomb is suicidal at this health.`)
  }

  const candidates = findBedPlacementCandidates()
  if (!candidates.length) return fail('use_bed_bomb', 'No valid spot to place bed for bomb.')
  const candidate = candidates[0]
  const pos = candidate.placePosition || candidate.pos
  const face = candidate.faceVector || candidate.face || new Vec3(0, 1, 0)
  const refBlock = candidate.referenceBlock || bot.blockAt(pos.minus(face))
  if (!refBlock) return fail('use_bed_bomb', 'Cannot determine bed placement reference block.')

  // Retreat to safe distance BEFORE placing to survive the explosion
  const dragon = findEnderDragon()
  const retreatDir = dragon && dragon.position
    ? bot.entity.position.minus(dragon.position)
    : (candidate.headDirection || new Vec3(1, 0, 0))
  const retreatLen = Math.sqrt(retreatDir.x * retreatDir.x + retreatDir.z * retreatDir.z) || 1
  const safePos = bot.entity.position.offset(
    (retreatDir.x / retreatLen) * BED_BOMB_SAFE_DISTANCE,
    0,
    (retreatDir.z / retreatLen) * BED_BOMB_SAFE_DISTANCE
  )
  try { await gotoPositionWithTimeout(safePos, EXPLORE_TIMEOUT_MS) } catch (_) {}

  // Place the bed
  try {
    await withTimeout(bot.equip(item, 'hand'), EQUIP_TIMEOUT_MS, 'equip bed')
    const placementRef = candidate.referenceBlock ? bot.blockAt(candidate.referenceBlock.position) : bot.blockAt(pos.minus(face))
    if (!placementRef) return fail('use_bed_bomb', 'Placement reference block vanished.')
    await withTimeout(bot.placeBlock(placementRef, face), PLACE_TIMEOUT_MS, 'place bed')
    await waitMs(500)
  } catch (err) {
    return fail('use_bed_bomb', `Failed to place bed: ${errorMessage(err)}`)
  }

  const bedBlock = bot.blockAt(pos)
  if (!bedBlock) return fail('use_bed_bomb', 'Bed block not found after placement.')

  // Activate to trigger explosion — explosion is nearly instant
  try {
    await withTimeout(bot.activateBlock(bedBlock), 3000, 'activate bed bomb')
  } catch (_) {
    // Explosion likely interrupted the call — that's expected
  }

  await waitMs(1500)
  return ok('use_bed_bomb', { detonated: true, health: typeof bot.health === 'number' ? bot.health : null })
}

async function avoidBedExplosion() {
  if (!bot.entity) return fail('avoid_bed_explosion', 'Bot not ready.')

  const bed = findNearbyBedBlock(16)
  if (!bed) {
    return ok('avoid_bed_explosion', { moved: false, reason: 'No bed found within 16 blocks.' })
  }

  const dist = bot.entity.position.distanceTo(bed.position)
  if (dist >= BED_BOMB_SAFE_DISTANCE) {
    return ok('avoid_bed_explosion', { moved: false, reason: `Already ${Math.round(dist)} blocks from bed — safe.` })
  }

  const dir = bot.entity.position.minus(bed.position).normalize()
  const safePos = bed.position.plus(dir.scaled(BED_BOMB_SAFE_DISTANCE + 1))

  try {
    await gotoPositionWithTimeout(safePos, 8000)
  } catch (err) {
    stopMovement()
    return fail('avoid_bed_explosion', `Failed to move away: ${errorMessage(err)}`)
  }

  stopMovement()
  const newDist = bot.entity.position.distanceTo(bed.position)
  return ok('avoid_bed_explosion', { moved: true, distance_from_bed: Math.round(newDist) })
}

// ---------------------------------------------------------------------------
// Nether portal actions
// ---------------------------------------------------------------------------

async function findLavaPool(requestedRadius) {
  if (!bot.entity) return fail('find_lava_pool', 'Bot not ready.')
  const radius = Math.min(LAVA_POOL_SEARCH_RADIUS_MAX, Math.max(16, requestedRadius || LAVA_POOL_SEARCH_RADIUS_DEFAULT))

  const lavaId = bot.registry.blocksByName.lava?.id
  if (!lavaId) return fail('find_lava_pool', 'Lava block not in registry.')

  const center = bot.entity.position.floored()
  const byY = {}

  for (let dx = -radius; dx <= radius; dx += 2) {
    for (let dy = -24; dy <= 4; dy++) {
      for (let dz = -radius; dz <= radius; dz += 2) {
        const pos = center.offset(dx, dy, dz)
        if (pos.distanceTo(center) > radius) continue
        const block = bot.blockAt(pos)
        if (block && block.type === lavaId && block.metadata === 0) {
          if (!byY[pos.y]) byY[pos.y] = []
          byY[pos.y].push(pos)
        }
      }
    }
  }

  const entries = Object.entries(byY).sort((a, b) => b[1].length - a[1].length)
  if (!entries.length) return fail('find_lava_pool', `No lava pool found within ${radius} blocks.`)

  const poolBlocks = entries[0][1]
  const poolY = poolBlocks[0].y
  const sumX = poolBlocks.reduce((s, p) => s + p.x, 0)
  const sumZ = poolBlocks.reduce((s, p) => s + p.z, 0)
  const poolCenter = new Vec3(
    Math.round(sumX / poolBlocks.length),
    poolY,
    Math.round(sumZ / poolBlocks.length)
  )

  // Navigate to within viewing distance of the pool (stay at least 4 blocks back)
  const approachPos = new Vec3(poolCenter.x, poolCenter.y + 1, poolCenter.z + 6)
  try { await gotoPositionWithTimeout(approachPos, EXPLORE_TIMEOUT_MS) } catch (_) {}

  markWaypoint('lava_pool', 'lava_pool')

  return ok('find_lava_pool', {
    found: true,
    pool_position: positionJson(poolCenter),
    pool_size: poolBlocks.length,
    y_level: poolY,
    waypoint: 'lava_pool',
  })
}

async function collectWater() {
  if (!bot.entity) return fail('collect_water', 'Bot not ready.')

  const bucket = firstInventoryItemByNames(['bucket'])
  if (!bucket) return fail('collect_water', 'Missing materials: no empty bucket.')

  const waterId = bot.registry.blocksByName.water?.id
  if (!waterId) return fail('collect_water', 'Water block not in registry.')

  const waterBlock = bot.findBlock({
    matching: (b) => b.type === waterId && b.metadata === 0,
    maxDistance: WATER_COLLECT_RADIUS,
  })
  if (!waterBlock) return fail('collect_water', `No water source found within ${WATER_COLLECT_RADIUS} blocks.`)

  try { await gotoPositionWithTimeout(waterBlock.position.offset(0, 0, 1), EXPLORE_TIMEOUT_MS) } catch (_) {}

  const freshWater = bot.blockAt(waterBlock.position)
  if (!freshWater || freshWater.type !== waterId || freshWater.metadata !== 0) {
    return fail('collect_water', 'Water source disappeared before collection.')
  }

  try {
    await withTimeout(bot.equip(bucket, 'hand'), EQUIP_TIMEOUT_MS, 'equip bucket')
    await bot.lookAt(waterBlock.position.offset(0.5, 0.5, 0.5), true)
    await delay(80)
    await withTimeout(bot.activateBlock(freshWater), 5000, 'collect water')
  } catch (err) {
    return fail('collect_water', `Failed to collect water: ${errorMessage(err)}`)
  }

  const deadline = Date.now() + 3000
  while (Date.now() < deadline) {
    if (countItemInInventory('water_bucket') > 0) break
    await waitMs(200)
  }

  if (countItemInInventory('water_bucket') === 0) {
    return fail('collect_water', 'Water bucket not in inventory after collection.')
  }

  return ok('collect_water', { collected: true, inventory: inventoryJson() })
}

async function collectLava() {
  if (!bot.entity) return fail('collect_lava', 'Bot not ready.')

  const bucket = firstInventoryItemByNames(['bucket'])
  if (!bucket) return fail('collect_lava', 'Missing materials: no empty bucket.')

  if (isBotInLiquid()) return fail('collect_lava', 'Refusing to collect lava while bot is in liquid.')

  const lavaId = bot.registry.blocksByName.lava?.id
  if (!lavaId) return fail('collect_lava', 'Lava block not in registry.')

  const lavaBlock = bot.findBlock({
    matching: (b) => b.type === lavaId && b.metadata === 0,
    maxDistance: LAVA_COLLECT_RADIUS,
  })
  if (!lavaBlock) return fail('collect_lava', `No lava source found within ${LAVA_COLLECT_RADIUS} blocks.`)

  const lavaPos = lavaBlock.position
  const botPos  = bot.entity.position
  const ddx = botPos.x - lavaPos.x
  const ddz = botPos.z - lavaPos.z
  const len = Math.sqrt(ddx * ddx + ddz * ddz) || 1
  const approachPos = new Vec3(
    Math.round(lavaPos.x + (ddx / len) * 2.5),
    lavaPos.y,
    Math.round(lavaPos.z + (ddz / len) * 2.5)
  )

  try { await gotoPositionWithTimeout(approachPos, EXPLORE_TIMEOUT_MS) } catch (_) {}

  if (isBotInLiquid()) return fail('collect_lava', 'Bot ended up in liquid during approach. Aborting.')

  const dist = bot.entity.position.distanceTo(lavaPos)
  if (dist > 5) return fail('collect_lava', `Could not get close enough to lava (${Math.round(dist)} blocks away).`)

  const freshLava = bot.blockAt(lavaPos)
  if (!freshLava || freshLava.type !== lavaId || freshLava.metadata !== 0) {
    return fail('collect_lava', 'Lava source changed before collection.')
  }

  try {
    await withTimeout(bot.equip(bucket, 'hand'), EQUIP_TIMEOUT_MS, 'equip bucket')
    await bot.lookAt(lavaPos.offset(0.5, 0.5, 0.5), true)
    await delay(80)
    await withTimeout(bot.activateBlock(freshLava), 5000, 'collect lava')
  } catch (err) {
    return fail('collect_lava', `Failed to collect lava: ${errorMessage(err)}`)
  }

  const deadline = Date.now() + 3000
  while (Date.now() < deadline) {
    if (countItemInInventory('lava_bucket') > 0) break
    await waitMs(200)
  }

  if (countItemInInventory('lava_bucket') === 0) {
    return fail('collect_lava', 'Lava bucket not in inventory after collection.')
  }

  if (isBotInLiquid()) return fail('collect_lava', 'Bot is in lava after collection — flee immediately!')

  return ok('collect_lava', { collected: true, inventory: inventoryJson() })
}

async function collectObsidian(requestedCount) {
  if (!bot.entity) return fail('collect_obsidian', 'Bot not ready.')
  const targetCount = Math.min(14, Math.max(1, requestedCount || 10))

  const pick = firstInventoryItemByNames(['netherite_pickaxe', 'diamond_pickaxe'])
  if (!pick) return fail('collect_obsidian', 'Missing tool: diamond_pickaxe or netherite_pickaxe required.')

  const obsidianId = bot.registry.blocksByName.obsidian?.id
  if (!obsidianId) return fail('collect_obsidian', 'Obsidian not in registry.')

  const snap = inventorySnapshot()
  let mined = 0

  for (let attempt = 0; attempt < targetCount + 6 && mined < targetCount; attempt++) {
    const block = bot.findBlock({ matching: obsidianId, maxDistance: 32 })
    if (!block) {
      if (mined === 0) return fail('collect_obsidian', 'No obsidian found within 32 blocks.')
      break
    }

    // Skip obsidian with lava directly below (unsafe)
    const below = bot.blockAt(block.position.offset(0, -1, 0))
    if (below && below.name.includes('lava')) continue

    try { await pathfindNearBlock(block, 3, ACQUIRE_PATH_TIMEOUT_MS) } catch (_) { continue }

    const fresh = bot.blockAt(block.position)
    if (!fresh || fresh.type !== obsidianId) continue

    try {
      const bestPick = firstInventoryItemByNames(['netherite_pickaxe', 'diamond_pickaxe'])
      if (bestPick) await bot.equip(bestPick, 'hand')
      await bot.lookAt(fresh.position.offset(0.5, 0.5, 0.5), true)
      await digBlockWithTimeout(fresh, OBSIDIAN_DIG_TIMEOUT_MS)
      await waitMs(600)
      mined++
    } catch (_) { continue }
  }

  const gained = inventoryDiff(snap)
  const obsidianGained = gained.obsidian || 0
  if (obsidianGained === 0) return fail('collect_obsidian', 'Could not mine any obsidian.')

  return ok('collect_obsidian', {
    collected: obsidianGained,
    requested: targetCount,
    total_obsidian: countItemInInventory('obsidian'),
    partial: obsidianGained < targetCount,
  })
}

async function buildNetherPortal() {
  if (!bot.entity) return fail('build_nether_portal', 'Bot not ready.')

  const dim = getBotDimension()
  if (!dim.includes('overworld')) {
    return fail('build_nether_portal', `build_nether_portal requires the Overworld (currently in ${dim}).`)
  }

  const obsidianCount = countItemInInventory('obsidian')
  if (obsidianCount < 14) {
    return fail('build_nether_portal',
      `Need 14 obsidian for full frame (have ${obsidianCount}). Mine more obsidian or use cast_nether_portal.`)
  }

  // Place the portal 2 blocks ahead of the bot (+Z) so the bot can place all blocks from z-1.
  const base = bot.entity.position.floored()
  const portalX = base.x - 1  // frame spans portalX … portalX+3 (bot is centered)
  const portalY = base.y
  const portalZ = base.z + 2

  // Verify solid ground beneath all 4 bottom-row positions
  for (let dx = 0; dx < 4; dx++) {
    const groundBlock = bot.blockAt(new Vec3(portalX + dx, portalY - 1, portalZ))
    if (!groundBlock || !isSolidBlock(groundBlock)) {
      return fail('build_nether_portal', 'Ground below portal position is not fully solid. Move to flat terrain.')
    }
  }

  // Navigate to the placement position (front-center of the portal frame)
  const placementPos = new Vec3(portalX + 1, portalY, portalZ - 1)
  try { await gotoPositionWithTimeout(placementPos, EXPLORE_TIMEOUT_MS) } catch (_) {}

  let placed = 0

  for (const [dx, dy, rdx, rdy, fx, fy, fz] of PORTAL_FRAME_OFFSETS) {
    const targetPos = new Vec3(portalX + dx, portalY + dy, portalZ)
    const refPos    = new Vec3(portalX + dx + rdx, portalY + dy + rdy, portalZ)

    const targetBlock = bot.blockAt(targetPos)
    if (targetBlock && targetBlock.name === 'obsidian') { placed++; continue }
    if (targetBlock && !canReplaceBlock(targetBlock)) continue

    const refBlock = bot.blockAt(refPos)
    if (!refBlock || !isSolidBlock(refBlock)) continue

    const faceVec = new Vec3(fx, fy, fz)
    const freshObs = bot.inventory.items().find((i) => i.name === 'obsidian')
    if (!freshObs) break

    try {
      await bot.equip(freshObs, 'hand')
      await bot.lookAt(faceCenter(refBlock.position, faceVec), true)
      await delay(80)
      await placeBlockWithTimeout(refBlock, faceVec, PLACE_TIMEOUT_MS)
    } catch (_) {}

    const verified = await waitForBlockAt(targetPos, ['obsidian'], PLACE_VERIFY_MS)
    if (verified) placed++
    await delay(150)
  }

  if (placed < 10) {
    return fail('build_nether_portal', `Only placed ${placed}/14 obsidian blocks — frame incomplete.`)
  }

  markWaypoint('nether_portal_overworld', 'nether_portal_overworld')

  return ok('build_nether_portal', {
    placed,
    full_frame: placed >= 14,
    portal_base: positionJson(new Vec3(portalX, portalY, portalZ)),
    waypoint: 'nether_portal_overworld',
  })
}

async function castNetherPortal() {
  if (!bot.entity) return fail('cast_nether_portal', 'Bot not ready.')

  const dim = getBotDimension()
  if (!dim.includes('overworld')) {
    return fail('cast_nether_portal', 'Portal casting only works in the Overworld.')
  }

  let waterBucket = firstInventoryItemByNames(['water_bucket'])
  if (!waterBucket) {
    if (!firstInventoryItemByNames(['bucket'])) {
      return fail('cast_nether_portal', 'Need at least one bucket.', { not_applicable: true })
    }
    const collectResult = await collectWater()
    if (!collectResult.ok) {
      return fail('cast_nether_portal', `Cannot get water: ${collectResult.error}`, { not_applicable: true })
    }
    waterBucket = firstInventoryItemByNames(['water_bucket'])
    if (!waterBucket) return fail('cast_nether_portal', 'Water bucket missing after collection.')
  }

  const lavaId     = bot.registry.blocksByName.lava?.id
  const waterId    = bot.registry.blocksByName.water?.id
  const obsidianId = bot.registry.blocksByName.obsidian?.id
  if (!lavaId || !waterId || !obsidianId) return fail('cast_nether_portal', 'Block type not in registry.')

  // Scan for flat lava pool (source blocks grouped by Y level)
  const center    = bot.entity.position.floored()
  const SCAN_RADIUS = 24
  const byY = {}

  for (let dx = -SCAN_RADIUS; dx <= SCAN_RADIUS; dx += 2) {
    for (let dy = -12; dy <= 0; dy++) {
      for (let dz = -SCAN_RADIUS; dz <= SCAN_RADIUS; dz += 2) {
        const pos = center.offset(dx, dy, dz)
        if (pos.distanceTo(center) > SCAN_RADIUS) continue
        const block = bot.blockAt(pos)
        if (block && block.type === lavaId && block.metadata === 0) {
          const key = pos.y
          if (!byY[key]) byY[key] = []
          byY[key].push({ x: pos.x, y: pos.y, z: pos.z })
        }
      }
    }
  }

  const poolEntries = Object.entries(byY).sort((a, b) => b[1].length - a[1].length)
  if (!poolEntries.length) {
    return fail('cast_nether_portal', 'No lava pool found within 24 blocks.', { not_applicable: true })
  }

  const poolBlocks = poolEntries[0][1]
  if (poolBlocks.length < 4) {
    return fail('cast_nether_portal', 'Lava pool too small (need ≥4 source blocks).', { not_applicable: true })
  }

  // Find a 4-wide consecutive X run for the bottom row
  const sortedByX = [...poolBlocks].sort((a, b) => a.x - b.x || a.z - b.z)
  let bottomRow = null

  for (let i = 0; i <= sortedByX.length - 4; i++) {
    const run = [sortedByX[i]]
    let cx = sortedByX[i].x
    const cz = sortedByX[i].z
    for (let j = i + 1; j < sortedByX.length && run.length < 4; j++) {
      if (sortedByX[j].x === cx + 1 && sortedByX[j].z === cz) { run.push(sortedByX[j]); cx++ }
    }
    if (run.length >= 4) { bottomRow = run.slice(0, 4); break }
  }

  if (!bottomRow) {
    return fail('cast_nether_portal', 'No 4-wide X-aligned run of lava source blocks found.', { not_applicable: true })
  }

  // Confirm above each target is accessible air
  const accessible = bottomRow.every((p) => {
    const above = bot.blockAt(new Vec3(p.x, p.y + 1, p.z))
    return above && (above.name === 'air' || above.boundingBox === 'empty')
  })
  if (!accessible) {
    return fail('cast_nether_portal', 'Lava surface is covered — cannot pour water from above.', { not_applicable: true })
  }

  // Cast: pour water onto the inner 2 lava sources of the bottom row
  let obsidianCreated = 0

  for (const lavaP of bottomRow.slice(1, 3)) {
    const lavaPos = new Vec3(lavaP.x, lavaP.y, lavaP.z)
    const approachPos = lavaPos.offset(0, 0, 2)
    try { await gotoPositionWithTimeout(approachPos, 8000) } catch (_) {}
    if (isBotInLiquid()) continue

    const freshLava = bot.blockAt(lavaPos)
    if (!freshLava || freshLava.type !== lavaId || freshLava.metadata !== 0) continue

    // Pour water from a solid block at lava-level+1 behind the target
    const pourRef = bot.blockAt(lavaPos.offset(0, 0, 1))
    if (!pourRef || !isSolidBlock(pourRef)) continue

    const wb = firstInventoryItemByNames(['water_bucket'])
    if (!wb) break

    try {
      await bot.equip(wb, 'hand')
      await bot.lookAt(lavaPos.offset(0.5, 1.5, 0.5), true)
      await delay(80)
      await placeBlockWithTimeout(pourRef, new Vec3(0, 1, 0), PLACE_TIMEOUT_MS)
    } catch (_) {}

    await waitMs(1500)

    const nowBlock = bot.blockAt(lavaPos)
    if (nowBlock && nowBlock.name === 'obsidian') obsidianCreated++

    // Collect water back
    const waterSrc = bot.findBlock({
      matching: (b) => b.type === waterId && b.metadata === 0,
      maxDistance: 8,
    })
    if (waterSrc) {
      const emptyBucketItem = firstInventoryItemByNames(['bucket'])
      if (emptyBucketItem) {
        try {
          await bot.equip(emptyBucketItem, 'hand')
          await bot.lookAt(waterSrc.position.offset(0.5, 0.5, 0.5), true)
          await delay(80)
          await withTimeout(bot.activateBlock(waterSrc), 3000, 'collect water back')
        } catch (_) {}
      }
    }
    await waitMs(400)
  }

  return ok('cast_nether_portal', {
    partial: true,
    obsidian_created: obsidianCreated,
    note: 'Partial: casts bottom-row inner blocks only. Full frame casting requires multiple passes.',
  })
}

async function craftFlintAndSteel() {
  if (!bot.entity) return fail('craft_flint_and_steel', 'Bot not ready.')

  if (countItemInInventory('iron_ingot') < 1) {
    return fail('craft_flint_and_steel', 'Missing materials: 1 iron_ingot required.')
  }
  if (countItemInInventory('flint') < 1) {
    return fail('craft_flint_and_steel', 'Missing materials: 1 flint required.')
  }

  const itemInfo = bot.registry.itemsByName.flint_and_steel
  if (!itemInfo) return fail('craft_flint_and_steel', 'flint_and_steel not in item registry.')

  // Try 2×2 inventory crafting first (no crafting table needed)
  let recipe = bot.recipesFor(itemInfo.id, null, 1, null)?.[0]
  let table  = null

  if (!recipe) {
    table  = findNearbyCraftingTable(STATION_USE_RADIUS)
    if (!table) return noCraftingTableFail('craft_flint_and_steel')
    recipe = bot.recipesFor(itemInfo.id, null, 1, table)?.[0]
    if (!recipe) return fail('craft_flint_and_steel', 'No recipe found for flint_and_steel.')
    try { await gotoPositionWithTimeout(table.position, EXPLORE_TIMEOUT_MS) } catch (_) {}
  }

  try {
    await craftWithTimeout(recipe, 1, table)
  } catch (err) {
    return fail('craft_flint_and_steel', `Crafting failed: ${errorMessage(err)}`)
  }

  if (countItemInInventory('flint_and_steel') === 0) {
    return fail('craft_flint_and_steel', 'Crafting completed but no flint_and_steel in inventory.')
  }

  return ok('craft_flint_and_steel', { crafted: 1, inventory: inventoryJson() })
}

async function lightNetherPortal() {
  if (!bot.entity) return fail('light_nether_portal', 'Bot not ready.')

  const flintAndSteel = firstInventoryItemByNames(['flint_and_steel'])
  if (!flintAndSteel) return fail('light_nether_portal', 'Missing materials: flint_and_steel required.')

  const obsidianId     = bot.registry.blocksByName.obsidian?.id
  const netherPortalId = bot.registry.blocksByName.nether_portal?.id

  if (!obsidianId) return fail('light_nether_portal', 'Obsidian not in registry.')

  // If already lit, succeed immediately
  if (netherPortalId && bot.findBlock({ matching: netherPortalId, maxDistance: 16 })) {
    return ok('light_nether_portal', { lit: true, already_lit: true })
  }

  const obsidian = bot.findBlock({ matching: obsidianId, maxDistance: 16 })
  if (!obsidian) return fail('light_nether_portal', 'No obsidian portal frame found within 16 blocks.')

  // Navigate in front of the portal
  try { await gotoPositionWithTimeout(obsidian.position.offset(0, 0, 2), EXPLORE_TIMEOUT_MS) } catch (_) {}

  // Verify there's an air block adjacent to the obsidian (interior of frame)
  const hasInterior = [
    new Vec3(1, 1, 0), new Vec3(-1, 1, 0), new Vec3(0, 1, 1), new Vec3(0, 1, -1),
    new Vec3(1, 0, 0), new Vec3(-1, 0, 0), new Vec3(0, 0, 1), new Vec3(0, 0, -1),
  ].some((off) => {
    const candidate = bot.blockAt(obsidian.position.plus(off))
    return candidate && (candidate.name === 'air' || candidate.boundingBox === 'empty')
  })

  if (!hasInterior) return fail('light_nether_portal', 'Cannot find air interior adjacent to obsidian.')

  try {
    await withTimeout(bot.equip(flintAndSteel, 'hand'), EQUIP_TIMEOUT_MS, 'equip flint_and_steel')
    await bot.lookAt(obsidian.position.offset(0.5, 0.5, 0.5), true)
    await delay(80)
    await withTimeout(bot.activateBlock(obsidian), 5000, 'light portal')
  } catch (err) {
    return fail('light_nether_portal', `Failed to light portal: ${errorMessage(err)}`)
  }

  // Wait for nether_portal blocks to appear
  let lit = !netherPortalId  // if registry doesn't know the block, trust the activation
  if (netherPortalId) {
    const deadline = Date.now() + 4000
    while (Date.now() < deadline) {
      if (bot.findBlock({ matching: netherPortalId, maxDistance: 10 })) { lit = true; break }
      await waitMs(400)
    }
  }

  if (!lit) return fail('light_nether_portal', 'Portal not lit — frame may be incomplete or incorrectly shaped.')

  return ok('light_nether_portal', { lit: true })
}

async function enterNether() {
  if (!bot.entity) return fail('enter_nether', 'Bot not ready.')

  const dim = getBotDimension()
  if (dim.includes('the_nether')) return fail('enter_nether', 'Already in the Nether.')

  const netherPortalId = bot.registry.blocksByName.nether_portal?.id
  if (!netherPortalId) return fail('enter_nether', 'nether_portal block not in registry.')

  // Store overworld portal position before entering
  markWaypoint('nether_portal_overworld', 'nether_portal_overworld')

  const portalBlock = bot.findBlock({ matching: netherPortalId, maxDistance: 16 })
  if (!portalBlock) return fail('enter_nether', 'No lit nether_portal block found within 16 blocks.')

  // Walk into the portal
  try { await gotoPositionWithTimeout(portalBlock.position, 8000) } catch (_) {}

  const beforeDim = getBotDimension()

  // Wait for dimension to change
  await new Promise((resolve) => {
    let done = false
    const iv = setInterval(() => {
      if (done) return
      if (getBotDimension() !== beforeDim) { done = true; clearInterval(iv); clearTimeout(tm); resolve() }
    }, 500)
    const tm = setTimeout(() => {
      if (!done) { done = true; clearInterval(iv); resolve() }
    }, PORTAL_WAIT_TIMEOUT_MS)
  })

  const afterDim = getBotDimension()
  if (afterDim === beforeDim) {
    return fail('enter_nether', 'Dimension did not change — stand inside the portal and retry enter_nether.')
  }

  await waitMs(2000)  // let the server finish loading the chunk
  markWaypoint('nether_portal_nether', 'nether_portal_nether')

  return ok('enter_nether', {
    dimension: afterDim,
    waypoints_stored: ['nether_portal_overworld', 'nether_portal_nether'],
  })
}

async function returnToPortal() {
  if (!bot.entity) return fail('return_to_portal', 'Bot not ready.')

  const dim = getBotDimension()
  let waypointLabel

  if (dim.includes('the_nether')) {
    waypointLabel = 'nether_portal_nether'
  } else if (dim.includes('the_end')) {
    return fail('return_to_portal', 'No Nether portal in The End. Use End Portal to return to Overworld.')
  } else {
    waypointLabel = 'nether_portal_overworld'
  }

  const wp = waypointStore.get(waypointLabel)
  if (!wp) {
    return fail('return_to_portal',
      `No waypoint '${waypointLabel}' stored. Use enter_nether or mark_waypoint to record portal location.`)
  }

  const portalPos = new Vec3(wp.x, wp.y, wp.z)

  try {
    await gotoPositionWithTimeout(portalPos, MOVEMENT_PATH_TIMEOUT_MS + 15000)
  } catch (err) {
    stopMovement()
    return fail('return_to_portal', `Navigation to portal failed: ${errorMessage(err)}`)
  }

  stopMovement()

  const netherPortalId = bot.registry.blocksByName.nether_portal?.id
  const portalNearby   = netherPortalId
    ? Boolean(bot.findBlock({ matching: netherPortalId, maxDistance: 8 }))
    : null

  return ok('return_to_portal', {
    arrived: true,
    portal_nearby: portalNearby,
    waypoint: waypointLabel,
    position: positionJson(bot.entity.position),
  })
}

// ---------------------------------------------------------------------------
// Nether safety and progression actions
// ---------------------------------------------------------------------------

async function equipGoldArmor() {
  if (!bot.entity) return fail('equip_gold_armor', 'Bot not ready.')
  // Prefer boots then helmet — any gold piece satisfies Piglin neutrality check
  const goldPieces = [
    { name: 'golden_boots',      slot: 'feet'  },
    { name: 'golden_helmet',     slot: 'head'  },
    { name: 'golden_chestplate', slot: 'torso' },
    { name: 'golden_leggings',   slot: 'legs'  },
  ]
  for (const piece of goldPieces) {
    const item = firstInventoryItemByNames([piece.name])
    if (!item) continue
    try {
      await withTimeout(bot.equip(item, piece.slot), EQUIP_TIMEOUT_MS, `equipping ${piece.name}`)
      return ok('equip_gold_armor', { equipped: piece.name, slot: piece.slot, piglin_safe: true })
    } catch (err) {
      return fail('equip_gold_armor', `Failed to equip ${piece.name}: ${errorMessage(err)}`)
    }
  }
  return fail('equip_gold_armor',
    'No gold armor found in inventory. Obtain golden_helmet, golden_chestplate, golden_leggings, or golden_boots.')
}

function avoidOpeningChestsNearPiglins() {
  if (!bot.entity || !bot.entities) return fail('avoid_opening_chests_near_piglins', 'Bot not ready.')
  const PIGLIN_CHECK_RADIUS = 16
  const piglins = Object.values(bot.entities).filter(e =>
    e && e !== bot.entity && e.position &&
    (e.name === 'piglin' || e.name === 'piglin_brute') &&
    bot.entity.position.distanceTo(e.position) <= PIGLIN_CHECK_RADIUS
  )
  if (piglins.length === 0) {
    return ok('avoid_opening_chests_near_piglins', {
      safe_to_loot: true,
      piglins_nearby: 0,
      message: 'No piglins within 16 blocks — safe to open chests.',
    })
  }
  const closest = piglins.sort(
    (a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position)
  )[0]
  return ok('avoid_opening_chests_near_piglins', {
    safe_to_loot: false,
    piglins_nearby: piglins.length,
    closest_distance: Math.round(bot.entity.position.distanceTo(closest.position) * 10) / 10,
    message: `${piglins.length} piglin(s) within 16 blocks — do NOT open chests. Move away or equip gold armor first.`,
  })
}

async function barterWithPiglins(requestedCount) {
  if (!bot.entity) return fail('barter_with_piglins', 'Bot not ready.')
  const dim = getBotDimension()
  if (!dim.includes('the_nether')) {
    return fail('barter_with_piglins', 'Bartering only works in the Nether.')
  }
  const goldCount = inventoryCount('gold_ingot')
  if (goldCount === 0) {
    return fail('barter_with_piglins', 'No gold_ingot in inventory. Piglins only accept gold ingots.')
  }
  const count = Math.min(requestedCount || 1, goldCount, 16)

  const wearingGold = [
    bot.inventory.slots[5],
    bot.inventory.slots[6],
    bot.inventory.slots[7],
    bot.inventory.slots[8],
  ].some(slot => slot && slot.name && slot.name.startsWith('golden_'))

  const piglin = Object.values(bot.entities)
    .filter(e =>
      e && e !== bot.entity && e.position &&
      e.name === 'piglin' &&
      bot.entity.position.distanceTo(e.position) <= BARTER_SEARCH_RADIUS
    )
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null

  if (!piglin) {
    return fail('barter_with_piglins',
      `No piglin found within ${BARTER_SEARCH_RADIUS} blocks. Explore to find piglins or a Bastion Remnant.`)
  }

  try {
    await gotoPositionWithTimeout(piglin.position, MOVEMENT_PATH_TIMEOUT_MS)
  } catch (err) {
    stopMovement()
    return fail('barter_with_piglins', `Could not approach piglin: ${errorMessage(err)}`)
  }
  stopMovement()

  const before = inventorySnapshot()
  const goldItem = firstInventoryItemByNames(['gold_ingot'])
  if (!goldItem) return fail('barter_with_piglins', 'Gold ingot disappeared from inventory.')

  try {
    await bot.lookAt(piglin.position.offset(0, 1, 0), true)
    await bot.toss(goldItem.type, null, count)
  } catch (err) {
    return fail('barter_with_piglins', `Failed to toss gold ingot: ${errorMessage(err)}`)
  }

  await waitMs(BARTER_WAIT_MS)

  const gained = inventoryDiff(before)
  const gainedList = Object.entries(gained).map(([name, n]) => ({ name, count: n }))
  const ender_pearls = gained.ender_pearl || 0

  return ok('barter_with_piglins', {
    gold_spent: count,
    wearing_gold: wearingGold,
    items_received: gainedList,
    ender_pearls,
    message: gainedList.length > 0
      ? `Bartered ${count}x gold_ingot. Received: ${gainedList.map(i => `${i.count}x ${i.name}`).join(', ')}.`
      : `Dropped ${count}x gold_ingot — piglin may still be animating or barter was refused.`,
  })
}

async function findNetherFortress(requestedRadius) {
  if (!bot.entity) return fail('find_nether_fortress', 'Bot not ready.')
  const dim = getBotDimension()
  if (!dim.includes('the_nether')) {
    return fail('find_nether_fortress', 'Must be in the Nether to search for a Nether Fortress.')
  }
  const radius = Math.min(NETHER_FORTRESS_SEARCH_RADIUS, Math.max(32, requestedRadius || NETHER_FORTRESS_SEARCH_RADIUS))
  const fortressBlocks = ['nether_bricks', 'nether_brick_fence', 'nether_brick_stairs']

  // Scan current area first (free, no movement)
  for (const blockName of fortressBlocks) {
    const blockDef = bot.registry.blocksByName[blockName]
    if (!blockDef) continue
    const found = bot.findBlock({ matching: blockDef.id, maxDistance: radius })
    if (found) {
      markWaypoint('fortress', 'fortress')
      try { await gotoPositionWithTimeout(found.position, MOVEMENT_PATH_TIMEOUT_MS + 15000) } catch (_) {}
      stopMovement()
      markWaypoint('fortress', 'fortress')
      return ok('find_nether_fortress', {
        found: true,
        block_hint: blockName,
        position: positionJson(found.position),
        waypoint: 'fortress',
      })
    }
  }

  // Bounded exploration: step outward in 4 cardinal directions, check after each step
  const base = bot.entity.position.floored()
  const STEP = 24
  const steps = Math.floor(radius / STEP)

  for (let i = 1; i <= steps; i++) {
    const targets = [
      base.offset(i * STEP, 0, 0),
      base.offset(-i * STEP, 0, 0),
      base.offset(0, 0, i * STEP),
      base.offset(0, 0, -i * STEP),
    ]
    for (const target of targets) {
      try { await gotoPositionWithTimeout(target, NETHER_NAVIGATE_TIMEOUT_MS) } catch (_) {}
      stopMovement()
      for (const blockName of fortressBlocks) {
        const blockDef = bot.registry.blocksByName[blockName]
        if (!blockDef) continue
        const found = bot.findBlock({ matching: blockDef.id, maxDistance: 32 })
        if (found) {
          markWaypoint('fortress', 'fortress')
          return ok('find_nether_fortress', {
            found: true,
            block_hint: blockName,
            position: positionJson(found.position),
            waypoint: 'fortress',
          })
        }
      }
    }
  }

  return ok('find_nether_fortress', {
    found: false,
    partial_success: true,
    can_retry: true,
    searched_radius: radius,
    message: `No Nether Fortress found within radius ${radius}. Retry or navigate_nether_safely in another direction.`,
  })
}

async function navigateNetherSafely(direction) {
  if (!bot.entity) return fail('navigate_nether_safely', 'Bot not ready.')
  const dim = getBotDimension()
  if (!dim.includes('the_nether')) {
    return fail('navigate_nether_safely', 'navigate_nether_safely is only for use in the Nether.')
  }
  if (isBotInLiquid()) {
    return fail('navigate_nether_safely', 'Bot is in liquid — use flee or recover_position first.')
  }

  const STEP = 24
  const startPos = bot.entity.position.floored()
  let dx = 0, dz = 0
  if      (direction === 'north') dz = -STEP
  else if (direction === 'south') dz =  STEP
  else if (direction === 'east')  dx =  STEP
  else if (direction === 'west')  dx = -STEP
  else {
    // Use current facing yaw
    const yaw = bot.entity.yaw || 0
    dx = Math.round(-Math.sin(yaw) * STEP)
    dz = Math.round(-Math.cos(yaw) * STEP)
  }

  // Quick lava scan halfway along the path
  const midX = startPos.x + Math.round(dx * 0.5)
  const midZ = startPos.z + Math.round(dz * 0.5)
  let lavaAhead = false
  for (let dy = -3; dy <= 0; dy++) {
    const b = bot.blockAt(new Vec3(midX, startPos.y + dy, midZ))
    if (b && b.name.includes('lava')) { lavaAhead = true; break }
  }
  if (lavaAhead) {
    return ok('navigate_nether_safely', {
      moved: false,
      lava_ahead: true,
      message: 'Lava detected ahead — choose a different direction or use bridge_gap to cross.',
    })
  }

  const target = startPos.offset(dx, 0, dz)
  try {
    await gotoPositionWithTimeout(target, NETHER_NAVIGATE_TIMEOUT_MS)
  } catch (err) {
    stopMovement()
    return ok('navigate_nether_safely', {
      moved: true,
      partial_success: true,
      can_retry: true,
      position: positionJson(bot.entity.position),
      distance_traveled: Math.round(bot.entity.position.distanceTo(startPos) * 10) / 10,
    })
  }
  stopMovement()
  return ok('navigate_nether_safely', {
    moved: true,
    direction: direction || 'forward',
    position: positionJson(bot.entity.position),
    distance_traveled: Math.round(bot.entity.position.distanceTo(startPos) * 10) / 10,
  })
}

async function collectBlazeRods(requestedCount) {
  if (!bot.entity) return fail('collect_blaze_rods', 'Bot not ready.')
  const dim = getBotDimension()
  if (!dim.includes('the_nether')) {
    return fail('collect_blaze_rods', 'Blazes only appear in the Nether.')
  }
  const targetCount = Math.min(
    Math.max(1, requestedCount || COLLECT_BLAZE_ROD_DEFAULT_COUNT),
    COLLECT_BLAZE_ROD_MAX_COUNT
  )

  const anyBlaze = Object.values(bot.entities).some(
    e => e && e !== bot.entity && e.position && e.name === 'blaze' &&
      bot.entity.position.distanceTo(e.position) <= 32
  )
  if (!anyBlaze) {
    return ok('collect_blaze_rods', {
      collected: 0,
      kills: 0,
      blaze_rods_in_inventory: inventoryCount('blaze_rod'),
      partial_success: false,
      suggested_next_action: 'find_nether_fortress',
      message: 'No blazes within 32 blocks. Use find_nether_fortress to locate a blaze spawner.',
    })
  }

  const before = inventorySnapshot()
  let totalRods = 0
  let kills = 0
  const deadline = Date.now() + COMBAT_TIMEOUT_MS * 3

  while (totalRods < targetCount && Date.now() < deadline) {
    if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break
    const result = await killBlaze()
    if (result.ok) {
      kills++
      totalRods += result.result.blaze_rods || 0
    } else {
      break
    }
    if (totalRods < targetCount) await waitMs(500)
  }

  return ok('collect_blaze_rods', {
    collected: totalRods,
    kills,
    blaze_rods_in_inventory: inventoryCount('blaze_rod'),
    partial_success: totalRods < targetCount,
    can_retry: totalRods < targetCount && (typeof bot.health !== 'number' || bot.health > LOW_HEALTH_THRESHOLD),
  })
}

async function retreatFromNetherDanger() {
  if (!bot.entity) return fail('retreat_from_nether_danger', 'Bot not ready.')
  const dim = getBotDimension()
  if (!dim.includes('the_nether')) {
    return fail('retreat_from_nether_danger', 'Not in the Nether. Use retreat_from_combat instead.')
  }

  const NETHER_THREAT_NAMES = new Set([
    'ghast', 'blaze', 'piglin_brute', 'hoglin', 'zoglin', 'wither_skeleton', 'magma_cube',
  ])
  const threat = (
    Object.values(bot.entities)
      .filter(e => e && e !== bot.entity && e.position && NETHER_THREAT_NAMES.has(e.name))
      .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0]
    || nearestHostileEntity()
  )

  if (!threat) {
    stopMovement()
    return ok('retreat_from_nether_danger', { retreated: false, reason: 'No Nether threat detected.' })
  }

  const away = bot.entity.position.minus(threat.position)
  const len = Math.sqrt(away.x * away.x + away.z * away.z) || 1
  const retreatTarget = bot.entity.position.offset(
    (away.x / len) * NETHER_RETREAT_DISTANCE,
    0,
    (away.z / len) * NETHER_RETREAT_DISTANCE
  )

  stopMovement()
  try {
    await gotoPositionWithTimeout(retreatTarget, NETHER_NAVIGATE_TIMEOUT_MS)
  } catch (_) {}
  stopMovement()

  return ok('retreat_from_nether_danger', {
    threat: entityJson(threat),
    position: bot.entity ? positionJson(bot.entity.position) : null,
    distance_from_threat: bot.entity
      ? Math.round(bot.entity.position.distanceTo(threat.position) * 10) / 10
      : null,
  })
}

async function leaveNether() {
  if (!bot.entity) return fail('leave_nether', 'Bot not ready.')
  const dim = getBotDimension()
  if (!dim.includes('the_nether')) {
    return fail('leave_nether', 'Not in the Nether. This action only works in the Nether.')
  }

  const wp = waypointStore.get('nether_portal_nether')
  if (!wp) {
    return fail('leave_nether',
      'No nether_portal_nether waypoint stored. Use enter_nether first to record the portal location.')
  }

  try {
    await gotoPositionWithTimeout(new Vec3(wp.x, wp.y, wp.z), MOVEMENT_PATH_TIMEOUT_MS + 15000)
  } catch (err) {
    stopMovement()
    return fail('leave_nether', `Could not navigate to Nether portal: ${errorMessage(err)}`)
  }
  stopMovement()

  const netherPortalId = bot.registry.blocksByName.nether_portal?.id
  const portalBlock = netherPortalId
    ? bot.findBlock({ matching: netherPortalId, maxDistance: 4 })
    : null

  if (!portalBlock) {
    return fail('leave_nether',
      'Reached portal waypoint but no nether_portal block found within 4 blocks. Portal may be unlit.')
  }

  const beforeDim = getBotDimension()
  try { await gotoPositionWithTimeout(portalBlock.position, 5000) } catch (_) {}

  const dimensionChanged = await new Promise((resolve) => {
    let interval = null, timeout = null
    interval = setInterval(() => {
      if (getBotDimension() !== beforeDim) {
        clearInterval(interval)
        clearTimeout(timeout)
        resolve(true)
      }
    }, 500)
    timeout = setTimeout(() => {
      clearInterval(interval)
      resolve(false)
    }, PORTAL_WAIT_TIMEOUT_MS)
  })

  if (!dimensionChanged) {
    return fail('leave_nether',
      'Stood in Nether portal but dimension did not change. Portal may need relighting with flint_and_steel.')
  }

  await waitMs(2000)
  markWaypoint('nether_portal_overworld', 'nether_portal_overworld')

  return ok('leave_nether', {
    from: beforeDim,
    to: getBotDimension(),
    position: bot.entity ? positionJson(bot.entity.position) : null,
  })
}

// ---------------------------------------------------------------------------
// Stronghold and End portal progression actions
// ---------------------------------------------------------------------------

// craft_eyes_of_ender: 1 ender_pearl + 1 blaze_powder → 1 eye_of_ender (inventory crafting, no table needed)
async function craftEyesOfEnder(requestedCount) {
  if (!bot.entity) return fail('craft_eyes_of_ender', 'Bot not ready.')

  const pearls = countItemInInventory('ender_pearl')
  const powder = countItemInInventory('blaze_powder')
  if (pearls < 1 || powder < 1) {
    return fail('craft_eyes_of_ender',
      `Missing materials: ender_pearl x${pearls}, blaze_powder x${powder}. Need 1 of each per eye.`)
  }

  const maxCraft = Math.min(pearls, powder)
  const count    = Math.min(Math.max(1, requestedCount || maxCraft), 12, maxCraft)

  const eyeType = itemType('ender_eye')
  if (!eyeType) return fail('craft_eyes_of_ender', 'This Minecraft version does not know item ender_eye.')

  const recipe = bot.recipesFor(eyeType.id, null, count, null)[0]
  if (!recipe) return fail('craft_eyes_of_ender', 'No recipe found for ender_eye.')

  const startEyes = countItemInInventory('ender_eye')
  try {
    await craftWithTimeout(recipe, count, null)
  } catch (err) {
    return fail('craft_eyes_of_ender', `Crafting failed: ${errorMessage(err)}`)
  }

  const produced = Math.max(0, countItemInInventory('ender_eye') - startEyes)
  return ok('craft_eyes_of_ender', { crafts: count, produced, inventory: inventoryJson() })
}

// throw_eye_of_ender: equip and throw an Eye of Ender, record travel direction for stronghold triangulation.
async function throwEyeOfEnder() {
  if (!bot.entity) return fail('throw_eye_of_ender', 'Bot not ready.')

  const eyeItem = firstInventoryItemByNames(['ender_eye'])
  if (!eyeItem) {
    return fail('throw_eye_of_ender',
      'No ender_eye in inventory. Craft from ender_pearl + blaze_powder first.')
  }

  try {
    await withTimeout(bot.equip(eyeItem, 'hand'), EQUIP_TIMEOUT_MS, 'equipping ender_eye')
  } catch (err) {
    return fail('throw_eye_of_ender', `Could not equip ender_eye: ${errorMessage(err)}`)
  }

  const throwPos = bot.entity.position.clone()

  // Capture the eye-of-ender projectile entity to read its travel direction
  let eyeEntity = null
  const onSpawn = (entity) => { if (entity.name === 'eye_of_ender' && !eyeEntity) eyeEntity = entity }
  bot.on('entitySpawn', onSpawn)
  bot.activateItem()
  await waitMs(600)  // give entity time to spawn and move slightly
  bot.removeListener('entitySpawn', onSpawn)

  // Derive direction from entity displacement; fall back to bot facing direction
  let dirX = null, dirZ = null
  if (eyeEntity && eyeEntity.position) {
    const dx = eyeEntity.position.x - throwPos.x
    const dz = eyeEntity.position.z - throwPos.z
    const len = Math.sqrt(dx * dx + dz * dz)
    if (len > 0.3) {
      dirX = Math.round((dx / len) * 1000) / 1000
      dirZ = Math.round((dz / len) * 1000) / 1000
    }
  }
  if (dirX === null && bot.entity) {
    dirX = Math.round(-Math.sin(bot.entity.yaw) * 1000) / 1000
    dirZ = Math.round(-Math.cos(bot.entity.yaw) * 1000) / 1000
  }

  await waitMs(EYE_THROW_WAIT_MS)  // wait for eye to land before next action

  const existing   = waypointStore.get('stronghold_search') || {}
  const throwCount = (existing.throw_count || 0) + 1
  waypointStore.set('stronghold_search', {
    throw_x:     Math.floor(throwPos.x),
    throw_y:     Math.floor(throwPos.y),
    throw_z:     Math.floor(throwPos.z),
    direction_x: dirX,
    direction_z: dirZ,
    throw_count: throwCount,
  })

  return ok('throw_eye_of_ender', {
    thrown:          true,
    eye_detected:    eyeEntity !== null,
    throw_position:  positionJson(throwPos),
    direction:       { x: dirX, z: dirZ },
    throw_count:     throwCount,
    message: 'Eye thrown. Use locate_stronghold_step to move in that direction, then throw again to triangulate.',
  })
}

// locate_stronghold_step: move STRONGHOLD_STEP_DISTANCE blocks in the stored eye direction,
// scan for stronghold indicator blocks, store waypoint if found.
async function locateStrongholdStep() {
  if (!bot.entity) return fail('locate_stronghold_step', 'Bot not ready.')

  const search = waypointStore.get('stronghold_search')
  if (!search || search.direction_x === null) {
    return fail('locate_stronghold_step',
      'No stronghold direction stored. Use throw_eye_of_ender first.')
  }

  const INDICATOR_NAMES = [
    'end_portal_frame', 'stone_bricks', 'mossy_stone_bricks', 'cracked_stone_bricks',
  ]

  function scanForStronghold(radius) {
    for (const bname of INDICATOR_NAMES) {
      const bid = bot.registry.blocksByName[bname]?.id
      if (!bid) continue
      const block = bot.findBlock({ matching: bid, maxDistance: radius })
      if (block) return { name: bname, position: positionJson(block.position) }
    }
    return null
  }

  // Scan before moving
  const preFound = scanForStronghold(STRONGHOLD_SCAN_RADIUS)
  if (preFound) {
    markWaypoint('stronghold', 'stronghold')
    return ok('locate_stronghold_step', {
      moved:            false,
      stronghold_found: true,
      found_block:      preFound,
      waypoint:         'stronghold',
      message: 'Stronghold detected nearby! Use dig_staircase_to_stronghold or scan_for_end_portal_room.',
    })
  }

  const pos    = bot.entity.position
  const dx     = search.direction_x
  const dz     = search.direction_z
  const target = new Vec3(
    Math.round(pos.x + dx * STRONGHOLD_STEP_DISTANCE),
    Math.floor(pos.y),
    Math.round(pos.z + dz * STRONGHOLD_STEP_DISTANCE),
  )

  const startPos = pos.clone()
  try {
    await gotoPositionWithTimeout(target, MOVEMENT_PATH_TIMEOUT_MS + 20000)
  } catch (_) { /* partial navigation is still useful */ }
  stopMovement()

  const postFound  = scanForStronghold(STRONGHOLD_SCAN_RADIUS)
  if (postFound) markWaypoint('stronghold', 'stronghold')

  const actualDist = Math.round(bot.entity.position.distanceTo(startPos) * 10) / 10

  return ok('locate_stronghold_step', {
    moved:            actualDist > 2,
    distance_moved:   actualDist,
    direction:        { x: dx, z: dz },
    position:         positionJson(bot.entity.position),
    stronghold_found: postFound !== null,
    found_block:      postFound,
    waypoint:         postFound ? 'stronghold' : null,
    throw_count:      search.throw_count,
    message: postFound
      ? 'Stronghold blocks detected! Use dig_staircase_to_stronghold or scan_for_end_portal_room.'
      : 'Moved toward estimated stronghold. Throw another eye to re-triangulate, then repeat.',
  })
}

// dig_staircase_to_stronghold: safely dig a diagonal downward staircase while scanning for
// stronghold blocks. Never digs straight down. Aborts on lava or bedrock.
async function digStaircaseToStronghold() {
  if (!bot.entity) return fail('dig_staircase_to_stronghold', 'Bot not ready.')
  if (!hasPickaxe()) return fail('dig_staircase_to_stronghold', 'No pickaxe in inventory.')

  const STRONGHOLD_NAMES = [
    'end_portal_frame', 'stone_bricks', 'mossy_stone_bricks', 'cracked_stone_bricks',
  ]

  function scanForStronghold(radius) {
    for (const bname of STRONGHOLD_NAMES) {
      const bid = bot.registry.blocksByName[bname]?.id
      if (!bid) continue
      const block = bot.findBlock({ matching: bid, maxDistance: radius })
      if (block) return { name: bname, position: positionJson(block.position) }
    }
    return null
  }

  const preFound = scanForStronghold(8)
  if (preFound) {
    markWaypoint('stronghold', 'stronghold')
    return ok('dig_staircase_to_stronghold', {
      already_inside: true,
      found_block:    preFound.name,
      waypoint:       'stronghold',
      position:       preFound.position,
      message:        'Already inside stronghold. Use scan_for_end_portal_room.',
    })
  }

  // Horizontal direction from current facing (never straight down)
  const yaw    = bot.entity.yaw
  const rawDir = new Vec3(Math.round(-Math.sin(yaw)), 0, Math.round(-Math.cos(yaw)))
  const dirVec = (rawDir.x !== 0 || rawDir.z !== 0) ? rawDir : new Vec3(0, 0, 1)

  let stepsDone = 0
  let foundBlock = null

  for (let i = 0; i < STRONGHOLD_STAIRCASE_MAX_STEPS; i++) {
    if (!bot.entity) break
    if (bot.entity.position.y < 5) break  // bedrock safety

    foundBlock = scanForStronghold(STRONGHOLD_SCAN_RADIUS)
    if (foundBlock) break

    const base  = bot.entity.position.floored()
    // Diagonal downward stair: forward same-level + head clearance + stair tread one lower
    const todig = [
      base.offset(dirVec.x,  0, dirVec.z),
      base.offset(dirVec.x,  1, dirVec.z),
      base.offset(dirVec.x, -1, dirVec.z),
    ]

    let failed = false
    for (const pos of todig) {
      const block = bot.blockAt(pos)
      if (!block || canReplaceBlock(block)) continue
      if (isLiquidBlock(block) || isDangerousAdjacent(block)) { failed = true; break }
      if (block.name === 'bedrock') { failed = true; break }
      if (NEVER_MINE_BLOCK_NAMES.has(block.name)) { failed = true; break }
      try {
        await equipBestPickaxe()
        await bot.lookAt(block.position.offset(0.5, 0.5, 0.5), true)
        await digBlockWithTimeout(block, STAIRCASE_DIG_TIMEOUT_MS)
      } catch (_) { failed = true; break }
    }
    if (failed) break

    const nextPos = base.offset(dirVec.x, -1, dirVec.z)
    try {
      await withTimeout(
        bot.pathfinder.goto(new goals.GoalBlock(nextPos.x, nextPos.y, nextPos.z)),
        STAIRCASE_STEP_TIMEOUT_MS, 'staircase step',
      )
    } catch (_) {}

    stepsDone++
    await delay(100)
  }

  if (foundBlock) markWaypoint('stronghold', 'stronghold')

  return ok('dig_staircase_to_stronghold', {
    steps_dug:        stepsDone,
    partial_success:  stepsDone > 0 || foundBlock !== null,
    can_retry:        stepsDone > 0 && !foundBlock,
    stronghold_found: foundBlock !== null,
    found_block:      foundBlock,
    waypoint:         foundBlock ? 'stronghold' : null,
    position:         bot.entity ? positionJson(bot.entity.position) : null,
    message: foundBlock
      ? 'Found stronghold blocks! Use scan_for_end_portal_room to locate the portal room.'
      : stepsDone > 0
        ? 'Dug staircase. Re-throw eye to verify direction, then retry dig_staircase_to_stronghold.'
        : 'Could not dig — lava, bedrock, or protected block blocking the path.',
  })
}

// scan_for_end_portal_room: search within END_PORTAL_SEARCH_RADIUS for end_portal_frame blocks,
// navigate to them, and store the end_portal_room waypoint.
async function scanForEndPortalRoom() {
  if (!bot.entity) return fail('scan_for_end_portal_room', 'Bot not ready.')

  const frameId = bot.registry.blocksByName.end_portal_frame?.id
  if (!frameId) return fail('scan_for_end_portal_room', 'end_portal_frame not in registry.')

  const frameBlock = bot.findBlock({ matching: frameId, maxDistance: END_PORTAL_SEARCH_RADIUS })
  if (!frameBlock) {
    return ok('scan_for_end_portal_room', {
      found:   false,
      message: `No end_portal_frame found within ${END_PORTAL_SEARCH_RADIUS} blocks. Navigate deeper into the stronghold or use dig_staircase_to_stronghold.`,
    })
  }

  try {
    await gotoPositionWithTimeout(frameBlock.position, MOVEMENT_PATH_TIMEOUT_MS + 30000)
  } catch (_) {
    stopMovement()
    markWaypoint('end_portal_room', 'end_portal_room')
    return ok('scan_for_end_portal_room', {
      found:      true,
      position:   positionJson(frameBlock.position),
      waypoint:   'end_portal_room',
      navigated:  false,
      message:    'End portal frame found but navigation failed. Waypoint stored — use activate_end_portal.',
    })
  }
  stopMovement()
  markWaypoint('end_portal_room', 'end_portal_room')

  // Count filled vs empty frames (bot.findBlocks returns Vec3 array)
  const framePositions = typeof bot.findBlocks === 'function'
    ? bot.findBlocks({ matching: frameId, maxDistance: 8, count: 12 })
    : []
  let filledFrames = 0, emptyFrames = 0
  for (const pos of framePositions) {
    const b     = bot.blockAt(pos)
    const props = b && b.getProperties ? b.getProperties() : {}
    if (String(props.eye) === 'true') filledFrames++; else emptyFrames++
  }

  const eyesNeeded = Math.max(0, 12 - filledFrames)
  return ok('scan_for_end_portal_room', {
    found:         true,
    position:      positionJson(frameBlock.position),
    waypoint:      'end_portal_room',
    navigated:     true,
    total_frames:  framePositions.length,
    filled_frames: filledFrames,
    empty_frames:  emptyFrames,
    eyes_needed:   eyesNeeded,
    portal_ready:  emptyFrames === 0 && framePositions.length >= 12,
    message: emptyFrames === 0 && framePositions.length >= 12
      ? 'End portal already active! Use enter_end.'
      : `Found ${framePositions.length} frames, ${emptyFrames} need eyes. Use activate_end_portal (need ender_eye x${eyesNeeded}).`,
  })
}

// activate_end_portal: place eyes of ender into all empty end_portal_frame blocks within reach.
async function activateEndPortal() {
  if (!bot.entity) return fail('activate_end_portal', 'Bot not ready.')

  if (countItemInInventory('ender_eye') < 1) {
    return fail('activate_end_portal',
      'No ender_eye in inventory. Craft from ender_pearl + blaze_powder.')
  }

  const frameId = bot.registry.blocksByName.end_portal_frame?.id
  if (!frameId) return fail('activate_end_portal', 'end_portal_frame not in registry.')

  const framePositions = typeof bot.findBlocks === 'function'
    ? bot.findBlocks({ matching: frameId, maxDistance: 8, count: 12 })
    : []

  if (framePositions.length === 0) {
    return fail('activate_end_portal',
      'No end_portal_frame blocks within 8 blocks. Use scan_for_end_portal_room first.')
  }

  // Collect empty frame Block objects (eye property is 'false' or missing)
  const emptyFrames = []
  for (const pos of framePositions) {
    const block = bot.blockAt(pos)
    if (!block) continue
    const props = block.getProperties ? block.getProperties() : {}
    if (String(props.eye) !== 'true') emptyFrames.push(block)
  }

  if (emptyFrames.length === 0) {
    const portalId  = bot.registry.blocksByName.end_portal?.id
    const portalNow = portalId ? bot.findBlock({ matching: portalId, maxDistance: 8 }) : null
    return ok('activate_end_portal', {
      all_filled:   true,
      eyes_placed:  0,
      portal_active: portalNow !== null,
      message: portalNow
        ? 'All frames have eyes and portal is active! Use enter_end.'
        : 'All frames already filled. Portal should activate soon — use enter_end.',
    })
  }

  let eyesPlaced = 0
  const errors   = []
  for (const frame of emptyFrames) {
    if (countItemInInventory('ender_eye') < 1) break
    const eyeItem = firstInventoryItemByNames(['ender_eye'])
    if (!eyeItem) break
    try {
      await withTimeout(bot.equip(eyeItem, 'hand'), EQUIP_TIMEOUT_MS, 'equip ender_eye')
      await bot.lookAt(frame.position.offset(0.5, 0.5, 0.5), true)
      await delay(150)
      await withTimeout(bot.activateBlock(frame), ACTIVATE_PORTAL_TIMEOUT_MS, 'activate frame')
      eyesPlaced++
      await delay(300)
    } catch (err) {
      errors.push(errorMessage(err))
    }
  }

  const portalId    = bot.registry.blocksByName.end_portal?.id
  const portalBlock = portalId ? bot.findBlock({ matching: portalId, maxDistance: 8 }) : null

  return ok('activate_end_portal', {
    eyes_placed:      eyesPlaced,
    frames_total:     framePositions.length,
    frames_remaining: Math.max(0, emptyFrames.length - eyesPlaced),
    portal_active:    portalBlock !== null,
    errors:           errors.length > 0 ? errors : undefined,
    message: portalBlock
      ? 'End portal activated! Use enter_end to enter The End.'
      : eyesPlaced > 0
        ? `Placed ${eyesPlaced} eyes. ${Math.max(0, emptyFrames.length - eyesPlaced)} empty frames remain.`
        : 'Could not place any eyes. Get closer to portal frames and retry.',
  })
}

// enter_end: step into an active End portal and wait for dimension change to the_end.
async function enterEnd() {
  if (!bot.entity) return fail('enter_end', 'Bot not ready.')

  const dim = getBotDimension()
  if (dim.includes('the_end')) return fail('enter_end', 'Already in The End.')

  const portalId = bot.registry.blocksByName.end_portal?.id
  if (!portalId) return fail('enter_end', 'end_portal block not in registry.')

  const portalBlock = bot.findBlock({ matching: portalId, maxDistance: 8 })
  if (!portalBlock) {
    return fail('enter_end',
      'No active end_portal block found within 8 blocks. Use activate_end_portal first.')
  }

  const beforeDim = getBotDimension()
  try { await gotoPositionWithTimeout(portalBlock.position, 8000) } catch (_) {}

  const dimensionChanged = await new Promise((resolve) => {
    let interval = null, timeout = null
    interval = setInterval(() => {
      if (getBotDimension() !== beforeDim) {
        clearInterval(interval); clearTimeout(timeout); resolve(true)
      }
    }, 500)
    timeout = setTimeout(() => { clearInterval(interval); resolve(false) }, PORTAL_WAIT_TIMEOUT_MS)
  })

  if (!dimensionChanged) {
    return fail('enter_end',
      'Stepped into End portal but dimension did not change. Ensure all 12 frames have eyes of ender.')
  }

  await waitMs(END_PORTAL_WAIT_MS)

  return ok('enter_end', {
    from:     beforeDim,
    to:       getBotDimension(),
    position: bot.entity ? positionJson(bot.entity.position) : null,
    message:  'Entered The End! Prioritize safe landing — use mlg_water_bucket to avoid fall damage.',
  })
}

// ---------------------------------------------------------------------------
// Ender Dragon fight phase actions
// ---------------------------------------------------------------------------

function requireEnd(action) {
  const dim = getBotDimension()
  if (!dim.includes('the_end')) {
    return fail(action, `${action} requires The End (currently in ${dim}).`)
  }
  return null
}

async function endSafeLanding() {
  const action = 'end_safe_landing'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError

  const velocityY = (bot.entity.velocity && bot.entity.velocity.y) || 0
  if (!bot.entity.onGround && velocityY < -0.15) {
    const waterBucket = firstInventoryItemByNames(['water_bucket'])
    if (waterBucket) {
      const mlg = await mlgWaterBucket()
      return ok(action, {
        partial_success: mlg.ok,
        falling: true,
        used_water_bucket: mlg.ok,
        can_retry: !mlg.ok,
        suggested_next_action: mlg.ok ? 'end_safe_landing' : 'recover_position',
        inner_result: mlg.result,
      })
    }
    return fail(action, 'Bot is falling in The End and has no water_bucket for safe landing.', {
      falling: true,
      can_retry: true,
      suggested_next_action: 'recover_position',
    })
  }

  await waitMs(500)
  const feet = bot.entity.position.floored()
  if (!isSafeStandPosition(feet)) {
    return fail(action, 'Current position is not safe; refusing to move toward the void.', {
      position: positionJson(bot.entity.position),
      can_retry: true,
      suggested_next_action: 'recover_position',
    })
  }

  const floor = bot.blockAt(feet.offset(0, -1, 0))
  const island = findNearestEndIslandStand(END_SAFE_LANDING_RADIUS)
  if (!isObsidianPlatformFloor(floor)) {
    return ok(action, {
      landed: true,
      on_obsidian_platform: false,
      position: positionJson(bot.entity.position),
      suggested_next_action: 'fight_dragon_phase',
    })
  }

  if (!island) {
    return ok(action, {
      landed: true,
      on_obsidian_platform: true,
      island_found: false,
      partial_success: true,
      can_retry: true,
      message: 'Safe on obsidian platform, but no End island surface was found nearby.',
      suggested_next_action: 'scan_end_crystals',
    })
  }

  try {
    await gotoPositionWithTimeout(island.position, MOVEMENT_PATH_TIMEOUT_MS)
    if (bot.entity && isSafeStandPosition(bot.entity.position.floored())) {
      return ok(action, {
        landed: true,
        left_platform: true,
        bridged: false,
        position: positionJson(bot.entity.position),
        island_position: positionJson(island.position),
        suggested_next_action: 'fight_dragon_phase',
      })
    }
  } catch (_) {}

  const direction = cardinalDirectionToward(bot.entity.position, island.position)
  const length = Math.min(BRIDGE_MAX_LENGTH, Math.max(1, Math.ceil(horizontalDistance(bot.entity.position, island.position))))
  const bridge = await bridgeGap(direction, length)
  return ok(action, {
    landed: true,
    on_obsidian_platform: true,
    bridged: bridge.ok && bridge.result && bridge.result.placed > 0,
    partial_success: true,
    can_retry: true,
    bridge_result: bridge.result,
    suggested_next_action: bridge.ok ? 'end_safe_landing' : 'scan_end_crystals',
  })
}

async function equipPumpkinHead() {
  const action = 'equip_pumpkin_head'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError

  const pumpkin = firstInventoryItemByNames(['carved_pumpkin'])
  if (!pumpkin) return fail(action, 'No carved_pumpkin in inventory.')

  try {
    await withTimeout(bot.equip(pumpkin, 'head'), EQUIP_TIMEOUT_MS, 'equipping carved pumpkin')
  } catch (err) {
    return fail(action, `Could not equip carved pumpkin: ${errorMessage(err)}`)
  }

  return ok(action, { equipped: 'carved_pumpkin', endermen_safe: true })
}

async function lookDownAroundEndermen() {
  const action = 'look_down_around_endermen'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError

  const endermen = findNearbyEndermen(ENDERMAN_AVOID_RADIUS)
  await bot.look(bot.entity.yaw, Math.PI / 2, true)
  stopMovement()
  return ok(action, {
    looked_down: true,
    endermen_nearby: endermen.length,
    closest_enderman_distance: endermen[0] ? bot.entity.position.distanceTo(endermen[0].position) : null,
  })
}

function scanEndCrystals() {
  const action = 'scan_end_crystals'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError

  const crystals = findEndCrystals(END_CRYSTAL_SCAN_RADIUS).map((entity) => endCrystalJson(entity))
  return ok(action, {
    crystals,
    count: crystals.length,
    caged_count: crystals.filter((c) => c.caged === true).length,
    unconfirmed_caged_count: crystals.filter((c) => c.caged === 'unconfirmed').length,
    suggested_next_action: crystals.length > 0 ? 'destroy_nearby_end_crystals' : 'dragon_phase_circle',
  })
}

async function destroyEndCrystal() {
  const action = 'destroy_end_crystal'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError
  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) {
    return fail(action, `Health too low (${bot.health}). Eat, flee, or reposition first.`, {
      suggested_next_action: 'eat_food',
    })
  }

  const crystals = findEndCrystals(END_CRYSTAL_SCAN_RADIUS)
  const target = crystals.find((c) => !isEndCrystalCaged(c)) || crystals[0] || null
  if (!target) {
    return ok(action, {
      destroyed: false,
      remaining: 0,
      milestone_reached: true,
      suggested_next_action: 'dragon_phase_circle',
    })
  }

  if (isEndCrystalCaged(target)) {
    return ok(action, {
      destroyed: false,
      caged: true,
      partial_success: true,
      can_retry: true,
      target: endCrystalJson(target),
      suggested_next_action: 'destroy_caged_end_crystal',
    })
  }

  const dist = bot.entity.position.distanceTo(target.position)
  if (dist < END_CRYSTAL_DANGER_RADIUS) {
    await retreatFromPosition(target.position, END_CRYSTAL_DANGER_RADIUS + 4)
  }

  if (hasBowAndArrows() && canSeeEntitySafe(target)) {
    const shot = await shootEntityWithBow(action, target)
    return finalizeCrystalDestroy(action, target, shot)
  }

  const yDiff = target.position.y - bot.entity.position.y
  if (yDiff <= END_CRYSTAL_LOW_REACH_Y && dist <= 6) {
    try {
      await bot.lookAt(target.position, true)
      await withTimeout(bot.attack(target), 1000, 'breaking End crystal')
    } catch (err) {
      return fail(action, `Could not melee End crystal: ${errorMessage(err)}`, {
        target: endCrystalJson(target),
        can_retry: true,
      })
    }
    await waitMs(1000)
    return finalizeCrystalDestroy(action, target, { ok: true, result: { method: 'melee' } })
  }

  return ok(action, {
    destroyed: false,
    partial_success: true,
    can_retry: true,
    target: endCrystalJson(target),
    reason: hasBowAndArrows() ? 'No clear line of sight to crystal.' : 'No bow and arrows available.',
    suggested_next_action: yDiff > END_CRYSTAL_LOW_REACH_Y ? 'pillar_up' : 'shoot_bow',
  })
}

async function destroyCagedEndCrystal() {
  const action = 'destroy_caged_end_crystal'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError
  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD + 4) {
    return fail(action, `Health too low (${bot.health}) for caged crystal work.`, {
      suggested_next_action: 'eat_food',
    })
  }
  if (!hasPickaxe()) return fail(action, 'No pickaxe in inventory to break iron bars.')

  const target = findEndCrystals(END_CRYSTAL_SCAN_RADIUS).find((c) => isEndCrystalCaged(c)) || null
  if (!target) {
    return ok(action, {
      destroyed: false,
      caged_crystal_found: false,
      suggested_next_action: 'destroy_nearby_end_crystals',
    })
  }

  const yDiff = target.position.y - bot.entity.position.y
  if (yDiff > END_CRYSTAL_MAX_PILLAR_HEIGHT) {
    return ok(action, {
      partial_success: true,
      can_retry: true,
      target: endCrystalJson(target),
      suggested_next_action: 'pillar_up',
      message: 'Caged crystal is high above the bot; bounded action will not tower indefinitely.',
    })
  }

  if (yDiff > 4) {
    const pillar = await pillarUp(Math.min(END_CRYSTAL_MAX_PILLAR_HEIGHT, Math.max(1, Math.ceil(yDiff - 4))))
    return ok(action, {
      partial_success: true,
      can_retry: true,
      target: endCrystalJson(target),
      pillar_result: pillar.result,
      suggested_next_action: 'destroy_caged_end_crystal',
    })
  }

  const bars = findIronBarsAround(target.position, 3)
    .filter((block) => bot.entity.position.distanceTo(block.position) <= 5)
    .slice(0, 6)
  if (bars.length === 0) {
    return ok(action, {
      partial_success: true,
      can_retry: true,
      target: endCrystalJson(target),
      message: 'Cage detected but no reachable iron bars found.',
      suggested_next_action: 'pillar_up',
    })
  }

  try { await equipBestPickaxe() } catch (err) {
    return fail(action, `Could not equip pickaxe: ${errorMessage(err)}`)
  }

  let broken = 0
  for (const bar of bars) {
    const fresh = bot.blockAt(bar.position)
    if (!fresh || fresh.name !== 'iron_bars') continue
    try {
      await bot.lookAt(fresh.position.offset(0.5, 0.5, 0.5), true)
      await withTimeout(bot.dig(fresh), 5000, 'breaking iron bars')
      broken++
    } catch (_) {
      break
    }
  }

  if (broken === 0) {
    return fail(action, 'Could not break any iron bars around caged crystal.', {
      target: endCrystalJson(target),
      can_retry: true,
    })
  }

  return ok(action, {
    partial_success: true,
    can_retry: true,
    bars_broken: broken,
    target: endCrystalJson(target),
    suggested_next_action: 'destroy_end_crystal',
  })
}

async function destroyNearbyEndCrystals() {
  const action = 'destroy_nearby_end_crystals'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError

  let attempted = 0
  let destroyed = 0
  let lastResult = null
  const started = Date.now()

  while (Date.now() - started < END_PHASE_TIMEOUT_MS && attempted < 3) {
    const crystals = findEndCrystals(END_CRYSTAL_SCAN_RADIUS)
    if (crystals.length === 0) break
    if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break

    const before = crystals.length
    const result = await destroyEndCrystal()
    attempted++
    lastResult = result
    await waitMs(800)
    const after = findEndCrystals(END_CRYSTAL_SCAN_RADIUS).length
    if (after < before || result.ok) destroyed += Math.max(0, before - after)
    if (!result.ok || (result.result && result.result.suggested_next_action === 'destroy_caged_end_crystal')) break
  }

  const remaining = findEndCrystals(END_CRYSTAL_SCAN_RADIUS).length
  return ok(action, {
    attempted,
    destroyed,
    remaining,
    partial_success: attempted > 0 || remaining === 0,
    milestone_reached: remaining === 0,
    can_retry: remaining > 0,
    last_result: lastResult ? lastResult.result : null,
    suggested_next_action: remaining > 0 ? 'scan_end_crystals' : 'dragon_phase_circle',
  })
}

async function attackPerchedDragon() {
  const action = 'attack_perched_dragon'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError
  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) {
    return fail(action, `Health too low (${bot.health}).`, { suggested_next_action: 'eat_food' })
  }

  const dragon = findEnderDragon()
  if (!dragon) {
    return ok(action, {
      attacked: false,
      dragon_found: false,
      milestone_reached: true,
      suggested_next_action: 'return_to_overworld_via_end_portal',
    })
  }
  if (!isDragonLikelyPerched(dragon)) {
    return ok(action, {
      attacked: false,
      dragon_perched: false,
      partial_success: true,
      can_retry: true,
      dragon: entityJson(dragon),
      suggested_next_action: 'attack_dragon_with_bow',
    })
  }

  try { await equipBestMeleeWeapon() } catch (_) {}
  const started = Date.now()
  let swings = 0
  while (Date.now() - started < END_DRAGON_ATTACK_MS) {
    const current = refreshEntity(dragon)
    if (!current) break
    if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break

    const dist = bot.entity.position.distanceTo(current.position)
    if (dist > 6) {
      try {
        await withTimeout(
          bot.pathfinder.goto(new goals.GoalNear(current.position.x, current.position.y, current.position.z, 5)),
          3000,
          'approaching perched dragon'
        )
      } catch (_) {}
    } else {
      try {
        await bot.lookAt(current.position.offset(0, 1, 0), true)
        await withTimeout(bot.attack(current), 1000, 'attacking perched dragon')
        swings++
      } catch (_) {}
      await waitMs(700)
    }
  }

  stopMovement()
  return ok(action, {
    attacked: swings > 0,
    swings,
    dragon_present: Boolean(refreshEntity(dragon)),
    health: typeof bot.health === 'number' ? bot.health : null,
    suggested_next_action: refreshEntity(dragon) ? 'fight_dragon_phase' : 'return_to_overworld_via_end_portal',
  })
}

async function attackDragonWithBow() {
  const action = 'attack_dragon_with_bow'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError

  const dragon = findEnderDragon()
  if (!dragon) {
    return ok(action, {
      shot: false,
      dragon_found: false,
      milestone_reached: true,
      suggested_next_action: 'return_to_overworld_via_end_portal',
    })
  }
  if (bot.entity.position.distanceTo(dragon.position) > END_DRAGON_BOW_RANGE) {
    return ok(action, {
      shot: false,
      dragon: entityJson(dragon),
      partial_success: true,
      can_retry: true,
      suggested_next_action: 'fight_dragon_phase',
    })
  }

  return await shootEntityWithBow(action, dragon)
}

async function dragonPhaseCrystals() {
  const action = 'dragon_phase_crystals'
  const endError = requireEnd(action)
  if (endError) return endError
  const crystals = findEndCrystals(END_CRYSTAL_SCAN_RADIUS)
  if (crystals.length === 0) {
    return ok(action, {
      milestone_reached: true,
      crystals_remaining: 0,
      suggested_next_action: 'dragon_phase_circle',
    })
  }
  const result = await destroyNearbyEndCrystals()
  return ok(action, {
    crystals_remaining: findEndCrystals(END_CRYSTAL_SCAN_RADIUS).length,
    partial_success: true,
    can_retry: true,
    inner_result: result.result,
    suggested_next_action: 'fight_dragon_phase',
  })
}

async function dragonPhaseCircle() {
  const action = 'dragon_phase_circle'
  const endError = requireEnd(action)
  if (endError) return endError
  const survival = await handleEndSurvivalPreflight(action)
  if (survival) return survival

  const dragon = findEnderDragon()
  if (!dragon) {
    return ok(action, {
      milestone_reached: true,
      dragon_found: false,
      suggested_next_action: 'return_to_overworld_via_end_portal',
    })
  }
  if (isDragonLikelyPerched(dragon)) {
    return ok(action, {
      partial_success: true,
      dragon_perched: true,
      suggested_next_action: 'dragon_phase_perch',
    })
  }

  const shot = await attackDragonWithBow()
  return ok(action, {
    partial_success: shot.ok,
    can_retry: true,
    inner_result: shot.result,
    suggested_next_action: 'fight_dragon_phase',
  })
}

async function dragonPhasePerch() {
  const action = 'dragon_phase_perch'
  const endError = requireEnd(action)
  if (endError) return endError
  const survival = await handleEndSurvivalPreflight(action)
  if (survival) return survival

  const bedBombEnabled = (process.env.END_BED_BOMB_ENABLED || '').trim() === '1'
  const hasBed = [...BED_ITEM_NAMES].some((n) => countItemInInventory(n) > 0)
  if (bedBombEnabled && hasBed && typeof bot.health === 'number' && bot.health > LOW_HEALTH_THRESHOLD + 6) {
    const bed = await useBedBomb()
    return ok(action, {
      partial_success: bed.ok,
      bed_bomb_attempted: true,
      inner_result: bed.result,
      suggested_next_action: 'fight_dragon_phase',
    })
  }

  const melee = await attackPerchedDragon()
  return ok(action, {
    partial_success: melee.ok,
    bed_bomb_attempted: false,
    inner_result: melee.result,
    suggested_next_action: 'fight_dragon_phase',
  })
}

async function fightDragonPhase() {
  const action = 'fight_dragon_phase'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError

  const survival = await handleEndSurvivalPreflight(action)
  if (survival) return survival

  const endermen = findNearbyEndermen(ENDERMAN_AVOID_RADIUS)
  if (endermen.length > 0) {
    await lookDownAroundEndermen()
  }

  const crystals = findEndCrystals(END_CRYSTAL_SCAN_RADIUS)
  if (crystals.length > 0) {
    const phase = await dragonPhaseCrystals()
    return ok(action, {
      phase: 'crystals',
      crystals_remaining: findEndCrystals(END_CRYSTAL_SCAN_RADIUS).length,
      inner_result: phase.result,
      suggested_next_action: 'fight_dragon_phase',
      can_retry: true,
    })
  }

  const dragon = findEnderDragon()
  if (!dragon) {
    return ok(action, {
      phase: 'complete',
      dragon_found: false,
      milestone_reached: true,
      suggested_next_action: 'return_to_overworld_via_end_portal',
    })
  }

  const phaseName = isDragonLikelyPerched(dragon) ? 'perch' : 'circle'
  const phase = phaseName === 'perch' ? await dragonPhasePerch() : await dragonPhaseCircle()
  return ok(action, {
    phase: phaseName,
    dragon: entityJson(dragon),
    inner_result: phase.result,
    suggested_next_action: 'fight_dragon_phase',
    can_retry: true,
  })
}

async function returnToOverworldViaEndPortal() {
  const action = 'return_to_overworld_via_end_portal'
  if (!bot.entity) return fail(action, 'Bot not ready.')
  const endError = requireEnd(action)
  if (endError) return endError

  const dragon = findEnderDragon()
  if (dragon) {
    return fail(action, 'Ender Dragon is still present; return portal should only be used after dragon death.', {
      dragon: entityJson(dragon),
      suggested_next_action: 'fight_dragon_phase',
    })
  }

  const portalId = bot.registry.blocksByName.end_portal?.id
  if (!portalId) return fail(action, 'end_portal block not in registry.')
  const portal = bot.findBlock({ matching: portalId, maxDistance: END_EXIT_PORTAL_RADIUS })
  if (!portal) {
    return fail(action, `No End exit portal found within ${END_EXIT_PORTAL_RADIUS} blocks.`, {
      can_retry: true,
      suggested_next_action: 'scan_for_specific_block',
    })
  }

  const beforeDim = getBotDimension()
  try {
    await gotoPositionWithTimeout(portal.position, MOVEMENT_PATH_TIMEOUT_MS)
  } catch (_) {}

  const dimensionChanged = await new Promise((resolve) => {
    let interval = null, timeout = null
    interval = setInterval(() => {
      if (getBotDimension() !== beforeDim) {
        clearInterval(interval); clearTimeout(timeout); resolve(true)
      }
    }, 500)
    timeout = setTimeout(() => { clearInterval(interval); resolve(false) }, PORTAL_WAIT_TIMEOUT_MS)
  })

  if (!dimensionChanged) {
    return fail(action, 'Entered End portal area but dimension did not change.', {
      portal: blockJson(portal),
      can_retry: true,
    })
  }

  return ok(action, {
    from: beforeDim,
    to: getBotDimension(),
    position: bot.entity ? positionJson(bot.entity.position) : null,
  })
}

// ---------------------------------------------------------------------------
// Movement and positioning actions
// ---------------------------------------------------------------------------

// find_safe_workspace — pathfind to a flat open area and remember it as a workspace.
async function findSafeWorkspace(requestedRadius, purpose) {
  if (!bot.entity) return fail('find_safe_workspace', 'Bot not ready.')
  const radius = Math.min(WORKSPACE_MAX_RADIUS, Math.max(8, requestedRadius || WORKSPACE_DEFAULT_RADIUS))
  const resolvedPurpose = WORKSPACE_PURPOSES.has(purpose) ? purpose : 'general'
  const target = findWorkspacePosition(radius)
  if (!target) return fail('find_safe_workspace', `No safe workspace found within radius ${radius}.`)
  try {
    await gotoPositionWithTimeout(target, WORKSPACE_PATH_TIMEOUT_MS)
  } catch (err) {
    return fail('find_safe_workspace', `Path to workspace failed: ${errorMessage(err)}`)
  }

  const openSpots = countAdjacentPlaceableSpots(target)
  const openSpaceScore = Math.round((openSpots / 4) * 100) / 100
  const canPlaceCraftingTable = openSpots >= 1
  const canPlaceFurnace        = openSpots >= 1
  const canPlaceChest          = openSpots >= 1
  const nearbyHostileCount = nearbyEntitiesJson(16).filter(e => e.hostile).length
  const safe = nearbyHostileCount === 0

  rememberWaypointAt('workspace', 'workspace', target)

  const suggestedNextAction = workspaceSuggestedNextAction(resolvedPurpose, canPlaceCraftingTable, canPlaceFurnace, canPlaceChest)

  return ok('find_safe_workspace', {
    position: positionJson(target),
    workspace_position: positionJson(target),
    radius,
    purpose: resolvedPurpose,
    safe,
    nearby_hostiles: nearbyHostileCount,
    open_space_score: openSpaceScore,
    can_place_crafting_table: canPlaceCraftingTable,
    can_place_furnace: canPlaceFurnace,
    can_place_chest: canPlaceChest,
    suggested_next_action: suggestedNextAction,
  })
}

// setup_workspace — navigate to a safe area and place requested crafting stations.
async function setupWorkspace(args) {
  if (!bot.entity) return fail('setup_workspace', 'Bot not ready.')

  const needCraftingTable = args.need_crafting_table !== false
  const needFurnace       = args.need_furnace === true
  const needChest         = args.need_chest === true
  const radius = Math.min(WORKSPACE_MAX_RADIUS, Math.max(8, args.radius || WORKSPACE_DEFAULT_RADIUS))

  // --- Step 1: determine workspace position ---
  let workspacePos = bot.entity.position.floored()
  const currentScore    = workspaceOpenSpaceScore(workspacePos, 3)
  const currentHostiles = nearbyEntitiesJson(16).filter(e => e.hostile).length
  const currentlySafe   = currentScore >= 0.5 && currentHostiles === 0 && !isBotInLiquid()

  if (!currentlySafe) {
    // Prefer returning to known workspace in same dimension if within radius
    const knownWp  = waypointStore.get('workspace')
    const dim      = getBotDimension()
    let navigated  = false

    if (knownWp && knownWp.dimension === dim) {
      const knownPos = new Vec3(knownWp.x, knownWp.y, knownWp.z)
      if (bot.entity.position.distanceTo(knownPos) <= radius) {
        try {
          await gotoPositionWithTimeout(knownPos, WORKSPACE_PATH_TIMEOUT_MS)
          workspacePos = bot.entity.position.floored()
          navigated    = true
        } catch (_) { /* fall through */ }
      }
    }

    if (!navigated) {
      const target = findWorkspacePosition(radius)
      if (!target) {
        return fail('setup_workspace', `No safe workspace found within radius ${radius}.`, {
          failure_type: 'no_safe_workspace',
          stop_reason: 'area_cramped',
          suggested_next_action: 'return_to_surface',
          can_retry: true,
        })
      }
      try {
        await gotoPositionWithTimeout(target, WORKSPACE_PATH_TIMEOUT_MS)
        workspacePos = bot.entity.position.floored()
      } catch (err) {
        return fail('setup_workspace', `Could not navigate to workspace: ${errorMessage(err)}`)
      }
    }
  }

  // --- Step 2: place stations as requested ---
  const placed  = []
  const missing = []

  async function tryPlaceStation(needed, itemName, findFn, placeFn, label) {
    if (!needed) return Boolean(findFn(STATION_USE_RADIUS))
    if (findFn(STATION_USE_RADIUS)) return true          // already present and usable
    if (!firstInventoryItemByNames([itemName])) { missing.push(label); return false }
    const r = await placeFn()
    if (r.ok) { placed.push(label); return true }
    missing.push(label)
    return false
  }

  const hasCraftingTable = await tryPlaceStation(needCraftingTable, 'crafting_table', findNearbyCraftingTable, placeCraftingTable, 'crafting_table')
  const hasFurnace       = await tryPlaceStation(needFurnace,       'furnace',        findNearbyFurnace,       placeFurnace,       'furnace')
  const hasChest         = await tryPlaceStation(needChest,         'chest',          findNearbyChest,         placeChest,         'chest')

  // --- Step 3: remember and respond ---
  rememberWaypointAt('workspace', 'workspace', workspacePos)

  const hostilesFinal = nearbyEntitiesJson(16).filter(e => e.hostile).length
  const safe          = hostilesFinal === 0 && !isBotInLiquid()

  let suggestedNextAction = null
  if (missing.includes('crafting_table'))  suggestedNextAction = 'craft_crafting_table'
  else if (missing.includes('furnace'))    suggestedNextAction = 'craft_furnace'
  else if (missing.includes('chest'))      suggestedNextAction = 'craft_chest'

  // If a known workspace exists far away in same dim, suggest returning instead
  const knownWpFar = waypointStore.get('workspace')
  if (!suggestedNextAction && knownWpFar && knownWpFar.dimension === getBotDimension()) {
    const dist = bot.entity.position.distanceTo(new Vec3(knownWpFar.x, knownWpFar.y, knownWpFar.z))
    if (dist > radius) suggestedNextAction = 'return_to_waypoint'
  }

  return ok('setup_workspace', {
    workspace_position: positionJson(workspacePos),
    has_crafting_table: needCraftingTable ? hasCraftingTable : Boolean(findNearbyCraftingTable(STATION_USE_RADIUS)),
    has_furnace:        needFurnace       ? hasFurnace       : Boolean(findNearbyFurnace(STATION_USE_RADIUS)),
    has_chest:          needChest         ? hasChest         : Boolean(findNearbyChest(STATION_USE_RADIUS)),
    placed,
    missing,
    safe,
    suggested_next_action: suggestedNextAction,
  })
}

async function approachStation(station, requestedRadius) {
  if (!bot.entity) return fail('approach_station', 'Bot not ready.')
  const stationName = STATION_BLOCK_TYPES.has(station) ? station : 'crafting_table'
  const radius = Math.max(2, Math.min(STATION_USE_RADIUS, requestedRadius || STATION_APPROACH_RADIUS))
  const stationBlock = findNearestStationBlock(stationName, STATION_SCAN_RADIUS)

  if (!stationBlock) {
    return fail('approach_station', `No ${stationName} visible within radius ${STATION_SCAN_RADIUS}.`, {
      failure_type: 'missing_station',
      stop_reason: `no_${stationName}_nearby`,
      station_needed: stationName,
      possible_next_actions: ['setup_workspace', 'place_crafting_table', 'return_to_workspace', 'look_around'],
      can_retry: true,
    })
  }

  const startDistance = bot.entity.position.distanceTo(stationBlock.position)
  let pathError = null
  try {
    await gotoPositionNearWithTimeout(stationBlock.position, radius, WORKSPACE_PATH_TIMEOUT_MS)
  } catch (err) {
    pathError = err
  }

  const finalDistance = bot.entity.position.distanceTo(stationBlock.position)
  const usableRadius = usableRadiusForStation(stationName)
  const reached = finalDistance <= radius
  const usableForStation = finalDistance <= usableRadius
  const distanceImproved = finalDistance < startDistance
  const baseResult = {
    station: stationName,
    station_needed: stationName,
    station_position: positionJson(stationBlock.position),
    start_distance: startDistance,
    final_distance: finalDistance,
    distance_improved: distanceImproved,
    target_radius: radius,
    usable_radius: usableRadius,
    usable_for_station: usableForStation,
  }

  if (reached) {
    return ok('approach_station', {
      ...baseResult,
      reached: true,
      usable: true,
    })
  }

  if (distanceImproved || usableForStation) {
    return {
      ok: false,
      action: 'approach_station',
      result: {
        ...baseResult,
        reached: false,
        partial_success: true,
        failure_type: 'station_not_reached',
        stop_reason: 'still_outside_requested_radius',
        possible_next_actions: possibleNextActionsForStation(stationName, usableForStation),
        can_retry: true,
      },
      error: 'Approached station but did not reach requested radius.',
    }
  }

  return fail('approach_station', `Could not approach ${stationName}: ${pathError ? errorMessage(pathError) : 'station did not get closer'}`, {
    ...baseResult,
    reached: false,
    partial_success: false,
    failure_type: 'station_not_reached',
    stop_reason: pathError ? 'path_timeout' : 'still_outside_requested_radius',
    station_needed: stationName,
    possible_next_actions: ['approach_station', 'setup_workspace', 'look_around'],
    can_retry: true,
  })
}

function usableRadiusForStation(stationName) {
  if (stationName === 'crafting_table') return STATION_USE_RADIUS
  if (stationName === 'furnace') return STATION_USE_RADIUS
  if (stationName === 'chest') return STATION_USE_RADIUS
  return STATION_USE_RADIUS
}

function possibleNextActionsForStation(stationName, usableForStation) {
  if (stationName === 'crafting_table') {
    const actions = ['approach_station', 'craft_stone_pickaxe', 'craft_wooden_pickaxe', 'craft_furnace', 'look_around']
    return usableForStation ? actions : ['approach_station', 'craft_stone_pickaxe', 'look_around']
  }
  if (stationName === 'furnace') {
    return usableForStation
      ? ['approach_station', 'smelt_iron', 'smelt_item', 'look_around']
      : ['approach_station', 'look_around']
  }
  if (stationName === 'chest') {
    return ['approach_station', 'look_around']
  }
  return ['approach_station', 'look_around']
}

// dig_staircase — carve a 1×2 angled corridor safely.
async function digStaircase(direction, maxSteps) {
  if (!bot.entity) return fail('dig_staircase', 'Bot not ready.')
  if (!hasPickaxe())  return fail('dig_staircase', 'No pickaxe in inventory.')

  const steps = Math.min(STAIRCASE_MAX_STEPS, Math.max(1, maxSteps || 8))
  const goingUp = direction === 'up_to_surface'
  const rawDir = direction === 'toward_target' || direction === 'down_to_target' || direction === 'down'
    ? yawToCardinalOffset(bot.entity.yaw)
    : goingUp
      ? yawToCardinalOffset(bot.entity.yaw)
      : resolveMovementDirection(direction)

  if (!rawDir || rawDir.y !== 0) {
    return fail('dig_staircase', `Unknown direction '${direction}'. Use north/south/east/west/up_to_surface/down.`)
  }

  const dirVec = new Vec3(rawDir.x, 0, rawDir.z)
  let stepsDone = 0

  for (let i = 0; i < steps; i++) {
    if (!bot.entity) break
    if (goingUp && isSkyVisible(bot.entity.position.floored())) break

    const base = bot.entity.position.floored()

    // Blocks to clear this step (2-high corridor + stair tread)
    const todig = goingUp
      ? [base.offset(dirVec.x, 0, dirVec.z), base.offset(dirVec.x, 1, dirVec.z), base.offset(dirVec.x, 2, dirVec.z)]
      : [base.offset(dirVec.x, 0, dirVec.z), base.offset(dirVec.x, 1, dirVec.z), base.offset(dirVec.x, -1, dirVec.z)]

    let failed = false
    for (const pos of todig) {
      const block = bot.blockAt(pos)
      if (!block || canReplaceBlock(block)) continue
      if (isLiquidBlock(block) || isDangerousAdjacent(block))          { failed = true; break }
      if (NEVER_MINE_BLOCK_NAMES.has(block.name) || block.name === 'bedrock') { failed = true; break }
      try {
        await equipBestPickaxe()
        await bot.lookAt(block.position.offset(0.5, 0.5, 0.5), true)
        await digBlockWithTimeout(block, STAIRCASE_DIG_TIMEOUT_MS)
      } catch (_) { failed = true; break }
    }
    if (failed) break

    const nextPos = goingUp
      ? base.offset(dirVec.x, 1, dirVec.z)
      : base.offset(dirVec.x, -1, dirVec.z)

    try {
      await withTimeout(
        bot.pathfinder.goto(new goals.GoalBlock(nextPos.x, nextPos.y, nextPos.z)),
        STAIRCASE_STEP_TIMEOUT_MS, 'staircase step'
      )
    } catch (_) { /* partial step is OK */ }

    stepsDone++
    await delay(100)
  }

  return ok('dig_staircase', {
    steps: stepsDone, direction,
    partial_success: stepsDone > 0,
    can_retry: stepsDone < steps,
    position: bot.entity ? positionJson(bot.entity.position) : null
  })
}

// return_to_surface — pathfind up or dig staircase to reach open sky.
async function returnToSurface() {
  if (!bot.entity) return fail('return_to_surface', 'Bot not ready.')

  const base = bot.entity.position.floored()
  if (isSkyVisible(base)) {
    return ok('return_to_surface', { already_at_surface: true, position: positionJson(bot.entity.position) })
  }

  // Try pathfinding to progressively higher positions
  for (let dy = 4; dy <= 64; dy += 4) {
    const target = nearestSafeStandPosition(base.offset(0, dy, 0), 4)
    if (!target) continue
    try {
      await gotoPositionWithTimeout(target, MOVEMENT_PATH_TIMEOUT_MS)
      if (isSkyVisible(bot.entity.position.floored())) {
        return ok('return_to_surface', { reached: true, position: positionJson(bot.entity.position) })
      }
    } catch (_) { continue }
    break
  }

  // Fall back to dig staircase upward
  const stairResult = await digStaircase('up_to_surface', 24)
  return ok('return_to_surface', {
    partial_success: stairResult.ok,
    reached_surface: bot.entity ? isSkyVisible(bot.entity.position.floored()) : false,
    position: bot.entity ? positionJson(bot.entity.position) : null,
    can_retry: true
  })
}

// pillar_up — jump + place block underfoot repeatedly.
async function pillarUp(requestedHeight, blockName) {
  if (!bot.entity) return fail('pillar_up', 'Bot not ready.')
  const maxH = Math.min(PILLAR_MAX_HEIGHT, Math.max(1, requestedHeight || 4))

  const pillarItem = resolvePillarItem(blockName)
  if (!pillarItem) return fail('pillar_up', 'No pillar material (need cobblestone, dirt, or planks).')

  let gained = 0
  for (let i = 0; i < maxH; i++) {
    if (!bot.entity) break

    const startFeet = bot.entity.position.floored()
    if (!canReplaceBlock(bot.blockAt(startFeet.offset(0, 2, 0)))) break // head blocked

    const refBlock = bot.blockAt(startFeet.offset(0, -1, 0))
    if (!refBlock || !isSolidBlock(refBlock)) break

    try {
      await bot.equip(pillarItem, 'hand')
      await bot.look(bot.entity.yaw, Math.PI / 2, true) // look down
    } catch (_) { break }

    // Jump and place block at original feet position while airborne
    bot.setControlState('jump', true)
    await delay(220)
    bot.setControlState('jump', false)

    try {
      await placeBlockWithTimeout(refBlock, new Vec3(0, 1, 0), PILLAR_STEP_TIMEOUT_MS)
    } catch (_) { /* may still have placed */ }

    await delay(380) // wait for landing

    if (bot.entity && bot.entity.position.y > startFeet.y + 0.5) {
      gained++
    } else {
      break
    }
  }

  bot.clearControlStates()
  return ok('pillar_up', {
    height_gained: gained,
    requested_height: maxH,
    partial_success: gained > 0,
    can_retry: gained < maxH,
    position: bot.entity ? positionJson(bot.entity.position) : null
  })
}

// bridge_gap — sneak-place blocks forward over a gap.
async function bridgeGap(direction, requestedLength, blockName) {
  if (!bot.entity) return fail('bridge_gap', 'Bot not ready.')

  const maxLen = Math.min(BRIDGE_MAX_LENGTH, Math.max(1, requestedLength || 4))
  const dirVec = resolveMovementDirection(direction || 'forward')
  if (!dirVec || dirVec.y !== 0) return fail('bridge_gap', `Unknown direction '${direction}'.`)

  const bridgeItem = blockName ? resolvePillarItem(blockName)
    : firstInventoryItemByNames([...BRIDGE_BLOCK_NAMES, ...Array.from(PLANK_ITEM_NAMES)])
  if (!bridgeItem) return fail('bridge_gap', 'No bridge material (cobblestone, dirt, or planks).')

  // Face the bridge direction
  try { await bot.look(Math.atan2(-dirVec.x, dirVec.z), 0, true) } catch (_) {}

  let placed = 0
  bot.setControlState('sneak', true)

  for (let step = 0; step < maxLen; step++) {
    if (!bot.entity) break

    const feetPos    = bot.entity.position.floored()
    const nextFloor  = bot.blockAt(feetPos.offset(dirVec.x, -1, dirVec.z))
    const nextBody   = bot.blockAt(feetPos.offset(dirVec.x,  0, dirVec.z))

    if (nextBody && isSolidBlock(nextBody)) break // wall in the way

    // Stop if next floor is lava
    if (nextFloor && isLiquidBlock(nextFloor) && nextFloor.name.includes('lava')) break

    if (!nextFloor || !isSolidBlock(nextFloor)) {
      // Gap ahead — place bridge block from current floor reference
      const curFloor = bot.blockAt(feetPos.offset(0, -1, 0))
      if (!curFloor || !isSolidBlock(curFloor)) break

      const faceVec = new Vec3(dirVec.x, 0, dirVec.z)
      try {
        await bot.equip(bridgeItem, 'hand')
        await bot.lookAt(faceCenter(curFloor.position, faceVec), true)
        await delay(80)
        await placeBlockWithTimeout(curFloor, faceVec, BRIDGE_STEP_TIMEOUT_MS)
        placed++
        await delay(200)
      } catch (_) { break }
    }

    const target = feetPos.offset(dirVec.x, 0, dirVec.z)
    try {
      await withTimeout(
        bot.pathfinder.goto(new goals.GoalBlock(target.x, target.y, target.z)),
        3000, 'bridge step'
      )
    } catch (_) { break }

    await delay(100)
  }

  bot.setControlState('sneak', false)
  return ok('bridge_gap', {
    placed, direction: direction || 'forward',
    partial_success: placed > 0,
    can_retry: placed < maxLen,
    position: bot.entity ? positionJson(bot.entity.position) : null
  })
}

// place_block_in_direction — thin wrapper for simple directional placement.
async function placeBlockInDirection(itemName, direction) {
  if (!itemName) return fail('place_block_in_direction', 'args.item is required.')
  if (!isAllowedPlaceItem(itemName)) return fail('place_block_in_direction', `Item '${itemName}' is not allowed.`)

  const blockItem = findPlaceableItem(itemName)
  return await placeItemSafely(itemName, {
    action: 'place_block_in_direction',
    item: blockItem,
    direction: direction || 'forward',
    mode: 'directional',
    verifyBlockNames: blockNamesForItem(itemName),
    requireOpenArea: false,
    avoidEntities: true,
    avoidWater: false,
    avoidLava: true,
  })
}

// mlg_water_bucket — place water below while falling to cancel fall damage.
async function mlgWaterBucket() {
  if (!bot.entity) return fail('mlg_water_bucket', 'Bot not ready.')

  const velY = (bot.entity.velocity && bot.entity.velocity.y) || 0
  if (velY >= -0.3) {
    return ok('mlg_water_bucket', { not_applicable: true, reason: 'Bot is not falling fast enough.' })
  }

  const waterItem = firstInventoryItemByNames(['water_bucket'])
  if (!waterItem) return fail('mlg_water_bucket', 'No water_bucket in inventory.')

  try { await bot.equip(waterItem, 'hand') } catch (err) {
    return fail('mlg_water_bucket', `Could not equip water bucket: ${errorMessage(err)}`)
  }

  await bot.look(bot.entity.yaw, Math.PI / 2, true) // look straight down

  // Find the nearest solid block below
  const feetPos = bot.entity.position.floored()
  let refBlock = null
  for (let dy = -1; dy >= -8; dy--) {
    const b = bot.blockAt(feetPos.offset(0, dy, 0))
    if (b && !canReplaceBlock(b) && !isLiquidBlock(b)) { refBlock = b; break }
  }

  if (!refBlock) return fail('mlg_water_bucket', 'No solid block found below for water placement.')

  try {
    await placeBlockWithTimeout(refBlock, new Vec3(0, 1, 0), 2000)
  } catch (err) {
    await delay(200)
    const check = bot.blockAt(feetPos.offset(0, -1, 0))
    if (check && check.name.includes('water')) {
      return ok('mlg_water_bucket', { placed: true, position: positionJson(check.position) })
    }
    return fail('mlg_water_bucket', `Placement failed: ${errorMessage(err)}`)
  }

  return ok('mlg_water_bucket', { placed: true, position: bot.entity ? positionJson(bot.entity.position) : null })
}

// enter_boat — mount a nearby boat, or place one if inventory has a boat item.
async function enterBoat() {
  if (!bot.entity) return fail('enter_boat', 'Bot not ready.')

  let boatEntity = findNearestBoatEntity(8)
  if (!boatEntity) {
    const boatItem = firstInventoryItemByNames(Array.from(BOAT_ITEM_NAMES))
    if (!boatItem) return fail('enter_boat', 'No boat entity nearby and no boat item in inventory.')

    const placed = await placeBoat()
    if (!placed.ok) return fail('enter_boat', `Could not place boat: ${placed.error}`)
    await delay(500)
    boatEntity = findNearestBoatEntity(8)
    if (!boatEntity) return fail('enter_boat', 'Placed boat but entity not found.')
  }

  try {
    await withTimeout(
      bot.pathfinder.goto(new goals.GoalNear(boatEntity.position.x, boatEntity.position.y, boatEntity.position.z, 2)),
      MOVEMENT_PATH_TIMEOUT_MS, 'pathing to boat'
    )
  } catch (_) { /* may be close enough */ }

  try {
    await withTimeout(bot.mount(boatEntity), 3000, 'mounting boat')
  } catch (err) {
    return fail('enter_boat', `Failed to mount boat: ${errorMessage(err)}`)
  }

  return ok('enter_boat', { boatType: boatEntity.name || 'boat', position: positionJson(boatEntity.position) })
}

// exit_boat — dismount safely.
async function exitBoat() {
  try {
    bot.dismount()
    await delay(300)
  } catch (err) {
    return fail('exit_boat', `Failed to dismount: ${errorMessage(err)}`)
  }
  return ok('exit_boat', { position: bot.entity ? positionJson(bot.entity.position) : null })
}

// set_sneak — toggle sneak control state.
function setSneak(enabled) {
  bot.setControlState('sneak', Boolean(enabled))
  return ok('set_sneak', { sneak: Boolean(enabled) })
}

// set_sprint — toggle sprint control state.
function setSprint(enabled) {
  bot.setControlState('sprint', Boolean(enabled))
  return ok('set_sprint', { sprint: Boolean(enabled) })
}

// recover_position — clear controls, escape liquid or stuck state.
async function recoverPosition() {
  stopMovement()
  await delay(100)

  if (!bot.entity) return ok('recover_position', { action_taken: 'cleared_controls' })

  if (isBotInLiquid()) {
    bot.setControlState('jump', true)
    await delay(600)
    bot.setControlState('jump', false)
    await delay(300)
    return ok('recover_position', {
      action_taken: 'attempted_liquid_escape',
      in_liquid: isBotInLiquid(),
      partial_success: !isBotInLiquid(),
      can_retry: isBotInLiquid(),
      position: positionJson(bot.entity.position)
    })
  }

  const positionBefore = bot.entity.position.clone()
  const safeSpot = nearestSafeStandPosition(bot.entity.position.floored(), 3)
  if (safeSpot && safeSpot.distanceTo(bot.entity.position.floored()) > 0.1) {
    try {
      await withTimeout(
        bot.pathfinder.goto(new goals.GoalBlock(safeSpot.x, safeSpot.y, safeSpot.z)),
        5000, 'recover position'
      )
    } catch (_) {}
  }

  const positionAfter = bot.entity.position
  const distanceMoved = positionBefore.distanceTo(positionAfter)
  if (distanceMoved < 0.5) {
    return fail('recover_position', 'No meaningful movement during recovery.', {
      failure_type: 'no_progress',
      position_before: positionJson(positionBefore),
      position_after: positionJson(positionAfter),
      distance_moved: distanceMoved,
    })
  }

  return ok('recover_position', {
    action_taken: 'moved_to_safe_position',
    position: positionJson(positionAfter),
    distance_moved: distanceMoved,
  })
}

// ---------------------------------------------------------------------------
// Inventory / equipment
// ---------------------------------------------------------------------------

function checkInventory() {
  const items = inventoryJson()
  const counts = {}
  for (const item of items) { counts[item.name] = (counts[item.name] || 0) + item.count }
  return ok('check_inventory', {
    inventory: items,
    counts,
    equipment: getEquipmentJson(),
    hotbar: items.filter(i => i.slot >= 36 && i.slot <= 44)
      .sort((a, b) => a.slot - b.slot)
      .map(i => ({ slot: i.slot - 36, name: i.name, count: i.count }))
  })
}

// ---------------------------------------------------------------------------
// Sensing actions
// ---------------------------------------------------------------------------

function checkTimeOfDay() {
  const t = timeJson()
  if (!t) return fail('check_time_of_day', 'Time info not available.')
  return ok('check_time_of_day', {
    timeOfDay: t.timeOfDay,
    day: t.day,
    isDay: t.isDay,
    isNight: !t.isDay,
    moonPhase: t.moonPhase
  })
}

function checkLightLevel() {
  if (!bot.entity) return fail('check_light_level', 'Bot not ready.')
  const pos = bot.entity.position.floored()
  const blockAbove = bot.blockAt(pos.offset(0, 1, 0))

  const blockLight = (blockAbove && typeof blockAbove.light === 'number') ? blockAbove.light : null
  const skyLight   = (blockAbove && typeof blockAbove.skyLight === 'number') ? blockAbove.skyLight : null

  // Count nearby light-emitting blocks as a heuristic fallback
  let lightSourceCount = 0
  for (const name of ['torch', 'wall_torch', 'lantern', 'soul_lantern', 'sea_lantern', 'glowstone', 'shroomlight', 'magma_block']) {
    const bd = bot.registry.blocksByName[name]
    if (bd && bot.findBlock({ matching: bd.id, maxDistance: 5 })) lightSourceCount++
  }

  const time = timeJson()
  const isDay = time ? time.isDay : null
  const estimatedLight = Math.max(
    blockLight ?? 0,
    skyLight ?? 0,
    isDay === true ? 15 : 0,
    lightSourceCount > 0 ? Math.min(15, 7 + lightSourceCount * 2) : 0
  )

  return ok('check_light_level', {
    block_light: blockLight,
    sky_light: skyLight,
    is_day: isDay,
    light_sources_nearby: lightSourceCount,
    estimated_light: estimatedLight,
    safe_from_spawns: estimatedLight >= 8,
    recommendation: estimatedLight < 8 ? 'Estimated light < 8. Place torches to prevent hostile mob spawning.' : null
  })
}

function checkBiome() {
  if (!bot.entity) return fail('check_biome', 'Bot not ready.')
  const pos = bot.entity.position.floored()
  let biomeInfo = null

  try {
    const block = bot.blockAt(pos)
    if (block && block.biome && block.biome.id !== undefined) {
      biomeInfo = { id: block.biome.id, name: block.biome.name || block.biome.displayName || `id_${block.biome.id}` }
    }
  } catch (_) {}

  if (!biomeInfo) {
    try {
      if (bot.world && typeof bot.world.getBiome === 'function') {
        const id = bot.world.getBiome(pos)
        const reg = bot.registry.biomes ? bot.registry.biomes[id] : null
        biomeInfo = { id, name: reg ? (reg.name || reg.displayName || `id_${id}`) : `biome_${id}` }
      }
    } catch (_) {}
  }

  return ok('check_biome', {
    position: positionJson(pos),
    dimension: getBotDimension(),
    biome: biomeInfo || { id: null, name: 'unavailable' }
  })
}

function scanForHostiles(requestedRadius) {
  if (!bot.entity) return fail('scan_for_hostiles', 'Bot not ready.')
  const radius = Math.min(64, Math.max(8, requestedRadius || 32))
  const hostiles = nearbyEntitiesJson(radius).filter(e => e.hostile)

  return ok('scan_for_hostiles', {
    radius,
    count: hostiles.length,
    immediate_danger: hostiles.some(e => e.distance <= 8),
    hostiles,
    recommendation: hostiles.length === 0 ? null
      : hostiles.some(e => e.distance <= 8) ? 'Immediate danger within 8 blocks. Use flee or attack_nearest_hostile.'
      : `${hostiles.length} hostile(s) detected. Nearest at ${hostiles[0].distance.toFixed(1)} blocks.`
  })
}

function scanForPassiveMobs(requestedRadius) {
  if (!bot.entity) return fail('scan_for_passive_mobs', 'Bot not ready.')
  const radius = Math.min(64, Math.max(8, requestedRadius || 32))
  const all = nearbyEntitiesJson(radius)
  const passive = all.filter(e => !e.hostile && PASSIVE_MOB_NAMES.has(e.name))

  return ok('scan_for_passive_mobs', {
    radius,
    count: passive.length,
    mobs: passive.slice(0, 12),
    food_sources: passive.filter(m => FOOD_MOB_NAMES.has(m.name)).length,
    wool_sources: passive.filter(m => m.name === 'sheep').length
  })
}

function scanForChests(requestedRadius) {
  if (!bot.entity) return fail('scan_for_chests', 'Bot not ready.')
  const radius = Math.min(64, Math.max(8, requestedRadius || 16))

  const chests = []
  for (const name of CHEST_BLOCK_NAMES) {
    const bd = bot.registry.blocksByName[name]
    if (!bd) continue
    const found = bot.findBlock({ matching: bd.id, maxDistance: radius })
    if (found) {
      chests.push({ type: name, position: positionJson(found.position), distance: bot.entity.position.distanceTo(found.position) })
    }
  }
  chests.sort((a, b) => a.distance - b.distance)

  return ok('scan_for_chests', { radius, count: chests.length, chests })
}

function scanForSpecificBlock(targets, requestedRadius) {
  if (!bot.entity) return fail('scan_for_specific_block', 'Bot not ready.')
  if (!Array.isArray(targets) || targets.length === 0) {
    return fail('scan_for_specific_block', 'args.targets must be a non-empty array of block names.')
  }

  const radius = Math.min(96, Math.max(8, requestedRadius || 32))
  const scanAllowed = new Set([...ACQUIRE_ALLOWED_TARGETS, ...SCAN_EXTRA_BLOCKS])
  const validTargets = targets.filter(t => typeof t === 'string' && (scanAllowed.has(t) || bot.registry.blocksByName[t]))

  if (validTargets.length === 0) {
    return fail('scan_for_specific_block', `No valid block names in targets: ${targets.slice(0,4).join(', ')}.`)
  }

  const found = []
  for (const name of validTargets.slice(0, 6)) {
    const bd = bot.registry.blocksByName[name]
    if (!bd) continue
    const block = bot.findBlock({ matching: bd.id, maxDistance: radius })
    if (block) {
      found.push({ name, position: positionJson(block.position), distance: bot.entity.position.distanceTo(block.position) })
    }
  }
  found.sort((a, b) => a.distance - b.distance)

  return ok('scan_for_specific_block', { targets: validTargets, radius, count: found.length, found })
}

function scanForLiquids(requestedRadius) {
  if (!bot.entity) return fail('scan_for_liquids', 'Bot not ready.')
  const radius = Math.min(32, Math.max(8, requestedRadius || 16))

  const results = []
  const center = bot.entity.position.floored()
  const seenKeys = new Set()

  for (let dx = -radius; dx <= radius; dx += 2) {
    for (let dy = -4; dy <= 4; dy++) {
      for (let dz = -radius; dz <= radius; dz += 2) {
        if (center.distanceTo(center.offset(dx, dy, dz)) > radius) continue
        const block = bot.blockAt(center.offset(dx, dy, dz))
        if (!block || !isLiquidBlock(block)) continue

        const key = `${Math.round(dx / 4)},${dy},${Math.round(dz / 4)}`
        if (seenKeys.has(key)) continue
        seenKeys.add(key)

        results.push({
          type: block.name.includes('lava') ? 'lava' : 'water',
          position: positionJson(center.offset(dx, dy, dz)),
          distance: bot.entity.position.distanceTo(center.offset(dx, dy, dz)),
          danger: block.name.includes('lava')
        })
      }
    }
  }

  results.sort((a, b) => a.distance - b.distance)
  const nearestLava  = results.find(r => r.type === 'lava')
  const nearestWater = results.find(r => r.type === 'water')

  return ok('scan_for_liquids', {
    radius,
    count: results.length,
    liquids: results.slice(0, 8),
    lava_nearby: Boolean(nearestLava),
    water_nearby: Boolean(nearestWater),
    nearest_lava_distance:  nearestLava  ? Math.round(nearestLava.distance)  : null,
    nearest_water_distance: nearestWater ? Math.round(nearestWater.distance) : null
  })
}

function scanForStructures(requestedRadius) {
  if (!bot.entity) return fail('scan_for_structures', 'Bot not ready.')
  const radius = Math.min(128, Math.max(16, requestedRadius || 48))

  const hints = {}
  for (const [structType, blockNames] of Object.entries(STRUCTURE_INDICATOR_BLOCKS)) {
    for (const name of blockNames) {
      const bd = bot.registry.blocksByName[name]
      if (!bd) continue
      const found = bot.findBlock({ matching: bd.id, maxDistance: radius })
      if (found) {
        const dist = bot.entity.position.distanceTo(found.position)
        if (!hints[structType] || dist < hints[structType].distance) {
          hints[structType] = { indicator_block: name, position: positionJson(found.position), distance: dist }
        }
        break
      }
    }
  }

  const structures = Object.entries(hints)
    .map(([type, data]) => ({ type, ...data }))
    .sort((a, b) => a.distance - b.distance)

  return ok('scan_for_structures', {
    radius,
    hint_count: structures.length,
    structures,
    note: 'Hints based on indicator blocks — not definitive structure detection.'
  })
}

function scanWorkspace() {
  if (!bot.entity) return fail('scan_workspace', 'Bot not ready.')
  const radius = 8
  const craftingTable = findNearbyCraftingTable(radius)
  const furnace = findNearbyFurnace(radius)
  const chest = findNearbyChest(radius)
  const openScore = workspaceOpenSpaceScore(bot.entity.position.floored(), 3)
  const hostiles = nearbyEntitiesJson(10).filter(e => e.hostile)
  const safe = openScore >= 0.35 && hostiles.length === 0 && !isBotInLiquid()

  return ok('scan_workspace', {
    radius,
    position: positionJson(bot.entity.position),
    dimension: getBotDimension(),
    has_crafting_table: Boolean(craftingTable),
    has_furnace: Boolean(furnace),
    has_chest: Boolean(chest),
    stations: {
      crafting_table: blockJson(craftingTable),
      furnace: blockJson(furnace),
      chest: blockJson(chest),
    },
    safe,
    open_space_score: openScore,
    hostile_count: hostiles.length,
  })
}

function workspaceOpenSpaceScore(center, radius) {
  if (!bot.entity) return 0
  let checked = 0
  let open = 0
  for (let dx = -radius; dx <= radius; dx++) {
    for (let dz = -radius; dz <= radius; dz++) {
      const feet = center.offset(dx, 0, dz)
      const floor = bot.blockAt(feet.offset(0, -1, 0))
      const body = bot.blockAt(feet)
      const head = bot.blockAt(feet.offset(0, 1, 0))
      checked++
      if (isSolidBlock(floor) && canReplaceBlock(body) && canReplaceBlock(head) && !isLiquidBlock(body) && !isLiquidBlock(head)) {
        open++
      }
    }
  }
  return checked > 0 ? Number((open / checked).toFixed(2)) : 0
}

function getEquipmentJson() {
  if (!bot.inventory || !Array.isArray(bot.inventory.slots)) return {}
  return {
    head:     slotItemJson(bot.inventory.slots[5]),
    torso:    slotItemJson(bot.inventory.slots[6]),
    legs:     slotItemJson(bot.inventory.slots[7]),
    feet:     slotItemJson(bot.inventory.slots[8]),
    offhand:  slotItemJson(bot.inventory.slots[45]),
    mainhand: slotItemJson(bot.heldItem)
  }
}

function slotItemJson(item) {
  if (!item) return null
  return { name: item.name, count: item.count, slot: item.slot }
}

async function dropItem(itemName, count, force) {
  if (!itemName) return fail('drop_item', 'args.item is required.')
  if (!force && DROP_CRITICAL_ITEMS.has(itemName)) {
    return fail('drop_item', `'${itemName}' is a critical item. Add force=true to allow dropping it.`)
  }

  const iType = itemType(itemName)
  if (!iType) return fail('drop_item', `Unknown item: ${itemName}.`)

  const available = countItemInInventory(itemName)
  if (available === 0) return fail('drop_item', `No ${itemName} in inventory.`)

  const dropCount = count ? Math.min(available, count) : available
  try {
    await bot.toss(iType.id, null, dropCount)
  } catch (err) {
    return fail('drop_item', `Drop failed: ${errorMessage(err)}`)
  }
  return ok('drop_item', { item: itemName, dropped: dropCount, inventory: inventoryJson() })
}

async function equipArmorAction(mode) {
  const m = mode || 'best'
  if (m === 'best') return await equipBestArmor()

  const pieces = [
    { name: `${m}_chestplate`, slot: 'torso' },
    { name: `${m}_leggings`,   slot: 'legs'  },
    { name: `${m}_helmet`,     slot: 'head'  },
    { name: `${m}_boots`,      slot: 'feet'  }
  ]
  const equipped = []
  const missing  = []
  for (const piece of pieces) {
    const inv = firstInventoryItemByNames([piece.name])
    if (!inv) { missing.push(piece.name); continue }
    try {
      await withTimeout(bot.equip(inv, piece.slot), EQUIP_TIMEOUT_MS, `equipping ${piece.name}`)
      equipped.push(piece.name)
    } catch (_) { missing.push(piece.name) }
  }
  if (equipped.length === 0) return fail('equip_armor', `No ${m} armor found in inventory.`)
  return ok('equip_armor', { mode: m, equipped, missing })
}

async function equipToolAction(blockName, toolName) {
  if (toolName) {
    const item = firstInventoryItemByNames([toolName])
    if (!item) return fail('equip_tool', `No ${toolName} in inventory.`)
    try {
      await withTimeout(bot.equip(item, 'hand'), EQUIP_TIMEOUT_MS, `equipping ${toolName}`)
    } catch (err) {
      return fail('equip_tool', `Could not equip ${toolName}: ${errorMessage(err)}`)
    }
    return ok('equip_tool', { equipped: toolName })
  }
  if (blockName) {
    const tool = await equipBestToolForBlock({ name: blockName })
    if (!tool) return fail('equip_tool', `No suitable tool for block '${blockName}'.`)
    return ok('equip_tool', { equipped: tool.name, block: blockName })
  }
  try {
    const pickaxe = await equipBestPickaxe()
    return ok('equip_tool', { equipped: pickaxe.name })
  } catch (err) {
    return fail('equip_tool', `No pickaxe available: ${errorMessage(err)}`)
  }
}

async function selectHotbarSlot(slot) {
  const s = Math.max(0, Math.min(8, typeof slot === 'number' ? slot : 0))
  try { await bot.setQuickBarSlot(s) } catch (err) {
    return fail('select_hotbar_slot', `Could not select slot: ${errorMessage(err)}`)
  }
  return ok('select_hotbar_slot', { slot: s })
}

// ---------------------------------------------------------------------------
// Container actions
// ---------------------------------------------------------------------------

function findNearbyChest(radius) {
  if (!bot.entity) return null
  for (const name of CHEST_BLOCK_NAMES) {
    const blockDef = bot.registry.blocksByName[name]
    if (!blockDef) continue
    const found = bot.findBlock({ matching: blockDef.id, maxDistance: radius })
    if (found) return found
  }
  return null
}

function containerItems(window) {
  const end = typeof window.inventoryStart === 'number' ? window.inventoryStart : 27
  return window.slots.slice(0, end).filter(Boolean)
}

function playerItems(window) {
  const start = typeof window.inventoryStart === 'number' ? window.inventoryStart : 27
  return window.slots.slice(start).filter(Boolean)
}

async function openChest() {
  if (!bot.entity) return fail('open_chest', 'Bot not ready.')
  const block = findNearbyChest(STATION_USE_RADIUS)
  if (!block) return fail('open_chest', 'No chest found within 6 blocks.')

  let win
  try { win = await withTimeout(bot.openChest(block), CONTAINER_TIMEOUT_MS, 'opening chest') }
  catch (err) { return fail('open_chest', `Could not open chest: ${errorMessage(err)}`) }

  const items = containerItems(win).map(i => ({ name: i.name, count: i.count, slot: i.slot }))
  win.close()
  return ok('open_chest', { position: positionJson(block.position), items, item_count: items.length })
}

async function lootChest(priority) {
  if (!bot.entity) return fail('loot_chest', 'Bot not ready.')
  const p = LOOT_PRIORITIES.has(priority) ? priority : 'general'
  const wantSet = LOOT_TAKE_SETS[p]

  const block = findNearbyChest(STATION_USE_RADIUS)
  if (!block) return fail('loot_chest', 'No chest found within 6 blocks.')

  let win
  try { win = await withTimeout(bot.openChest(block), CONTAINER_TIMEOUT_MS, 'opening chest') }
  catch (err) { return fail('loot_chest', `Could not open chest: ${errorMessage(err)}`) }

  const taken = []
  for (const item of containerItems(win)) {
    if (!wantSet.has(item.name) && !FOOD_ITEM_NAMES.has(item.name)) continue
    try {
      await withTimeout(win.withdraw(item.type, null, item.count), 3000, `taking ${item.name}`)
      taken.push({ name: item.name, count: item.count })
    } catch (_) {}
  }

  win.close()
  return ok('loot_chest', { priority: p, taken, position: positionJson(block.position), inventory: inventoryJson() })
}

async function depositItems(itemNames) {
  if (!bot.entity) return fail('deposit_items', 'Bot not ready.')
  if (!Array.isArray(itemNames) || itemNames.length === 0) {
    return fail('deposit_items', 'args.items must be a non-empty array.')
  }

  const block = findNearbyChest(4)
  if (!block) return fail('deposit_items', 'No chest within 4 blocks.')

  // Reject if any requested item is in the blocked set
  const blocked = itemNames.filter(n => DEPOSIT_BLOCKED_ITEMS.has(n))
  if (blocked.length > 0) {
    return fail('deposit_items', `Refusing to deposit critical items: ${blocked.join(', ')}.`)
  }

  let win
  try { win = await withTimeout(bot.openChest(block), CONTAINER_TIMEOUT_MS, 'opening chest') }
  catch (err) { return fail('deposit_items', `Could not open chest: ${errorMessage(err)}`) }

  const deposited = []
  for (const name of itemNames) {
    const iType = itemType(name)
    if (!iType) continue
    const count = countItemInInventory(name)
    if (count === 0) continue
    try {
      await withTimeout(win.deposit(iType.id, null, count), 3000, `depositing ${name}`)
      deposited.push({ name, count })
    } catch (_) {}
  }

  win.close()
  return ok('deposit_items', { deposited, inventory: inventoryJson() })
}

async function withdrawItems(itemNames) {
  if (!bot.entity) return fail('withdraw_items', 'Bot not ready.')
  if (!Array.isArray(itemNames) || itemNames.length === 0) {
    return fail('withdraw_items', 'args.items must be a non-empty array.')
  }

  const block = findNearbyChest(4)
  if (!block) return fail('withdraw_items', 'No chest within 4 blocks.')

  let win
  try { win = await withTimeout(bot.openChest(block), CONTAINER_TIMEOUT_MS, 'opening chest') }
  catch (err) { return fail('withdraw_items', `Could not open chest: ${errorMessage(err)}`) }

  const taken = []
  for (const name of itemNames) {
    const found = containerItems(win).find(i => i.name === name)
    if (!found) continue
    try {
      await withTimeout(win.withdraw(found.type, null, found.count), 3000, `taking ${name}`)
      taken.push({ name, count: found.count })
    } catch (_) {}
  }

  win.close()
  return ok('withdraw_items', { taken, inventory: inventoryJson() })
}

// ---------------------------------------------------------------------------
// Waypoints
// ---------------------------------------------------------------------------

function markWaypoint(label, kind) {
  if (!bot.entity || !bot.game) return fail('mark_waypoint', 'Bot not ready.')
  const pos = bot.entity.position
  const wp = rememberWaypointAt(label || 'unnamed', kind, pos)
  return ok('mark_waypoint', { ...wp, stored: true })
}

function rememberWaypointAt(label, kind, pos) {
  const dimension = getBotDimension()
  const safeKind = VALID_WAYPOINT_KINDS.has(kind) ? kind : 'general'
  const wp = {
    label: String(label || 'unnamed').trim(),
    kind: safeKind,
    x: Math.floor(pos.x),
    y: Math.floor(pos.y),
    z: Math.floor(pos.z),
    dimension,
    ts: Date.now()
  }
  waypointStore.set(wp.label, wp)
  return wp
}

function listWaypoints() {
  const waypoints = Array.from(waypointStore.values())
  return ok('list_waypoints', { waypoints, count: waypoints.length })
}

async function returnToWaypoint(label) {
  if (!bot.entity) return fail('return_to_waypoint', 'Bot not ready.')
  if (!label) return fail('return_to_waypoint', 'args.label is required.')

  const wp = waypointStore.get(String(label).trim())
  if (!wp) {
    return fail('return_to_waypoint', `Waypoint '${label}' not found. Known: ${[...waypointStore.keys()].join(', ') || 'none'}.`)
  }

  const dim = getBotDimension()
  if (wp.dimension !== dim) {
    return fail('return_to_waypoint',
      `Waypoint '${label}' is in '${wp.dimension}' but bot is in '${dim}'.`,
      { suggested_next_action: wp.dimension.includes('nether') ? 'enter_nether' : 'leave_nether' })
  }

  try {
    await gotoPositionWithTimeout(new Vec3(wp.x, wp.y, wp.z), MOVEMENT_PATH_TIMEOUT_MS)
  } catch (err) {
    return fail('return_to_waypoint', `Could not reach waypoint '${label}': ${errorMessage(err)}`)
  }

  return ok('return_to_waypoint', {
    label: wp.label,
    waypoint: { x: wp.x, y: wp.y, z: wp.z, dimension: wp.dimension },
    position: positionJson(bot.entity.position)
  })
}

// return_to_position — pathfind to explicit xyz coordinates in the current dimension.
async function returnToPosition(x, y, z, dimension, radius) {
  if (!bot.entity) return fail('return_to_position', 'Bot not ready.')

  const targetDim  = String(dimension || 'overworld').replace('minecraft:', '')
  const currentDim = getBotDimension().replace('minecraft:', '')

  if (targetDim !== currentDim) {
    let suggestedNextAction = 'status'
    if (targetDim === 'the_nether') suggestedNextAction = 'enter_nether'
    else if (targetDim === 'the_end') suggestedNextAction = 'enter_end'
    else if (currentDim === 'the_nether') suggestedNextAction = 'leave_nether'
    return fail('return_to_position',
      `Cannot navigate: target is in ${targetDim} but bot is in ${currentDim}.`,
      { failure_type: 'dimension_mismatch', dimension_mismatch: true, target_dimension: targetDim, current_dimension: currentDim, suggested_next_action: suggestedNextAction }
    )
  }

  const tol    = Math.max(1, Math.min(16, radius || 3))
  const target = new Vec3(Math.round(x), Math.round(y), Math.round(z))
  const initDist = bot.entity.position.distanceTo(target)

  if (initDist <= tol) {
    return ok('return_to_position', {
      position: positionJson(bot.entity.position),
      target: { x: target.x, y: target.y, z: target.z },
      reached: true, partial: false,
      distance_on_arrival: Math.round(initDist * 10) / 10,
    })
  }

  const goal = new goals.GoalNear(target.x, target.y, target.z, tol)
  try {
    await withTimeout(bot.pathfinder.goto(goal), WORKSPACE_PATH_TIMEOUT_MS, 'pathing to return position')
  } catch (err) {
    stopMovement()
    const distNow = bot.entity ? Math.round(bot.entity.position.distanceTo(target) * 10) / 10 : null
    if (distNow !== null && distNow <= tol * 3) {
      return ok('return_to_position', {
        position: positionJson(bot.entity.position),
        target: { x: target.x, y: target.y, z: target.z },
        reached: true, partial: true,
        distance_on_arrival: distNow,
      })
    }
    return fail('return_to_position', `Could not reach position: ${errorMessage(err)}`, {
      failure_type: isPathTimeoutError(err) ? 'navigation_failed' : 'target_unreachable',
      stop_reason: isPathTimeoutError(err) ? 'path_timeout' : 'navigation_failed',
      repeatable_now: true,
      can_retry: true,
      suggested_next_action: 'recover_position',
      distance_on_fail: distNow,
    })
  }

  const distFinal = bot.entity ? Math.round(bot.entity.position.distanceTo(target) * 10) / 10 : 0
  return ok('return_to_position', {
    position: positionJson(bot.entity.position),
    target: { x: target.x, y: target.y, z: target.z },
    reached: true, partial: false,
    distance_on_arrival: distFinal,
  })
}

// set_home_position — mark current position as persistent home base.
function setHomePosition() {
  if (!bot.entity) return fail('set_home_position', 'Bot not ready.')
  const wp = rememberWaypointAt('home', 'home', bot.entity.position)
  return ok('set_home_position', { ...wp, stored: true })
}

// ---------------------------------------------------------------------------
// Death recovery
// ---------------------------------------------------------------------------

function inferRecentDamageCause() {
  if (!bot.entity) return null
  const hostile = nearestHostileEntity()
  if (hostile && bot.entity.position.distanceTo(hostile.position) <= 8) {
    return `near_${hostile.name || hostile.displayName || 'hostile'}`
  }
  if (isInNamedLiquid('lava')) return 'lava'
  if (bot.entity.position.y <= END_VOID_MIN_Y) return 'void_or_fall'
  return null
}

function respawnedRecently() {
  return Boolean(lastRespawnAt && Date.now() - lastRespawnAt <= RESPAWN_RECENT_SECONDS * 1000)
}

function deathRecoveryState() {
  if (!lastDeath) {
    return {
      known: false,
      respawned_recently: respawnedRecently(),
      failures: deathRecoveryFailures,
    }
  }

  const ageSeconds = Math.max(0, Math.floor((Date.now() - lastDeath.ts) / 1000))
  return {
    known: true,
    last_death: lastDeath,
    age_seconds: ageSeconds,
    recent: ageSeconds <= DEATH_RECENT_SECONDS,
    despawn_warning: ageSeconds >= DEATH_ITEM_DESPAWN_SECONDS - 60,
    time_remaining_s: Math.max(0, DEATH_ITEM_DESPAWN_SECONDS - ageSeconds),
    respawned_recently: respawnedRecently(),
    attempts: lastDeath.recovery_attempts || 0,
    failures: deathRecoveryFailures,
    abandoned: Boolean(lastDeath.abandoned),
    abandoned_at: deathRecoveryAbandonedAt,
    suggested_next_action: deathRecoveryFailures >= DEATH_RECOVERY_MAX_FAILURES
      ? 'abandon_death_recovery'
      : 'recover_death_items',
  }
}

function recordDeathRecoveryFailure() {
  deathRecoveryFailures++
  if (lastDeath) {
    lastDeath.recovery_failures = deathRecoveryFailures
  }
}

function markDeathRecoveryAttempt() {
  if (!lastDeath) return
  lastDeath.recovery_attempts = (lastDeath.recovery_attempts || 0) + 1
  lastDeath.recovery_failures = deathRecoveryFailures
}

function isDroppedItemEntity(entity) {
  if (!entity || !entity.position) return false
  const name = String(entity.name || entity.displayName || entity.type || '').toLowerCase()
  const objType = String(entity.objectType || '').toLowerCase()
  // Exclude XP orbs and other non-item entities
  if (name.includes('experience') || name.includes('xp_orb') || name.includes('orb')) return false
  if (entity.type === 'experience_orb' || objType === 'experience_orb') return false
  // Match dropped item entities across mineflayer/minecraft versions
  return (
    name === 'item' ||
    objType === 'item' ||
    entity.type === 'item' ||
    (name.includes('item') && !name.includes('frame') && !name.includes('display'))
  )
}

function droppedItemEntitiesNear(position, radius) {
  if (!bot.entity || !bot.entities || !position) return []
  return Object.values(bot.entities)
    .filter((entity) => {
      if (!entity || entity === bot.entity || !entity.position) return false
      return isDroppedItemEntity(entity) && entity.position.distanceTo(position) <= radius
    })
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))
}

async function recoverDeathItems() {
  if (!bot.entity) return fail('recover_death_items', 'Bot not ready.')
  if (!lastDeath) {
    return fail('recover_death_items', 'No death location recorded in this session.')
  }

  if (lastDeath.abandoned) {
    return fail('recover_death_items', 'Death recovery was abandoned for the latest death.', {
      death_state: deathRecoveryState(),
      suggested_next_action: 'return_to_spawn_or_home',
    })
  }

  if (deathRecoveryFailures >= DEATH_RECOVERY_MAX_FAILURES) {
    return fail('recover_death_items', 'Death recovery already failed twice; refusing to repeat the same lethal route.', {
      death_state: deathRecoveryState(),
      suggested_next_action: 'abandon_death_recovery',
    })
  }

  const ageMs = Date.now() - lastDeath.ts
  const ageSec = Math.floor(ageMs / 1000)
  if (ageSec > DEATH_ITEM_DESPAWN_SECONDS - 10) {
    return ok('recover_death_items', {
      not_applicable: true,
      reason: `Death items likely despawned (${ageSec}s ago; items despawn at ${DEATH_ITEM_DESPAWN_SECONDS}s).`,
      last_death: lastDeath,
      despawn_warning: true,
      suggested_next_action: 'abandon_death_recovery',
    })
  }

  markDeathRecoveryAttempt()

  const dim = getBotDimension()
  if (lastDeath.dimension !== dim) {
    recordDeathRecoveryFailure()
    return fail('recover_death_items',
      `Death was in '${lastDeath.dimension}' but bot is in '${dim}'.`,
      {
        death_state: deathRecoveryState(),
        suggested_next_action: lastDeath.dimension.includes('nether') ? 'enter_nether' : 'return_to_spawn_or_home',
      })
  }

  if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD && nearestHostileEntity()) {
    recordDeathRecoveryFailure()
    return fail('recover_death_items', `Too dangerous to recover items at health ${bot.health}.`, {
      death_state: deathRecoveryState(),
      suggested_next_action: firstInventoryItemByNames(Array.from(FOOD_ITEM_NAMES)) ? 'eat_food' : 'return_to_spawn_or_home',
    })
  }

  const beforeCounts = {}
  for (const item of inventoryJson()) { beforeCounts[item.name] = (beforeCounts[item.name] || 0) + item.count }
  const deathPos = new Vec3(lastDeath.x, lastDeath.y, lastDeath.z)

  try {
    await gotoPositionWithTimeout(deathPos, MOVEMENT_PATH_TIMEOUT_MS * 2)
  } catch (err) {
    recordDeathRecoveryFailure()
    return fail('recover_death_items', `Could not reach death location: ${errorMessage(err)}`, {
      death_state: deathRecoveryState(),
      death_location: lastDeath,
      time_remaining_s: Math.max(0, DEATH_ITEM_DESPAWN_SECONDS - ageSec),
      despawn_warning: ageSec >= DEATH_ITEM_DESPAWN_SECONDS - 60,
      suggested_next_action: deathRecoveryFailures >= DEATH_RECOVERY_MAX_FAILURES
        ? 'abandon_death_recovery'
        : 'return_to_spawn_or_home',
    })
  }

  const visibleDrops = droppedItemEntitiesNear(deathPos, DEATH_RECOVERY_PICKUP_RADIUS)
  for (const drop of visibleDrops.slice(0, 12)) {
    if (typeof bot.health === 'number' && bot.health <= LOW_HEALTH_THRESHOLD) break
    try {
      await gotoPositionWithTimeout(drop.position, 5000)
      await delay(250)
    } catch (_) {}
  }

  await delay(2500)

  const afterCounts = {}
  for (const item of inventoryJson()) { afterCounts[item.name] = (afterCounts[item.name] || 0) + item.count }

  const recovered = Object.entries(afterCounts)
    .filter(([name, count]) => count > (beforeCounts[name] || 0))
    .map(([name, count]) => ({ name, count: count - (beforeCounts[name] || 0) }))

  const success = recovered.length > 0
  if (!success) recordDeathRecoveryFailure()

  return ok('recover_death_items', {
    reached_location: true,
    recovered,
    recovered_any: success,
    visible_drops_seen: visibleDrops.length,
    death_location: lastDeath,
    age_seconds: ageSec,
    time_remaining_s: Math.max(0, DEATH_ITEM_DESPAWN_SECONDS - ageSec),
    despawn_warning: ageSec >= DEATH_ITEM_DESPAWN_SECONDS - 60,
    recovery_failures: deathRecoveryFailures,
    can_retry: !success && deathRecoveryFailures < DEATH_RECOVERY_MAX_FAILURES,
    suggested_next_action: success
      ? 'status'
      : deathRecoveryFailures >= DEATH_RECOVERY_MAX_FAILURES
        ? 'abandon_death_recovery'
        : 'recover_death_items',
    inventory: inventoryJson()
  })
}

function abandonDeathRecovery() {
  if (!lastDeath) {
    return ok('abandon_death_recovery', { abandoned: false, reason: 'No death location recorded.' })
  }
  lastDeath.abandoned = true
  deathRecoveryAbandonedAt = Date.now()
  waypointStore.delete('death_location')
  return ok('abandon_death_recovery', {
    abandoned: true,
    last_death: lastDeath,
    suggested_next_action: 'return_to_spawn_or_home',
  })
}

async function returnToSpawnOrHome() {
  if (!bot.entity) return fail('return_to_spawn_or_home', 'Bot not ready.')
  const labels = ['spawn_bed', 'home', 'surface']
  const dim = getBotDimension()

  for (const label of labels) {
    const wp = waypointStore.get(label)
    if (!wp) continue
    if (wp.dimension !== dim) {
      return fail('return_to_spawn_or_home', `Waypoint '${label}' is in '${wp.dimension}' but bot is in '${dim}'.`, {
        waypoint: wp,
        suggested_next_action: wp.dimension.includes('nether') ? 'leave_nether' : 'return_to_portal',
      })
    }
    try {
      await gotoPositionWithTimeout(new Vec3(wp.x, wp.y, wp.z), MOVEMENT_PATH_TIMEOUT_MS)
      return ok('return_to_spawn_or_home', {
        destination: label,
        waypoint: wp,
        position: positionJson(bot.entity.position),
      })
    } catch (err) {
      return fail('return_to_spawn_or_home', `Could not reach '${label}': ${errorMessage(err)}`, {
        waypoint: wp,
        suggested_next_action: 'find_safe_workspace',
      })
    }
  }

  const spawn = bot.spawnPoint
  if (spawn && typeof spawn.x === 'number' && typeof spawn.y === 'number' && typeof spawn.z === 'number') {
    try {
      await gotoPositionWithTimeout(new Vec3(spawn.x, spawn.y, spawn.z), MOVEMENT_PATH_TIMEOUT_MS)
      return ok('return_to_spawn_or_home', {
        destination: 'world_spawn',
        position: positionJson(bot.entity.position),
      })
    } catch (err) {
      return fail('return_to_spawn_or_home', `Could not reach world spawn: ${errorMessage(err)}`, {
        suggested_next_action: 'find_safe_workspace',
      })
    }
  }

  return fail('return_to_spawn_or_home', 'No spawn_bed, home, surface, or spawn point is known.', {
    suggested_next_action: 'find_safe_workspace',
  })
}

async function collectWood(requestedCount) {
  const targetCount = requestedCount === undefined ? COLLECT_WOOD_DEFAULT_COUNT : requestedCount
  return await acquireBlocksForAction('collect_wood', {
    targets: Array.from(WOOD_BLOCK_NAMES),
    count: targetCount,
    radius: COLLECT_WOOD_RADIUS,
    allowExcavate: false,
    accessMode: 'surface_first'
  })
}

async function acquireBlocksAction(args) {
  return await acquireBlocksForAction('acquire_blocks', normalizeAcquireBlockArgs(args))
}

async function navigateToBlockType(args) {
  const targets = args.targets.filter((target) => ACQUIRE_ALLOWED_TARGETS.has(target))
  const targetSet = new Set(targets)
  const radius = args.radius === undefined ? ACQUIRE_BLOCKS_DEFAULT_RADIUS : args.radius
  const diagnostics = emptyAcquireResult({ targets, count: 0 }, 'failed')

  if (targets.length === 0) {
    return fail('navigate_to_block_type', 'No allowed navigation targets were provided.')
  }

  const candidate = await findSurfaceNavigationCandidate(targetSet, radius, diagnostics)
  if (!candidate) {
    return {
      ok: false,
      action: 'navigate_to_block_type',
      result: {
        targets,
        radius,
        ...navigationDiagnostics(diagnostics)
      },
      error: 'No accessible target block found. Try explore_nearby or choose a different target.'
    }
  }

  try {
    await approachTarget(candidate.block, candidate.standPosition)
  } catch (error) {
    diagnostics.rejectedUnreachable += 1
    stopMovement()
    return fail('navigate_to_block_type', `Navigation path failed: ${errorMessage(error)}`, {
      failure_type: isPathTimeoutError(error) ? 'navigation_failed' : 'target_unreachable',
      stop_reason: isPathTimeoutError(error) ? 'path_timeout' : 'navigation_failed',
      repeatable_now: true,
      targets,
      radius,
      target: blockJson(candidate.block),
      standPosition: positionJson(candidate.standPosition),
      ...navigationDiagnostics(diagnostics)
    })
  }

  return ok('navigate_to_block_type', {
    targets,
    radius,
    target: blockJson(candidate.block),
    standPosition: positionJson(candidate.standPosition),
    strategy: bot.entity.position.distanceTo(candidate.standPosition) <= 2.5 ? 'immediate_surface' : 'moved_to_surface',
    ...navigationDiagnostics(diagnostics)
  })
}

function normalizeAcquireBlockArgs(args) {
  return {
    targets: args.targets,
    count: args.count === undefined ? ACQUIRE_BLOCKS_DEFAULT_COUNT : args.count,
    radius: args.radius === undefined ? ACQUIRE_BLOCKS_DEFAULT_RADIUS : args.radius,
    allowExcavate: args.allowExcavate === undefined ? false : args.allowExcavate,
    accessMode: args.accessMode === undefined ? 'surface_first' : args.accessMode
  }
}

function navigationDiagnostics(diagnostics) {
  return {
    targetCandidatesFound: diagnostics.targetCandidatesFound,
    targetCandidatesFoundRaw: diagnostics.targetCandidatesFoundRaw || diagnostics.targetCandidatesFound,
    exposedCandidatesFound: diagnostics.exposedCandidatesFound,
    accessCandidatesFound: diagnostics.accessCandidatesFound,
    candidates_seen: diagnostics.candidates_seen || diagnostics.targetCandidatesFound,
    candidates_evaluated: diagnostics.candidates_evaluated || 0,
    candidatesEvaluated: diagnostics.candidatesEvaluated || 0,
    scan_limited: Boolean(diagnostics.scan_limited),
    rejectedDangerous: diagnostics.rejectedDangerous,
    rejectedProtected: diagnostics.rejectedProtected,
    rejectedUnsupported: diagnostics.rejectedUnsupported,
    rejectedNoSafeStand: diagnostics.rejectedNoSafeStand,
    rejectedUnreachable: diagnostics.rejectedUnreachable
  }
}

async function acquireBlocksForAction(actionName, options) {
  const sharedDiagnostics = emptyAcquireResult(options, 'failed')
  const startPosition = bot.entity ? positionJson(bot.entity.position) : null
  const startInventoryCounts = inventoryCounts()
  const targets = (options.targets || []).filter((t) => ACQUIRE_ALLOWED_TARGETS.has(t))

  try {
    return await withTimeout(acquireBlocksCore(actionName, options, sharedDiagnostics), ACQUIRE_BLOCKS_TIMEOUT_MS, actionName)
  } catch (error) {
    stopMovement()

    const endPosition = bot.entity ? positionJson(bot.entity.position) : null
    const endInventoryCounts = inventoryCounts()
    const timeoutMs = ACQUIRE_BLOCKS_TIMEOUT_MS

    // Compute distance moved
    let distanceMoved = 0
    if (startPosition && endPosition) {
      const dx = endPosition.x - startPosition.x
      const dy = endPosition.y - startPosition.y
      const dz = endPosition.z - startPosition.z
      distanceMoved = Math.sqrt(dx * dx + dy * dy + dz * dz)
    }

    // Compute inventory delta (targets only)
    const inventoryDeltaAtTimeout = {}
    for (const target of targets) {
      const before = startInventoryCounts[target] || 0
      const after = endInventoryCounts[target] || 0
      if (after !== before) inventoryDeltaAtTimeout[target] = after - before
    }
    const hasInventoryGain = Object.values(inventoryDeltaAtTimeout).some((v) => v > 0)

    // Update nearest target distance end
    if (sharedDiagnostics.nearestTargetDistance !== null) {
      sharedDiagnostics.nearestTargetDistanceEnd = sharedDiagnostics.nearestTargetDistance
    }

    // Classify progress signals
    const progressSignals = []
    if (sharedDiagnostics.excavatedBlocks > 0) progressSignals.push(`excavated_blocks:${sharedDiagnostics.excavatedBlocks}`)
    if (sharedDiagnostics.minedTargetBlocks > 0) progressSignals.push(`mined_target_blocks:${sharedDiagnostics.minedTargetBlocks}`)
    if (distanceMoved >= 1.0) progressSignals.push(`distance_moved:${Math.round(distanceMoved * 10) / 10}`)
    if (hasInventoryGain) progressSignals.push('inventory_gain')

    const isPartialProgress = progressSignals.length > 0

    sharedDiagnostics.failure_type = isPartialProgress ? 'partial_progress_timeout' : 'action_timeout'
    sharedDiagnostics.repeatable_now = true
    sharedDiagnostics.can_retry = true
    sharedDiagnostics.suggested_next_action = 'acquire_blocks'
    sharedDiagnostics.stop_reason = sharedDiagnostics.failure_type
    sharedDiagnostics.inventory = inventoryJson()
    updateResourceInventoryDiagnostics(sharedDiagnostics, targets, startInventoryCounts, options.count)
    sharedDiagnostics.partial_success = sharedDiagnostics.collected > 0 || isPartialProgress

    if (isPartialProgress) {
      sharedDiagnostics.failed_because = [{
        kind: 'partial_progress_timeout',
        action: actionName,
        timeout_ms: timeoutMs,
        progress_signals: progressSignals,
        excavated_blocks: sharedDiagnostics.excavatedBlocks,
        mined_target_blocks: sharedDiagnostics.minedTargetBlocks,
        distance_moved: Math.round(distanceMoved * 10) / 10,
        inventory_delta: inventoryDeltaAtTimeout,
        last_substep: sharedDiagnostics.currentSubstep,
        nearestRawTargetDistance: sharedDiagnostics.nearestRawTargetDistance,
        selectedTargetDistance: sharedDiagnostics.selectedTargetDistance,
        last_target_position: sharedDiagnostics.last_target_position,
        continuation_relevant: true
      }]
    } else {
      sharedDiagnostics.failed_because = [{
        kind: 'action_timeout',
        action: actionName,
        timeout_ms: timeoutMs,
        last_substep: sharedDiagnostics.currentSubstep,
        nearestRawTargetDistance: sharedDiagnostics.nearestRawTargetDistance,
        nearestRawTargetPosition: sharedDiagnostics.nearestRawTargetPosition,
        selectedTargetDistance: sharedDiagnostics.selectedTargetDistance,
        selectedTargetPosition: sharedDiagnostics.selectedTargetPosition
      }]
    }

    const successResponse = resourceSuccessFromInventory(actionName, sharedDiagnostics, 'action_timeout_inventory_delta')
    if (successResponse) return successResponse

    return {
      ok: false,
      action: actionName,
      result: sharedDiagnostics,
      error: `Block acquisition failed: ${errorMessage(error)}`
    }
  }
}

function buildProgressSignals(diagnostics, startInventorySnapshot, startPositionSnapshot, targets) {
  const signals = {}
  let hasProgress = false

  if (diagnostics.excavatedBlocks > 0) {
    signals.excavatedBlocks = diagnostics.excavatedBlocks
    hasProgress = true
  }
  if (diagnostics.minedTargetBlocks > 0) {
    signals.minedTargetBlocks = diagnostics.minedTargetBlocks
    hasProgress = true
  }

  // Inventory delta for target items only
  const endInventory = inventoryCounts()
  const inventoryDelta = {}
  for (const target of targets) {
    const before = startInventorySnapshot[target] || 0
    const after = endInventory[target] || 0
    if (after !== before) inventoryDelta[target] = after - before
  }
  // Also track non-target deltas (dirt, stone excavated, etc.)
  for (const [item, afterVal] of Object.entries(endInventory)) {
    const beforeVal = startInventorySnapshot[item] || 0
    if (afterVal !== beforeVal && !(item in inventoryDelta)) {
      inventoryDelta[item] = afterVal - beforeVal
    }
  }
  for (const [item, before] of Object.entries(startInventorySnapshot)) {
    const after = endInventory[item] || 0
    if (after !== before && !(item in inventoryDelta)) {
      inventoryDelta[item] = after - before
    }
  }
  if (Object.keys(inventoryDelta).length > 0) {
    signals.inventory_delta = inventoryDelta
    hasProgress = true
  }

  if (
    diagnostics.nearestTargetDistance !== null &&
    diagnostics.nearestTargetDistanceEnd !== null &&
    diagnostics.nearestTargetDistanceEnd < diagnostics.nearestTargetDistance
  ) {
    signals.nearestTargetDistance = diagnostics.nearestTargetDistance
    signals.nearestTargetDistanceEnd = diagnostics.nearestTargetDistanceEnd
    hasProgress = true
  }

  if (diagnostics.accessCandidatesFound > 0 && diagnostics.pathAttempts > 0) {
    signals.accessCandidatesFound = diagnostics.accessCandidatesFound
    signals.pathAttempts = diagnostics.pathAttempts
    hasProgress = true
  }

  // Distance moved from start
  if (startPositionSnapshot && bot.entity) {
    const cur = bot.entity.position
    const dx = cur.x - startPositionSnapshot.x
    const dy = cur.y - startPositionSnapshot.y
    const dz = cur.z - startPositionSnapshot.z
    const distMoved = Math.sqrt(dx * dx + dy * dy + dz * dz)
    if (distMoved >= 1.0) {
      signals.distance_moved = Math.round(distMoved * 10) / 10
      hasProgress = true
    }
  }

  if (diagnostics.nearestTargetDistance !== null && diagnostics.nearestTargetDistanceEnd !== null) {
    const delta = diagnostics.nearestTargetDistanceEnd - diagnostics.nearestTargetDistance
    signals.distance_to_target_delta = Math.round(delta * 10) / 10
  }

  return { hasProgress, signals }
}

async function acquireBlocksCore(actionName, options, externalDiagnostics) {
  const targets = options.targets.filter((target) => ACQUIRE_ALLOWED_TARGETS.has(target))
  const targetSet = new Set(targets)
  const requested = Math.max(1, Math.min(options.count, ACQUIRE_BLOCKS_MAX_COUNT))
  const radius = Math.max(ACQUIRE_BLOCKS_MIN_RADIUS, Math.min(options.radius, ACQUIRE_BLOCKS_MAX_RADIUS, MAX_SCAN_RADIUS))
  const allowExcavate = options.allowExcavate === true
  const accessMode = ACQUIRE_ACCESS_MODES.has(options.accessMode) ? options.accessMode : 'surface_first'
  const diagnostics = externalDiagnostics || emptyAcquireResult({ targets, count: requested }, 'failed')
  // Sync requested/targets in case externalDiagnostics was created with defaults
  diagnostics.requested = requested
  diagnostics.targets = targets
  diagnostics.radius = radius
  const startingCount = inventoryCountForTargets(targets)
  const startInventorySnapshot = inventoryCounts()
  diagnostics.inventoryBefore = startInventorySnapshot
  const startPositionSnapshot = bot.entity ? positionJson(bot.entity.position) : null
  const targetInventoryCount = startingCount + requested
  const targetLabel = targets.length === 1 ? targets[0] : 'target block'
  const ignoredPositions = new Set()
  let attempts = 0
  let staircaseSteps = 0
  let lastError = null
  let pathTimeoutCount = 0  // consecutive path timeouts with no progress; reset on successful mine

  // Reuse last known target if still valid (avoids full rescan on continuation)
  let cachedCandidate = null
  const cachedEntry = _lastAcquireTargetByAction.get(actionName)
  if (cachedEntry && Date.now() - cachedEntry.timestamp < ACQUIRE_TARGET_CACHE_TTL_MS) {
    const freshBlock = bot.blockAt(cachedEntry.blockPosition)
    if (freshBlock && isTargetBlock(freshBlock, targetSet) && !ignoredPositions.has(positionKey(freshBlock.position))) {
      diagnostics.lastTargetStillExists = true
      const cacheDist = bot.entity ? Math.round(bot.entity.position.distanceTo(freshBlock.position) * 10) / 10 : null
      diagnostics.distanceToLastTarget = cacheDist
      // Seed nearestTargetDistance from cache so close-range check can fire before a full scan
      if (cacheDist !== null && diagnostics.nearestTargetDistance === null) {
        diagnostics.nearestTargetDistance = cacheDist
        diagnostics.nearestTargetPosition = positionJson(freshBlock.position)
        diagnostics.nearestRawTargetDistance = cacheDist
        diagnostics.nearestRawTargetPosition = positionJson(freshBlock.position)
      }
      const faceInfo = findExposedFace(freshBlock)
      const standPosition = faceInfo ? findSafeStandNearFace(freshBlock, faceInfo) : null
      // Cached block may be close-range-accessible even without an exposed face
      cachedCandidate = {
        block: freshBlock,
        faceInfo: faceInfo || null,
        standPosition: standPosition || null,
        fromCache: true
      }
      diagnostics.reusedLastTarget = true
    }
  }

  if (targets.length === 0) {
    diagnostics.stop_reason = 'no_targets_found'
    diagnostics.suggested_next_action = 'explore_nearby'
    diagnostics.inventory = inventoryJson()
    return {
      ok: false,
      action: actionName,
      result: diagnostics,
      error: 'No allowed acquisition targets were provided.'
    }
  }

  if (typeof bot.health === 'number' && bot.health <= MINE_STONE_MIN_HEALTH) {
    diagnostics.stop_reason = 'low_health'
    diagnostics.suggested_next_action = 'status'
    diagnostics.inventory = inventoryJson()
    return {
      ok: false,
      action: actionName,
      result: diagnostics,
      error: `Health too low for block acquisition: ${bot.health}.`
    }
  }

  const floorDrops = bot.entity ? droppedItemEntitiesNear(bot.entity.position, Math.min(radius, DROP_COLLECTION_RADIUS)) : []
  if (floorDrops.length > 0) {
    diagnostics.currentSubstep = 'collect_floor_drop_before_mining'
    diagnostics.floorDropCollectionAttempted = true
    const floorDropResult = await collectNearbyDrops({
      aroundPosition: bot.entity.position,
      targets,
      radius: Math.min(radius, DROP_COLLECTION_RADIUS),
      timeoutMs: Math.min(4000, DROP_COLLECTION_TIMEOUT_MS)
    }, diagnostics)
    diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
    diagnostics.inventory = inventoryJson()
    if (floorDropResult.collected > 0 || diagnostics.collected >= requested) {
      diagnostics.currentSubstep = 'floor_drop_collected'
      return ok(actionName, diagnostics)
    }
  }

  while (inventoryCountForTargets(targets) < targetInventoryCount && attempts < ACQUIRE_MAX_ATTEMPTS) {
    if (typeof bot.health === 'number' && bot.health <= MINE_STONE_MIN_HEALTH) {
      lastError = `Health too low for block acquisition: ${bot.health}.`
      break
    }

    await yieldToEventLoop()

    // Scan for candidates first — this sets nearestTargetDistance in diagnostics.
    // For cache hits, nearestTargetDistance is already seeded so we skip the expensive scan.
    let candidate
    if (cachedCandidate) {
      candidate = cachedCandidate.standPosition ? cachedCandidate : null
      cachedCandidate = null
    } else {
      diagnostics.currentSubstep = 'scan'
      candidate = await findSurfaceAcquisitionCandidate(targetSet, radius, ignoredPositions, diagnostics)
    }

    // After the scan, nearestTargetDistance is now reliably set.
    // If the nearest raw target is within close range, intercept before using any far candidate.
    const nearestRawDist = diagnostics.nearestTargetDistance
    const isCloseRange = nearestRawDist !== null && nearestRawDist <= RESOURCE_CLOSE_RANGE_BLOCKS

    if (isCloseRange && diagnostics.nearestTargetPosition) {
      const np = diagnostics.nearestTargetPosition
      const nearBlock = bot.blockAt(new Vec3(np.x, np.y, np.z))
      if (nearBlock && isTargetBlock(nearBlock, targetSet) && !ignoredPositions.has(positionKey(nearBlock.position))) {
        attempts++
        ignoredPositions.add(positionKey(nearBlock.position))

        diagnostics.selectedTargetMode = 'close_raw_target'
        diagnostics.selectedTargetDistance = nearestRawDist
        diagnostics.selectedTargetPosition = positionJson(nearBlock.position)
        diagnostics.selectedCloseRangeTargetPosition = positionJson(nearBlock.position)
        diagnostics.last_target_position = positionJson(nearBlock.position)
        // Record the access candidate distance separately even though we're not using it
        if (candidate && bot.entity) {
          diagnostics.selectedAccessTargetDistance = Math.round(bot.entity.position.distanceTo(candidate.block.position) * 10) / 10
        }

        _lastAcquireTargetByAction.set(actionName, {
          blockPosition: nearBlock.position.clone(),
          timestamp: Date.now()
        })

        diagnostics.currentSubstep = 'close_range_access'
        const localExcavationBeforeFallback = diagnostics.localExcavationSteps
        const fallbackResult = await closeRangeAccessFallback(nearBlock, targetSet, diagnostics)

        if (fallbackResult.ok && fallbackResult.mined) {
          diagnostics.minedTargetBlocks += 1
          diagnostics.currentSubstep = 'collect_drop'
          const dropResult = await collectNearbyDrops(
            { aroundPosition: nearBlock.position, targets, radius: 6 },
            diagnostics
          )
          diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
          diagnostics.inventory = inventoryJson()
          if (dropResult.collected > 0) {
            diagnostics.currentSubstep = 'close_range_done'
            if (diagnostics.collected >= requested) return ok(actionName, diagnostics)
            continue
          }
          return buildDropCollectionFailure(dropResult.reason, actionName, targetLabel, nearestRawDist, diagnostics)
        }

        if (fallbackResult.ok && fallbackResult.moved) {
          let minedAfterMove = false
          try {
            const freshNear = bot.blockAt(nearBlock.position)
            if (freshNear && isTargetBlock(freshNear, targetSet)) {
              diagnostics.digAttempts += 1
              diagnostics.currentSubstep = 'dig_target'
              await mineBlockSafe(freshNear, targetSet)
              diagnostics.minedTargetBlocks += 1
              minedAfterMove = true
            }
          } catch (error) {
            lastError = errorMessage(error)
            stopMovement()
          }
          if (minedAfterMove) {
            diagnostics.currentSubstep = 'collect_drop'
            const dropResult = await collectNearbyDrops(
              { aroundPosition: nearBlock.position, targets, radius: 6 },
              diagnostics
            )
            diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
            diagnostics.inventory = inventoryJson()
            if (dropResult.collected > 0) {
              diagnostics.currentSubstep = 'close_range_done'
              if (diagnostics.collected >= requested) return ok(actionName, diagnostics)
              continue
            }
            return buildDropCollectionFailure(dropResult.reason, actionName, targetLabel, nearestRawDist, diagnostics)
          }
          continue
        }

        const closeRangeExcavatedThisAttempt = diagnostics.localExcavationSteps > localExcavationBeforeFallback
        if (closeRangeExcavatedThisAttempt && diagnostics.localExcavationSteps < LOCAL_EXCAVATION_STEP_LIMIT) {
          ignoredPositions.delete(positionKey(nearBlock.position))
          diagnostics.currentSubstep = 'close_range_access_retry_after_excavation'
          diagnostics.closeRangeFailureReason = 'local_excavation_opened_access_retrying_target'
          await yieldToEventLoop()
          continue
        }

        // Close-range fallback failed: check for progress
        const crSignals = buildProgressSignals(diagnostics, startInventorySnapshot, startPositionSnapshot, targets)
        if (crSignals.hasProgress && closeRangeExcavatedThisAttempt) {
          // Made progress (excavation, movement) → return partial; don't try the far candidate
          diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
          diagnostics.inventory = inventoryJson()
          diagnostics.can_retry = true
          diagnostics.repeatable_now = true
          diagnostics.failure_type = 'partial_progress_timeout'
          diagnostics.stop_reason = 'close_range_access_timeout'
          diagnostics.partial_success = true
          diagnostics.continuation_relevant = true
          diagnostics.progress_made = true
          diagnostics.failed_because = [{
            kind: 'close_range_access_timeout',
            action: actionName,
            stop_reason: 'close_range_access_timeout',
            progress_signals: crSignals.signals,
            continuation_relevant: true,
            nearestRawTargetDistance: nearestRawDist,
            selectedTargetDistance: nearestRawDist,
            selectedAccessTargetDistance: diagnostics.selectedAccessTargetDistance,
            localFallbackAttempted: true,
            localExcavationSteps: diagnostics.localExcavationSteps,
            closeRangeFailureReason: diagnostics.closeRangeFailureReason || 'local_access_exhausted'
          }]
          return {
            ok: false,
            action: actionName,
            result: diagnostics,
            error: `Close-range access partial progress for ${targetLabel}`
          }
        }

        // Zero progress from close-range: fall through to pathfind to the access candidate.
        // nearBlock is now in ignoredPositions so it won't be retried as a close-range target.
        diagnostics.selectedTargetMode = 'access_candidate'
      }
    }

    // Normal access candidate path (also runs after zero-progress close-range fallback)
    if (candidate) {
      attempts++

      const selectedDist = bot.entity ? Math.round(bot.entity.position.distanceTo(candidate.block.position) * 10) / 10 : null
      diagnostics.last_target_position = positionJson(candidate.block.position)
      diagnostics.last_stand_position = positionJson(candidate.standPosition)
      diagnostics.selectedTargetDistance = selectedDist
      diagnostics.selectedTargetPosition = positionJson(candidate.block.position)
      if (!diagnostics.selectedTargetMode) diagnostics.selectedTargetMode = 'access_candidate'
      diagnostics.selectedAccessTargetDistance = selectedDist
      diagnostics.selectedAccessTargetPosition = positionJson(candidate.block.position)

      // Safety: if the scan found a close raw target that step 2 missed (e.g. cached candidate
      // path skipped the scan, or the block was at the threshold boundary), redirect before
      // the expensive pathfind. Uses the already-computed nearestRawTargetDistance — no re-scan.
      // The far candidate is NOT added to ignoredPositions so the next iteration can still use it.
      if (
        diagnostics.closeRangeFallbackAttempted === 0 &&
        bot.entity &&
        diagnostics.nearestRawTargetDistance !== null &&
        diagnostics.nearestRawTargetDistance <= RESOURCE_CLOSE_RANGE_BLOCKS
      ) {
        const np = diagnostics.nearestRawTargetPosition
        const closeBlock = np ? bot.blockAt(new Vec3(np.x, np.y, np.z)) : null
        if (closeBlock && isTargetBlock(closeBlock, targetSet) && !ignoredPositions.has(positionKey(closeBlock.position))) {
          // Next iteration fires close-range via step 2; candidate stays available
          continue
        }
      }

      // Commit: add candidate to ignoredPositions so it won't be re-selected
      ignoredPositions.add(positionKey(candidate.block.position))

      // Cache the selected target for next invocation
      _lastAcquireTargetByAction.set(actionName, {
        blockPosition: candidate.block.position.clone(),
        timestamp: Date.now()
      })

      if (selectedDist !== null && selectedDist <= RESOURCE_CLOSE_RANGE_BLOCKS) {
        diagnostics.currentSubstep = 'close_range_access_for_selected_candidate'
        const localExcavationBeforeFallback = diagnostics.localExcavationSteps
        const fallbackResult = await closeRangeAccessFallback(candidate.block, targetSet, diagnostics)

        if (fallbackResult.ok && fallbackResult.mined) {
          diagnostics.minedTargetBlocks += 1
          diagnostics.currentSubstep = 'collect_drop'
          const dropResult = await collectNearbyDrops(
            { aroundPosition: candidate.block.position, targets, radius: 6 },
            diagnostics
          )
          diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
          diagnostics.inventory = inventoryJson()
          if (dropResult.collected > 0) {
            diagnostics.currentSubstep = 'close_range_done'
            if (diagnostics.collected >= requested) return ok(actionName, diagnostics)
            continue
          }
          return buildDropCollectionFailure(dropResult.reason, actionName, targetLabel, selectedDist, diagnostics)
        }

        if (fallbackResult.ok && fallbackResult.moved) {
          let minedAfterMove = false
          try {
            const freshNear = bot.blockAt(candidate.block.position)
            if (freshNear && isTargetBlock(freshNear, targetSet)) {
              diagnostics.digAttempts += 1
              diagnostics.currentSubstep = 'dig_target_after_close_selected_local_move'
              await mineBlockSafe(freshNear, targetSet)
              diagnostics.minedTargetBlocks += 1
              minedAfterMove = true
            }
          } catch (digError) {
            lastError = errorMessage(digError)
            stopMovement()
          }

          if (minedAfterMove) {
            diagnostics.currentSubstep = 'collect_drop'
            const dropResult = await collectNearbyDrops(
              { aroundPosition: candidate.block.position, targets, radius: 6 },
              diagnostics
            )
            diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
            diagnostics.inventory = inventoryJson()
            if (dropResult.collected > 0) {
              diagnostics.currentSubstep = 'close_range_done'
              if (diagnostics.collected >= requested) return ok(actionName, diagnostics)
              continue
            }
            return buildDropCollectionFailure(dropResult.reason, actionName, targetLabel, selectedDist, diagnostics)
          }
        }

        const closeRangeExcavatedThisAttempt = diagnostics.localExcavationSteps > localExcavationBeforeFallback
        if (closeRangeExcavatedThisAttempt && diagnostics.localExcavationSteps < LOCAL_EXCAVATION_STEP_LIMIT) {
          ignoredPositions.delete(positionKey(candidate.block.position))
          diagnostics.currentSubstep = 'close_range_access_retry_after_selected_excavation'
          diagnostics.closeRangeFailureReason = 'local_excavation_opened_access_retrying_target'
          await yieldToEventLoop()
          continue
        }

        const crSignals = buildProgressSignals(diagnostics, startInventorySnapshot, startPositionSnapshot, targets)
        if (crSignals.hasProgress && closeRangeExcavatedThisAttempt) {
          diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
          diagnostics.inventory = inventoryJson()
          diagnostics.can_retry = true
          diagnostics.repeatable_now = true
          diagnostics.failure_type = 'partial_progress_timeout'
          diagnostics.stop_reason = 'close_range_access_timeout'
          diagnostics.partial_success = true
          diagnostics.continuation_relevant = true
          diagnostics.progress_made = true
          diagnostics.failed_because = [{
            kind: 'close_range_access_timeout',
            action: actionName,
            stop_reason: 'close_range_access_timeout',
            progress_signals: crSignals.signals,
            continuation_relevant: true,
            nearestRawTargetDistance: diagnostics.nearestRawTargetDistance,
            nearestRawTargetPosition: diagnostics.nearestRawTargetPosition,
            selectedTargetDistance: selectedDist,
            selectedTargetPosition: diagnostics.selectedTargetPosition,
            selectedAccessTargetDistance: diagnostics.selectedAccessTargetDistance,
            selectedAccessTargetPosition: diagnostics.selectedAccessTargetPosition,
            localFallbackAttempted: true,
            localExcavationSteps: diagnostics.localExcavationSteps,
            closeRangeFailureReason: diagnostics.closeRangeFailureReason || 'local_access_exhausted'
          }]
          return {
            ok: diagnostics.collected > 0,
            action: actionName,
            result: diagnostics,
            error: diagnostics.collected > 0 ? null : `Close-range access partial progress for ${targetLabel}`
          }
        }

        diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
        diagnostics.inventory = inventoryJson()
        diagnostics.can_retry = true
        diagnostics.repeatable_now = true
        diagnostics.failure_type = 'target_unreachable'
        diagnostics.stop_reason = 'close_range_access_failed'
        diagnostics.partial_success = diagnostics.collected > 0
        diagnostics.failed_because = [{
          kind: 'close_range_access_failed',
          action: actionName,
          stop_reason: 'close_range_access_failed',
          selectedTargetDistance: selectedDist,
          selectedTargetPosition: diagnostics.selectedTargetPosition,
          selectedAccessTargetDistance: diagnostics.selectedAccessTargetDistance,
          selectedAccessTargetPosition: diagnostics.selectedAccessTargetPosition,
          nearestRawTargetDistance: diagnostics.nearestRawTargetDistance,
          nearestRawTargetPosition: diagnostics.nearestRawTargetPosition,
          localFallbackAttempted: true,
          localExcavationSteps: diagnostics.localExcavationSteps,
          closeRangeFailureReason: diagnostics.closeRangeFailureReason || 'local_access_failed'
        }]
        return {
          ok: diagnostics.collected > 0,
          action: actionName,
          result: diagnostics,
          error: diagnostics.collected > 0 ? null : `Close-range access failed for ${targetLabel}`
        }
      }

      // Skip pathfinding for ore whose stand position is significantly below the bot —
      // that means it's in an underground cave not yet connected to the bot's location.
      // Immediately pivot to staircase excavation instead of burning the full path timeout.
      const botY = bot.entity ? bot.entity.position.y : candidate.standPosition.y
      const standBelowThreshold = candidate.standPosition.y < botY - 8
      if (
        standBelowThreshold &&
        allowExcavate &&
        accessMode === 'safe_staircase' &&
        diagnostics.excavatedBlocks < ACQUIRE_MAX_EXCAVATED_BLOCKS &&
        staircaseSteps < Math.min(ACQUIRE_MAX_STEPS, MAX_EXCAVATION_STEPS)
      ) {
        ignoredPositions.delete(positionKey(candidate.block.position))
        diagnostics.currentSubstep = 'staircase_preempt_deep_candidate'
        diagnostics.strategy = 'safe_staircase'
        const staircaseTarget = await findNearestExcavationTarget(targetSet, radius, ignoredPositions, diagnostics)
        if (staircaseTarget) {
          const moved = await safeStaircaseStep(staircaseTarget, targetSet, diagnostics)
          if (moved) {
            attempts++
            staircaseSteps++
            continue
          }
        }
        // Staircase couldn't advance — fall through to normal pathfinding attempt
      }

      try {
        diagnostics.strategy = bot.entity.position.distanceTo(candidate.standPosition) <= 2.5
          ? 'immediate_surface'
          : 'moved_to_surface'
        diagnostics.pathAttempts += 1
        diagnostics.currentSubstep = 'path_to_access'
        await approachTarget(candidate.block, candidate.standPosition)
      } catch (error) {
        lastError = errorMessage(error)
        diagnostics.rejectedUnreachable += 1
        stopMovement()
        diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
        diagnostics.inventory = inventoryJson()
        diagnostics.can_retry = true
        diagnostics.repeatable_now = true

        const isPlanTimeout = isPlanningTimeoutError(error)
        const isPathTimeout = isPathTimeoutError(error)
        const errMsg = errorMessage(error)

        if (isPlanTimeout || isPathTimeout) diagnostics.pathPlannerError = errMsg

        const rawStopReason = isPlanTimeout
          ? 'path_planning_timeout'
          : isPathTimeout ? 'path_timeout_before_target' : 'navigation_failed'
        const rawFailureType = (isPathTimeout || isPlanTimeout) ? 'navigation_failed' : 'target_unreachable'

        if (
          (isPathTimeout || isPlanTimeout) &&
          selectedDist !== null &&
          selectedDist <= RESOURCE_CLOSE_RANGE_BLOCKS
        ) {
          diagnostics.currentSubstep = 'close_range_access_after_path_timeout'
          const localExcavationBeforeFallback = diagnostics.localExcavationSteps
          const fallbackResult = await closeRangeAccessFallback(candidate.block, targetSet, diagnostics)

          if (fallbackResult.ok && fallbackResult.mined) {
            diagnostics.minedTargetBlocks += 1
            diagnostics.currentSubstep = 'collect_drop'
            const dropResult = await collectNearbyDrops(
              { aroundPosition: candidate.block.position, targets, radius: 6 },
              diagnostics
            )
            diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
            diagnostics.inventory = inventoryJson()
            if (dropResult.collected > 0) {
              diagnostics.currentSubstep = 'close_range_done_after_path_timeout'
              if (diagnostics.collected >= requested) return ok(actionName, diagnostics)
              continue
            }
            return buildDropCollectionFailure(dropResult.reason, actionName, targetLabel, nearestRawDist, diagnostics)
          }

          if (fallbackResult.ok && fallbackResult.moved) {
            let minedAfterMove = false
            try {
              const freshNear = bot.blockAt(candidate.block.position)
              if (freshNear && isTargetBlock(freshNear, targetSet)) {
                diagnostics.digAttempts += 1
                diagnostics.currentSubstep = 'dig_target_after_local_path_timeout_recovery'
                await mineBlockSafe(freshNear, targetSet)
                diagnostics.minedTargetBlocks += 1
                minedAfterMove = true
              }
            } catch (digError) {
              lastError = errorMessage(digError)
              stopMovement()
            }

            if (minedAfterMove) {
              diagnostics.currentSubstep = 'collect_drop'
              const dropResult = await collectNearbyDrops(
                { aroundPosition: candidate.block.position, targets, radius: 6 },
                diagnostics
              )
              diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
              diagnostics.inventory = inventoryJson()
              if (dropResult.collected > 0) {
                diagnostics.currentSubstep = 'close_range_done_after_path_timeout'
                if (diagnostics.collected >= requested) return ok(actionName, diagnostics)
                continue
              }
              return buildDropCollectionFailure(dropResult.reason, actionName, targetLabel, nearestRawDist, diagnostics)
            }
          }

          const closeRangeExcavatedThisAttempt = diagnostics.localExcavationSteps > localExcavationBeforeFallback
          if (closeRangeExcavatedThisAttempt && diagnostics.localExcavationSteps < LOCAL_EXCAVATION_STEP_LIMIT) {
            ignoredPositions.delete(positionKey(candidate.block.position))
            diagnostics.currentSubstep = 'close_range_access_retry_after_path_timeout_excavation'
            diagnostics.closeRangeFailureReason = 'local_excavation_opened_access_retrying_target'
            await yieldToEventLoop()
            continue
          }
        }

        if (isPathTimeout || isPlanTimeout) {
          const progressSignals = buildProgressSignals(diagnostics, startInventorySnapshot, startPositionSnapshot, targets)
          // In path-timeout context, movement alone is NOT meaningful progress — the bot
          // walked toward an unreachable block. Only inventory change counts.
          const hadItemProgress = diagnostics.collected > 0

          if (hadItemProgress) {
            // Genuinely collected something earlier this action, then got stuck pathfinding.
            diagnostics.failure_type = 'partial_progress_timeout'
            diagnostics.stop_reason = rawStopReason
            diagnostics.partial_success = true
            diagnostics.suggested_next_action = actionName
            diagnostics.continuation_relevant = true
            diagnostics.progress_made = true
            diagnostics.failed_because = [{
              kind: isPlanTimeout ? 'path_planning_timeout' : 'partial_progress_timeout',
              action: actionName,
              stop_reason: rawStopReason,
              progress_signals: progressSignals.signals,
              continuation_relevant: true,
              nearestRawTargetDistance: diagnostics.nearestRawTargetDistance,
              nearestRawTargetPosition: diagnostics.nearestRawTargetPosition,
              selectedTargetDistance: selectedDist,
              selectedTargetPosition: diagnostics.selectedTargetPosition,
              selectedAccessTargetDistance: diagnostics.selectedAccessTargetDistance,
              selectedAccessTargetPosition: diagnostics.selectedAccessTargetPosition,
              accessCandidatesFound: diagnostics.accessCandidatesFound,
              pathAttempts: diagnostics.pathAttempts,
              resourcePathfindingTimeoutMs: RESOURCE_PATHFINDING_TIMEOUT_MS,
              pathPlannerError: errMsg,
              recoverable: true
            }]
          } else if (
            allowExcavate &&
            accessMode === 'safe_staircase' &&
            diagnostics.excavatedBlocks < ACQUIRE_MAX_EXCAVATED_BLOCKS &&
            staircaseSteps < Math.min(ACQUIRE_MAX_STEPS, MAX_EXCAVATION_STEPS)
          ) {
            // Path failed to an underground ore (cave not connected from here). Pivot
            // immediately to staircase excavation — dig one step toward the ore instead
            // of burning more time trying to walk to it.
            // Un-ignore the block so staircase can pick it as the excavation target.
            ignoredPositions.delete(positionKey(candidate.block.position))
            diagnostics.currentSubstep = 'staircase_pivot_after_path_timeout'
            const staircaseTarget = await findNearestExcavationTarget(targetSet, radius, ignoredPositions, diagnostics)
            if (staircaseTarget) {
              const moved = await safeStaircaseStep(staircaseTarget, targetSet, diagnostics)
              if (moved) {
                attempts++
                staircaseSteps++
                diagnostics.strategy = 'safe_staircase'
                continue
              }
            }
            // Staircase pivot also failed — give up with a clear reason
            diagnostics.failure_type = 'target_unreachable'
            diagnostics.stop_reason = 'targets_found_but_not_accessible'
            diagnostics.suggested_next_action = 'navigate_to_block_type'
            diagnostics.can_retry = true
            diagnostics.failed_because = [{
              kind: 'path_timeout_staircase_also_failed',
              action: actionName,
              currentSubstep: 'staircase_pivot_after_path_timeout',
              selectedTargetPosition: diagnostics.selectedTargetPosition,
              selectedTargetDistance: selectedDist,
              resourcePathfindingTimeoutMs: RESOURCE_PATHFINDING_TIMEOUT_MS,
              pathPlannerError: errMsg,
            }]
          } else if (pathTimeoutCount < 3) {
            // Non-excavate mode — skip this candidate and try the next one.
            // The block is already in ignoredPositions so the next scan picks a different target.
            pathTimeoutCount++
            await yieldToEventLoop()
            continue
          } else {
            // No progress and we have already skipped 3 unreachable candidates — give up.
            diagnostics.failure_type = rawFailureType
            diagnostics.stop_reason = rawStopReason
            diagnostics.partial_success = diagnostics.collected > 0
            diagnostics.suggested_next_action = isPlanTimeout ? null : 'navigate_to_block_type'
            diagnostics.failed_because = [{
              kind: 'path_planning_timeout',
              action: actionName,
              currentSubstep: 'path_to_access',
              selectedTargetPosition: diagnostics.selectedTargetPosition,
              selectedTargetDistance: selectedDist,
              selectedAccessTargetPosition: diagnostics.selectedAccessTargetPosition,
              selectedAccessTargetDistance: diagnostics.selectedAccessTargetDistance,
              nearestRawTargetPosition: diagnostics.nearestRawTargetPosition,
              nearestRawTargetDistance: diagnostics.nearestRawTargetDistance,
              accessCandidatesFound: diagnostics.accessCandidatesFound,
              closeRangeFallbackAttempted: diagnostics.closeRangeFallbackAttempted,
              pathAttempts: diagnostics.pathAttempts,
              resourcePathfindingTimeoutMs: RESOURCE_PATHFINDING_TIMEOUT_MS,
              pathPlannerError: errMsg,
              recoverable: true
            }]
          }
        } else {
          diagnostics.failure_type = rawFailureType
          diagnostics.stop_reason = rawStopReason
          diagnostics.partial_success = diagnostics.collected > 0
          diagnostics.suggested_next_action = 'navigate_to_block_type'
          diagnostics.failed_because = [{
            kind: 'navigation_failed',
            action: actionName,
            currentSubstep: 'path_to_access',
            selectedTargetPosition: diagnostics.selectedTargetPosition,
            selectedTargetDistance: selectedDist,
            selectedAccessTargetPosition: diagnostics.selectedAccessTargetPosition,
            selectedAccessTargetDistance: diagnostics.selectedAccessTargetDistance,
            nearestRawTargetPosition: diagnostics.nearestRawTargetPosition,
            nearestRawTargetDistance: diagnostics.nearestRawTargetDistance,
            error: errMsg
          }]
        }

        return {
          ok: diagnostics.collected > 0,
          action: actionName,
          result: diagnostics,
          error: diagnostics.collected > 0 ? null : lastError
        }
      }

      try {
        diagnostics.digAttempts += 1
        diagnostics.currentSubstep = 'dig_target'
        await mineBlockSafe(candidate.block, targetSet)
        diagnostics.minedTargetBlocks += 1
        pathTimeoutCount = 0
        await delay(250)
      } catch (error) {
        lastError = errorMessage(error)
        diagnostics.rejectedUnreachable += 1
        stopMovement()
      }
      continue
    }

    if (
      allowExcavate &&
      accessMode === 'safe_staircase' &&
      diagnostics.excavatedBlocks < ACQUIRE_MAX_EXCAVATED_BLOCKS &&
      staircaseSteps < Math.min(ACQUIRE_MAX_STEPS, MAX_EXCAVATION_STEPS)
    ) {
      diagnostics.currentSubstep = 'excavate_staircase'
      const target = await findNearestExcavationTarget(targetSet, radius, ignoredPositions, diagnostics)
      if (!target) {
        lastError = stopReasonMessage(targetLabel, diagnostics)
        diagnostics.stop_reason = stopReasonForNoCandidate(diagnostics)
        diagnostics.suggested_next_action = suggestedActionForStopReason(diagnostics.stop_reason)
        diagnostics.can_retry = diagnostics.suggested_next_action !== 'explore_nearby'
        break
      }

      diagnostics.last_target_position = positionJson(target.position)
      // Track nearest distance end as we approach during excavation
      if (bot.entity) {
        diagnostics.nearestTargetDistanceEnd = Math.round(bot.entity.position.distanceTo(target.position) * 10) / 10
      }
      const moved = await safeStaircaseStep(target, targetSet, diagnostics)
      if (!moved) {
        ignoredPositions.add(positionKey(target.position))
        lastError = 'Safe staircase could not advance without risky digging.'
        diagnostics.stop_reason = 'targets_found_but_not_accessible'
        diagnostics.can_retry = true
        diagnostics.suggested_next_action = 'navigate_to_block_type'
        continue
      }

      attempts++
      staircaseSteps++
      diagnostics.strategy = 'safe_staircase'
      continue
    }

    lastError = stopReasonMessage(targetLabel, diagnostics)
    diagnostics.stop_reason = stopReasonForNoCandidate(diagnostics)
    diagnostics.suggested_next_action = suggestedActionForStopReason(diagnostics.stop_reason)
    diagnostics.can_retry = diagnostics.suggested_next_action !== 'explore_nearby'
    break
  }

  updateResourceInventoryDiagnostics(diagnostics, targets, startInventorySnapshot, requested)

  if (diagnostics.collected <= 0) {
    diagnostics.strategy = diagnostics.strategy === 'failed' ? 'failed' : diagnostics.strategy
    if (!diagnostics.stop_reason) {
      diagnostics.stop_reason = stopReasonForNoCandidate(diagnostics)
      diagnostics.suggested_next_action = suggestedActionForStopReason(diagnostics.stop_reason)
      diagnostics.can_retry = diagnostics.suggested_next_action !== 'explore_nearby'
    }
    return {
      ok: false,
      action: actionName,
      result: diagnostics,
      error: lastError || `No reachable ${targetLabel} found. Try explore_nearby or move closer to exposed blocks.`
    }
  }

  const originalStopReason = diagnostics.stop_reason

  if (diagnostics.collected >= requested) {
    diagnostics.partial_success = false
    diagnostics.can_retry = false
    diagnostics.suggested_next_action = null
    diagnostics.stop_reason = 'collected_requested'
  } else {
    diagnostics.partial_success = true
    diagnostics.can_retry = true
    diagnostics.suggested_next_action = 'acquire_blocks'
    const wasTimeout = originalStopReason && (
      originalStopReason.includes('timeout') || originalStopReason.includes('path_timeout')
    )
    diagnostics.stop_reason = wasTimeout ? 'partial_collected_after_timeout' : 'partial_collected'
  }

  if (originalStopReason && originalStopReason !== diagnostics.stop_reason) {
    diagnostics.original_stop_reason = originalStopReason
    diagnostics.success_due_to_inventory_delta = true
  }

  return ok(actionName, diagnostics)
}

function emptyAcquireResult(options, strategy) {
  return {
    requested: options.count || ACQUIRE_BLOCKS_DEFAULT_COUNT,
    collected: 0,
    targets: options.targets || [],
    radius: options.radius !== undefined ? options.radius : ACQUIRE_BLOCKS_DEFAULT_RADIUS,
    partial_success: false,
    can_retry: false,
    suggested_next_action: null,
    last_target_position: null,
    last_stand_position: null,
    stop_reason: null,
    strategy,
    targetCandidatesFound: 0,
    targetCandidatesFoundRaw: 0,
    exposedCandidatesFound: 0,
    accessCandidatesFound: 0,
    candidates_seen: 0,
    candidates_evaluated: 0,
    candidatesEvaluated: 0,
    scan_limited: false,
    excavatedBlocks: 0,
    minedTargetBlocks: 0,
    currentSubstep: 'scan',
    rejectedDangerous: 0,
    rejectedProtected: 0,
    rejectedUnsupported: 0,
    rejectedNoSafeStand: 0,
    rejectedNotExposed: 0,
    rejectedUnreachable: 0,
    nearestTargetDistance: null,
    nearestTargetPosition: null,
    nearestTargetDistanceEnd: null,
    nearestRawTargetDistance: null,
    nearestRawTargetPosition: null,
    selectedTargetDistance: null,
    selectedTargetPosition: null,
    selectedTargetMode: null,
    selectedCloseRangeTargetPosition: null,
    selectedAccessTargetDistance: null,
    selectedAccessTargetPosition: null,
    dropCollectionAttempted: false,
    closeDropPickupAttempted: false,
    closeDropPickupTicks: 0,
    dropCollectionPasses: 0,
    dropsCollectedThisAction: 0,
    targetInventoryDelta: 0,
    inventoryBefore: null,
    inventoryAfter: null,
    nearbyDropsFound: 0,
    relevantDropsFound: 0,
    nearestDropDistance: null,
    dropPathAttempts: 0,
    dropCollectionTimeoutMs: null,
    dropCollectionMethod: null,
    dropDirectWalkAttempted: false,
    dropDirectWalkTicks: 0,
    dropVerticalDelta: null,
    dropEntityPosition: null,
    distanceToDropStart: null,
    distanceToDropEnd: null,
    dropEntityDisappeared: false,
    dropEntityStillExists: null,
    distanceToDropMin: null,
    dropDistanceImproved: false,
    dropCollectionSucceeded: false,
    localDropRecoveryAttempted: false,
    dropSafeStandCandidatesFound: 0,
    selectedDropStandPosition: null,
    dropLocalPathAttempted: false,
    dropLocalPathSucceeded: false,
    dropLocalExcavationSteps: 0,
    dropBlockedBy: null,
    dropBlockedByDiggable: null,
    dropBlockedBySafeToDig: null,
    dropBlockedByWithinReach: null,
    blockerReason: null,
    blockerIntersectsMovementVolume: null,
    dropCollectionAbandoned: false,
    abandonedDropReason: null,
    resource_action_still_valid: null,
    dropLocalExcavationAttempted: false,
    dropLocalExcavationBlocksDug: 0,
    dropRecoveryFailureReason: null,
    distanceToDropAfterLocalRecovery: null,
    distanceToDropAfterExcavation: null,
    directWalkNoMovement: false,
    botPositionChanged: null,
    inventoryDeltaAfterDig: null,
    inventoryDeltaAfterDropCollection: null,
    targetBlockStillExists: null,
    pathfindingTimeoutMs: PATHFINDING_TIMEOUT_MS,
    resourcePathfindingTimeoutMs: RESOURCE_PATHFINDING_TIMEOUT_MS,
    pathAttempts: 0,
    digAttempts: 0,
    closeRangeFallbackAttempted: 0,
    directDigAttempted: 0,
    localStandAdjustmentAttempted: false,
    localExcavationSteps: 0,
    closeRangeFailureReason: null,
    reusedLastTarget: false,
    lastTargetStillExists: false,
    distanceToLastTarget: null,
    pathPlannerError: null,
    dropCollectabilityScore: null,
    expectedDropSafeStandCandidates: null,
    expectedDropVerticalRisk: null,
    targetRejectedForDropRisk: false,
    inventory: []
  }
}

function stopReasonForNoCandidate(diagnostics) {
  if (diagnostics.targetCandidatesFound <= 0) {
    return 'no_targets_found'
  }

  return 'targets_found_but_not_accessible'
}

function suggestedActionForStopReason(stopReason) {
  if (stopReason === 'no_targets_found') {
    return 'explore_nearby'
  }

  if (stopReason === 'targets_found_but_not_accessible' || stopReason === 'path_timeout_before_target') {
    return 'navigate_to_block_type'
  }

  return 'acquire_blocks'
}

function stopReasonMessage(targetLabel, diagnostics) {
  if (stopReasonForNoCandidate(diagnostics) === 'no_targets_found') {
    return `No ${targetLabel} found nearby. Try explore_nearby.`
  }

  return `No accessible ${targetLabel} found. Try navigate_to_block_type or move closer to exposed blocks.`
}

function inventoryCounts() {
  const counts = {}
  for (const item of inventoryJson()) {
    counts[item.name] = (counts[item.name] || 0) + item.count
  }
  return counts
}

function inventoryCountForTargets(targets) {
  const counts = inventoryCounts()
  const names = new Set()

  for (const target of targets) {
    names.add(target)
    for (const drop of (ACQUIRE_DROPS[target] || [])) {
      names.add(drop)
    }
  }

  let total = 0
  for (const name of names) {
    total += counts[name] || 0
  }
  return total
}

function targetInventoryNames(targets) {
  const names = new Set()
  const targetList = targets instanceof Set ? Array.from(targets) : (Array.isArray(targets) ? targets : [])
  for (const target of targetList) {
    names.add(target)
    for (const drop of (ACQUIRE_DROPS[target] || [])) {
      names.add(drop)
    }
  }
  return names
}

function inventoryDeltaBetween(beforeCounts, afterCounts) {
  const delta = {}
  const allKeys = new Set([
    ...Object.keys(beforeCounts || {}),
    ...Object.keys(afterCounts || {})
  ])
  for (const key of allKeys) {
    const change = (afterCounts[key] || 0) - (beforeCounts[key] || 0)
    if (change !== 0) delta[key] = change
  }
  return delta
}

function updateResourceInventoryDiagnostics(diagnostics, targets, inventoryBefore, requested) {
  const before = inventoryBefore || diagnostics.inventoryBefore || {}
  const after = inventoryCounts()
  const delta = inventoryDeltaBetween(before, after)
  const targetNames = targetInventoryNames(targets || diagnostics.targets || [])
  let targetDelta = 0
  for (const [item, change] of Object.entries(delta)) {
    if (targetNames.has(item) && change > 0) {
      targetDelta += change
    }
  }

  diagnostics.inventoryBefore = before
  diagnostics.inventoryAfter = after
  diagnostics.inventory_delta = delta
  diagnostics.targetInventoryDelta = targetDelta
  diagnostics.collected = Math.max(0, targetDelta)
  diagnostics.requested = requested || diagnostics.requested
  diagnostics.inventory = inventoryJson()
  return targetDelta
}

function resourceSuccessFromInventory(actionName, diagnostics, reason = null) {
  const collected = updateResourceInventoryDiagnostics(
    diagnostics,
    diagnostics.targets,
    diagnostics.inventoryBefore,
    diagnostics.requested
  )
  if (collected <= 0) return null

  const originalStopReason = diagnostics.stop_reason

  diagnostics.failure_type = null
  diagnostics.failed_because = []
  diagnostics.error = null
  diagnostics.dropCollectionSucceeded = diagnostics.dropCollectionAttempted ? true : diagnostics.dropCollectionSucceeded
  diagnostics.progress_made = true
  diagnostics.drop_collection_reason = reason || diagnostics.drop_collection_reason || null

  if (collected >= diagnostics.requested) {
    diagnostics.partial_success = false
    diagnostics.can_retry = false
    diagnostics.repeatable_now = false
    diagnostics.suggested_next_action = null
    diagnostics.stop_reason = 'collected_requested'
  } else {
    diagnostics.partial_success = true
    diagnostics.can_retry = true
    diagnostics.repeatable_now = true
    diagnostics.suggested_next_action = actionName
    const wasTimeout = originalStopReason && (
      originalStopReason.includes('timeout') || originalStopReason.includes('path_timeout')
    )
    diagnostics.stop_reason = wasTimeout ? 'partial_collected_after_timeout' : 'partial_collected'
  }

  if (originalStopReason && originalStopReason !== diagnostics.stop_reason) {
    diagnostics.original_stop_reason = originalStopReason
    diagnostics.success_due_to_inventory_delta = true
  }

  return ok(actionName, diagnostics)
}

function isTargetBlock(block, targets) {
  return Boolean(block && targets.has(block.name))
}

async function findTargetCandidates(targets, radius, diagnostics) {
  const matching = Array.from(targets)
    .map((name) => bot.registry.blocksByName[name])
    .filter((blockType) => blockType)
    .map((blockType) => blockType.id)

  if (matching.length === 0) {
    diagnostics.rejectedUnsupported += 1
    return []
  }

  // Raw find: fetch a pool larger than the evaluation cap so we can sort by distance
  // and prefer the nearest blocks. In debug mode allow an unlimited scan.
  const rawFetchLimit = RESOURCE_DEBUG_FULL_SCAN
    ? 65536
    : Math.max(MAX_RESOURCE_CANDIDATES_EVALUATED * 4, MAX_BLOCK_CANDIDATES)

  const positions = bot.findBlocks({
    matching,
    maxDistance: Math.min(radius, MAX_SCAN_RADIUS),
    count: rawFetchLimit
  }) || []

  const rawFound = positions.length
  diagnostics.targetCandidatesFoundRaw = (diagnostics.targetCandidatesFoundRaw || 0) + rawFound
  diagnostics.targetCandidatesFound += rawFound
  diagnostics.candidates_seen = (diagnostics.candidates_seen || 0) + rawFound

  // Convert positions to blocks and sort by distance so close blocks are evaluated first.
  const blocks = positions
    .map((position) => bot.blockAt(position))
    .filter((block) => block && isTargetBlock(block, targets))
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))

  // Record nearest raw target on first non-empty scan pass.
  if (blocks.length > 0 && diagnostics.nearestTargetDistance === null) {
    const nearest = blocks[0]
    const nearDist = Math.round(bot.entity.position.distanceTo(nearest.position) * 10) / 10
    const nearPos = positionJson(nearest.position)
    diagnostics.nearestTargetDistance = nearDist
    diagnostics.nearestTargetPosition = nearPos
    diagnostics.nearestRawTargetDistance = nearDist
    diagnostics.nearestRawTargetPosition = nearPos
  }

  await yieldToEventLoop()
  return blocks
}

async function findSurfaceAcquisitionCandidate(targets, radius, ignoredPositions, diagnostics) {
  const allCandidates = await findTargetCandidates(targets, radius, diagnostics)

  // Quick exposure pre-sort: blocks with top face open are evaluated first because
  // they are the most likely to have a safe stand position. This lets us find a
  // valid candidate in the first few evaluations instead of scanning the full list.
  const likelyExposed = []
  const buried = []
  for (const block of allCandidates) {
    const above = bot.blockAt(block.position.offset(0, 1, 0))
    if (above && canReplaceBlock(above) && !isLiquidBlock(above)) {
      likelyExposed.push(block)
    } else {
      buried.push(block)
    }
  }

  let localEval = 0
  // Collect a window of valid candidates and score each for drop collectability.
  // Candidates arrive in distance order; within a tie in score the closer one wins.
  const scoredWindow = []
  let firstWindowBlock = null

  for (const block of likelyExposed.concat(buried)) {
    // Per-pass evaluation cap prevents evaluating thousands of buried blocks per iteration.
    if (!RESOURCE_DEBUG_FULL_SCAN && localEval >= MAX_RESOURCE_CANDIDATES_EVALUATED) {
      diagnostics.scan_limited = true
      break
    }
    // Stop gathering once the window is full.
    if (scoredWindow.length >= DROP_COLLECTABILITY_WINDOW) break

    if (ignoredPositions.has(positionKey(block.position))) continue

    // Cheap pre-filters before expensive face/stand checks
    if (isProtectedBlock(block)) { diagnostics.rejectedProtected += 1; continue }
    if (isDirectlyUnderBot(block)) { diagnostics.rejectedDangerous += 1; continue }
    if (!canMineBlock(block)) { diagnostics.rejectedUnsupported += 1; continue }
    if (isDangerousAdjacent(block)) { diagnostics.rejectedDangerous += 1; continue }

    // Expensive: check exposed face then safe stand position
    localEval += 1
    diagnostics.candidatesEvaluated += 1
    diagnostics.candidates_evaluated = diagnostics.candidatesEvaluated

    const faceInfo = findExposedFace(block)
    if (!faceInfo) {
      diagnostics.rejectedNotExposed += 1
      continue
    }
    diagnostics.exposedCandidatesFound += 1

    const standPosition = findSafeStandNearFace(block, faceInfo)
    if (!standPosition) {
      diagnostics.rejectedNoSafeStand += 1
      continue
    }
    diagnostics.accessCandidatesFound += 1

    const dropScore = estimateDropCollectability(block)
    scoredWindow.push({ block, faceInfo, standPosition, dropScore })
    if (firstWindowBlock === null) firstWindowBlock = block
  }

  if (scoredWindow.length === 0) return null

  // Sort by drop collectability score descending. Array.sort is stable in V8, so
  // equal-score entries preserve insertion order — closer candidate wins ties.
  scoredWindow.sort((a, b) => b.dropScore.score - a.dropScore.score)
  const best = scoredWindow[0]

  diagnostics.dropCollectabilityScore = Math.round(best.dropScore.score * 100) / 100
  diagnostics.expectedDropSafeStandCandidates = best.dropScore.safeStandCandidates
  diagnostics.expectedDropVerticalRisk = best.dropScore.verticalRisk
  // True when a closer candidate was deprioritised in favour of one with safer drop pickup.
  diagnostics.targetRejectedForDropRisk = (
    scoredWindow.length > 1 &&
    positionKey(best.block.position) !== positionKey(firstWindowBlock.position)
  )

  return { block: best.block, faceInfo: best.faceInfo, standPosition: best.standPosition }
}

async function findSurfaceNavigationCandidate(targets, radius, diagnostics) {
  const allCandidates = await findTargetCandidates(targets, radius, diagnostics)
  let localEval = 0
  for (const block of allCandidates) {
    if (!RESOURCE_DEBUG_FULL_SCAN && localEval >= MAX_RESOURCE_CANDIDATES_EVALUATED) {
      diagnostics.scan_limited = true
      break
    }

    if (isProtectedBlock(block)) { diagnostics.rejectedProtected += 1; continue }
    if (isDirectlyUnderBot(block) || isDangerousAdjacent(block)) { diagnostics.rejectedDangerous += 1; continue }

    localEval += 1
    diagnostics.candidatesEvaluated += 1
    diagnostics.candidates_evaluated = diagnostics.candidatesEvaluated

    const faceInfo = findExposedFace(block)
    if (!faceInfo) { diagnostics.rejectedUnreachable += 1; continue }
    diagnostics.exposedCandidatesFound += 1

    const standPosition = findSafeStandNearFace(block, faceInfo)
    if (!standPosition) { diagnostics.rejectedNoSafeStand += 1; continue }
    diagnostics.accessCandidatesFound += 1

    return { block, faceInfo, standPosition }
  }

  return null
}

function findExposedFace(block) {
  for (const offset of MINE_FACE_OFFSETS) {
    const neighborPosition = block.position.plus(offset)
    const neighbor = bot.blockAt(neighborPosition)
    if (canReplaceBlock(neighbor) && !isLiquidBlock(neighbor)) {
      return { offset, position: neighborPosition }
    }
  }

  return null
}

function findSafeStandNearFace(block, faceInfo) {
  const candidates = []

  if (faceInfo.offset.y === 0) {
    candidates.push(faceInfo.position)
    candidates.push(faceInfo.position.offset(faceInfo.offset.x, 0, faceInfo.offset.z))
  }

  for (const offset of [
    new Vec3(1, 0, 0),
    new Vec3(-1, 0, 0),
    new Vec3(0, 0, 1),
    new Vec3(0, 0, -1),
    new Vec3(1, 0, 1),
    new Vec3(1, 0, -1),
    new Vec3(-1, 0, 1),
    new Vec3(-1, 0, -1)
  ]) {
    candidates.push(block.position.plus(offset))
    candidates.push(block.position.plus(offset).offset(0, 1, 0))
  }

  return candidates
    .filter((position) => isSafeStandPosition(position))
    .sort((a, b) => bot.entity.position.distanceTo(a) - bot.entity.position.distanceTo(b))[0] || null
}

function isSafeStandPosition(position) {
  if (!bot.entity) {
    return false
  }

  const floor = bot.blockAt(position.offset(0, -1, 0))
  const feet = bot.blockAt(position)
  const head = bot.blockAt(position.offset(0, 1, 0))
  const belowFloor = bot.blockAt(position.offset(0, -2, 0))

  if (!isSolidBlock(floor) || !canReplaceBlock(feet) || !canReplaceBlock(head)) {
    return false
  }

  if (isLiquidBlock(floor) || isLiquidBlock(feet) || isLiquidBlock(head) || isLiquidBlock(belowFloor)) {
    return false
  }

  return true
}

function buildDropCollectionFailure(reason, actionName, targetLabel, nearestRawDist, diagnostics) {
  diagnostics.dropEntityDisappeared = reason === 'drop_disappeared_without_inventory_delta'
    ? true
    : diagnostics.dropEntityDisappeared
  const successResponse = resourceSuccessFromInventory(actionName, diagnostics, reason)
  if (successResponse) return successResponse

  if (reason === 'internal_drop_collection_bug') {
    diagnostics.failure_type = 'internal_drop_collection_bug'
    diagnostics.stop_reason = 'drop_close_but_no_pickup_attempt'
    diagnostics.partial_success = true
    diagnostics.continuation_relevant = true
    diagnostics.failed_because = [{
      kind: 'internal_drop_collection_bug',
      action: actionName,
      stop_reason: 'drop_close_but_no_pickup_attempt',
      drop_distance: diagnostics.nearestDropDistance,
      dropVerticalDelta: diagnostics.dropVerticalDelta,
      minedTargetBlocks: diagnostics.minedTargetBlocks,
      closeDropPickupAttempted: diagnostics.closeDropPickupAttempted,
      dropDirectWalkAttempted: diagnostics.dropDirectWalkAttempted,
      continuation_relevant: true
    }]
    return {
      ok: false,
      action: actionName,
      result: diagnostics,
      error: `Drop close but no pickup attempted (dist=${diagnostics.nearestDropDistance}, vertDelta=${diagnostics.dropVerticalDelta})`
    }
  }

  const isDeepUnreachable = (
    reason === 'drop_no_safe_stand' &&
    typeof diagnostics.dropVerticalDelta === 'number' &&
    diagnostics.dropVerticalDelta <= -3 &&
    diagnostics.dropSafeStandCandidatesFound === 0
  )
  if (isDeepUnreachable) {
    const dropPos = diagnostics.dropEntityPosition
    const posKey = dropPos
      ? `${Math.round(dropPos.x)}_${Math.round(dropPos.y)}_${Math.round(dropPos.z)}`
      : null
    const dcFamily = posKey
      ? `drop_collection:${targetLabel}:${posKey}`
      : `drop_collection:${targetLabel}`
    diagnostics.stop_reason = 'drop_deep_unreachable'
    diagnostics.failure_type = 'partial_progress_timeout'
    diagnostics.partial_success = true
    diagnostics.continuation_relevant = false
    diagnostics.resource_action_still_valid = true
    diagnostics.dropCollectionAbandoned = true
    diagnostics.abandonedDropReason = 'deep_no_safe_stand'
    diagnostics.can_retry = false
    diagnostics.failed_because = [{
      kind: 'drop_deep_unreachable',
      action: actionName,
      item: targetLabel,
      dropVerticalDelta: diagnostics.dropVerticalDelta,
      dropSafeStandCandidatesFound: diagnostics.dropSafeStandCandidatesFound,
      dropEntityPosition: diagnostics.dropEntityPosition,
      same_drop_retry_not_recommended: true,
      continuation_relevant: false,
      resource_action_still_valid: true,
      drop_collection_family: dcFamily,
      minedTargetBlocks: diagnostics.minedTargetBlocks,
    }]
    return {
      ok: false,
      action: actionName,
      result: diagnostics,
      error: `Mined ${targetLabel} but drop fell deep and unreachable (vertDelta=${diagnostics.dropVerticalDelta}, noSafeStand): abandoning this drop`
    }
  }

  const isHardFail = (
    reason === 'drop_unreachable' ||
    reason === 'drop_disappeared_without_inventory_delta' ||
    reason === 'drop_direct_walk_no_progress' ||
    reason === 'drop_no_safe_stand'
  )
  const isPartialProgress = reason === 'drop_collection_partial_progress' || reason === 'drop_local_excavation_progress'

  const stopReason = isHardFail ? (reason === 'drop_direct_walk_no_progress' ? 'drop_direct_walk_no_progress' : reason)
    : isPartialProgress ? reason
    : 'mined_target_but_drop_not_collected'
  const failedKind = isHardFail ? 'drop_collection_failed' : 'mined_target_but_drop_not_collected'

  diagnostics.can_retry = true
  diagnostics.repeatable_now = true
  diagnostics.failure_type = 'partial_progress_timeout'
  diagnostics.stop_reason = stopReason
  diagnostics.partial_success = true
  diagnostics.continuation_relevant = true
  diagnostics.progress_made = true
  diagnostics.failed_because = [{
    kind: failedKind,
    action: actionName,
    stop_reason: stopReason,
    drop_collection_reason: reason,
    minedTargetBlocks: diagnostics.minedTargetBlocks,
    nearbyDropsFound: diagnostics.nearbyDropsFound,
    relevantDropsFound: diagnostics.relevantDropsFound,
    nearestDropDistance: diagnostics.nearestDropDistance,
    dropEntityPosition: diagnostics.dropEntityPosition,
    distanceToDropStart: diagnostics.distanceToDropStart,
    distanceToDropMin: diagnostics.distanceToDropMin,
    distanceToDropEnd: diagnostics.distanceToDropEnd,
    dropDistanceImproved: diagnostics.dropDistanceImproved,
    dropEntityStillExists: diagnostics.dropEntityStillExists,
    dropCollectionMethod: diagnostics.dropCollectionMethod,
    dropDirectWalkAttempted: diagnostics.dropDirectWalkAttempted,
    dropDirectWalkTicks: diagnostics.dropDirectWalkTicks,
    dropPathAttempts: diagnostics.dropPathAttempts,
    dropVerticalDelta: diagnostics.dropVerticalDelta,
    localDropRecoveryAttempted: diagnostics.localDropRecoveryAttempted,
    dropSafeStandCandidatesFound: diagnostics.dropSafeStandCandidatesFound,
    selectedDropStandPosition: diagnostics.selectedDropStandPosition,
    dropLocalPathAttempted: diagnostics.dropLocalPathAttempted,
    dropLocalPathSucceeded: diagnostics.dropLocalPathSucceeded,
    dropLocalExcavationSteps: diagnostics.dropLocalExcavationSteps,
    dropBlockedBy: diagnostics.dropBlockedBy,
    dropBlockedByDiggable: diagnostics.dropBlockedByDiggable,
    dropBlockedBySafeToDig: diagnostics.dropBlockedBySafeToDig,
    dropBlockedByWithinReach: diagnostics.dropBlockedByWithinReach,
    blockerReason: diagnostics.blockerReason,
    blockerIntersectsMovementVolume: diagnostics.blockerIntersectsMovementVolume,
    dropLocalExcavationAttempted: diagnostics.dropLocalExcavationAttempted,
    dropLocalExcavationBlocksDug: diagnostics.dropLocalExcavationBlocksDug,
    dropRecoveryFailureReason: diagnostics.dropRecoveryFailureReason,
    distanceToDropAfterLocalRecovery: diagnostics.distanceToDropAfterLocalRecovery,
    distanceToDropAfterExcavation: diagnostics.distanceToDropAfterExcavation,
    directWalkNoMovement: diagnostics.directWalkNoMovement,
    botPositionChanged: diagnostics.botPositionChanged,
    inventoryDeltaAfterDropCollection: diagnostics.inventoryDeltaAfterDropCollection,
    closeDropPickupAttempted: diagnostics.closeDropPickupAttempted,
    closeDropPickupTicks: diagnostics.closeDropPickupTicks,
    dropCollectionPasses: diagnostics.dropCollectionPasses,
    dropsCollectedThisAction: diagnostics.dropsCollectedThisAction,
    targetInventoryDelta: diagnostics.targetInventoryDelta,
    inventoryBefore: diagnostics.inventoryBefore,
    inventoryAfter: diagnostics.inventoryAfter,
    bot_position: currentPositionJson(),
    nearestRawTargetDistance: nearestRawDist,
    selectedTargetDistance: nearestRawDist,
    continuation_relevant: true
  }]
  return {
    ok: false,
    action: actionName,
    result: diagnostics,
    error: `Mined ${targetLabel} but drop collection failed: ${reason}`
  }
}

function isWalkDirectionSafe(toward) {
  if (!bot.entity) return false
  const from = bot.entity.position
  const dx = toward.x - from.x
  const dz = toward.z - from.z
  const len = Math.sqrt(dx * dx + dz * dz)
  if (len < 0.01) return true
  const nx = dx / len
  const nz = dz / len
  const aheadXZ = from.offset(nx * 1.3, 0, nz * 1.3).floored()
  const feetBlock = bot.blockAt(aheadXZ)
  const headBlock = bot.blockAt(aheadXZ.offset(0, 1, 0))
  if ((feetBlock && isLiquidBlock(feetBlock)) || (headBlock && isLiquidBlock(headBlock))) return false
  // Don't walk off a cliff (>3 block drop and not moving toward a lower drop)
  const floorAhead = bot.blockAt(aheadXZ.offset(0, -1, 0))
  if (floorAhead && canReplaceBlock(floorAhead)) {
    let drop = 0
    for (let dy = -1; dy >= -5; dy--) {
      const b = bot.blockAt(aheadXZ.offset(0, dy, 0))
      if (b && isSolidBlock(b)) break
      drop++
    }
    if (drop >= 4) return false
  }
  return true
}

function clearDropWalkControls() {
  try {
    bot.setControlState('forward', false)
    bot.setControlState('back', false)
    bot.setControlState('left', false)
    bot.setControlState('right', false)
    bot.setControlState('jump', false)
    bot.setControlState('sprint', false)
  } catch (_) {}
}

function updateDropDistanceDiagnostics(dropEntity, distance, diagnostics) {
  const rounded = Math.round(distance * 10) / 10
  diagnostics.nearestDropDistance = rounded
  diagnostics.distanceToDropEnd = rounded
  if (diagnostics.distanceToDropStart === null) {
    diagnostics.distanceToDropStart = rounded
  }
  if (diagnostics.distanceToDropMin === null || rounded < diagnostics.distanceToDropMin) {
    diagnostics.distanceToDropMin = rounded
  }
  diagnostics.dropDistanceImproved = (
    diagnostics.distanceToDropStart !== null &&
    diagnostics.distanceToDropMin !== null &&
    diagnostics.distanceToDropMin < diagnostics.distanceToDropStart - 0.05
  )
  if (dropEntity && dropEntity.position) {
    diagnostics.dropEntityPosition = positionJson(dropEntity.position)
    if (bot.entity) {
      diagnostics.dropVerticalDelta = Math.round((dropEntity.position.y - bot.entity.position.y) * 10) / 10
    }
  }
}

function nearestRelevantDrop(radius, aroundPosition) {
  const scanPos = aroundPosition || (bot.entity ? bot.entity.position : null)
  return droppedItemEntitiesNear(scanPos, radius)[0] || null
}

async function directWalkToDrop(_dropEntity, targets, startingCount, deadline, diagnostics, aroundPosition, radius) {
  diagnostics.dropDirectWalkAttempted = true
  diagnostics.dropCollectionMethod = 'direct_walk'

  let lastImprovedAt = Date.now()
  let closeTicks = 0
  const startPosition = bot.entity ? bot.entity.position.clone() : null

  try {
    while (Date.now() < deadline) {
      const delta = inventoryCountForTargets(targets) - startingCount
      if (delta > 0) {
        diagnostics.inventoryDeltaAfterDropCollection = delta
        diagnostics.dropEntityStillExists = Boolean(nearestRelevantDrop(radius, aroundPosition))
        clearDropWalkControls()
        return { collected: delta, reason: 'success' }
      }

      if (!bot.entity) {
        clearDropWalkControls()
        return { collected: 0, reason: 'bot_not_ready' }
      }

      const entity = nearestRelevantDrop(radius, aroundPosition)
      if (!entity || !entity.position) {
        clearDropWalkControls()
        diagnostics.dropEntityDisappeared = true
        diagnostics.dropEntityStillExists = false
        const afterDelta = inventoryCountForTargets(targets) - startingCount
        diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, afterDelta)
        if (afterDelta > 0) return { collected: afterDelta, reason: 'success' }
        if (diagnostics.dropDistanceImproved) {
          return { collected: 0, reason: 'drop_collection_partial_progress' }
        }
        return { collected: 0, reason: 'drop_disappeared_without_inventory_delta' }
      }

      const dropPos = entity.position
      const botPos = bot.entity.position
      const dist3d = botPos.distanceTo(dropPos)
      const vertDelta = dropPos.y - botPos.y
      diagnostics.botPositionChanged = Boolean(startPosition && botPos.distanceTo(startPosition) > 0.35)
      diagnostics.directWalkNoMovement = diagnostics.botPositionChanged === false

      diagnostics.dropEntityStillExists = true
      const previousMin = diagnostics.distanceToDropMin
      updateDropDistanceDiagnostics(entity, dist3d, diagnostics)

      if (previousMin === null || diagnostics.distanceToDropMin < previousMin - 0.05) {
        lastImprovedAt = Date.now()
      }

      if (dist3d < 1.2) {
        closeTicks += 1
        clearDropWalkControls()
        await delay(120)
        diagnostics.dropDirectWalkTicks++
        if (closeTicks >= 4) {
          const closeDelta = inventoryCountForTargets(targets) - startingCount
          diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, closeDelta)
          if (closeDelta > 0) return { collected: closeDelta, reason: 'success' }
        }
        continue
      }
      closeTicks = 0

      try {
        await bot.lookAt(new Vec3(dropPos.x, dropPos.y + 0.2, dropPos.z), true)
      } catch (_) {}

      const stuckMs = Date.now() - lastImprovedAt
      const shouldJump = stuckMs > 800 || Boolean(bot.entity.isCollidedHorizontally) || vertDelta > 0.5
      if (isWalkDirectionSafe(dropPos)) {
        bot.setControlState('forward', true)
        bot.setControlState('sprint', true)
      } else {
        bot.setControlState('forward', false)
        bot.setControlState('sprint', false)
      }
      bot.setControlState('jump', shouldJump)

      await delay(100)
      diagnostics.dropDirectWalkTicks++

      if (Date.now() - lastImprovedAt > 2000) {
        diagnostics.directWalkNoMovement = !diagnostics.botPositionChanged
        return { collected: 0, reason: 'drop_direct_walk_no_progress' }
      }
    }
  } finally {
    clearDropWalkControls()
  }

  const finalDelta = inventoryCountForTargets(targets) - startingCount
  diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, finalDelta)
  const lastDrop = nearestRelevantDrop(radius, aroundPosition)
  diagnostics.dropEntityStillExists = Boolean(lastDrop)
  if (bot.entity && lastDrop && lastDrop.position) {
    updateDropDistanceDiagnostics(lastDrop, bot.entity.position.distanceTo(lastDrop.position), diagnostics)
  }
  if (finalDelta > 0) return { collected: finalDelta, reason: 'success' }
  if (diagnostics.dropDistanceImproved) return { collected: 0, reason: 'drop_collection_partial_progress' }
  return { collected: 0, reason: 'drop_direct_walk_no_progress' }
}

function estimateDropCollectability(block) {
  // Estimate how reliably the drop from mining this block can be collected.
  // Returns { score [0.0–1.0], verticalRisk (blocks fallen), safeStandCandidates }.
  // Called during target selection to prefer blocks whose drops are reachable.
  if (!bot.entity) return { score: 1.0, verticalRisk: 0, safeStandCandidates: 2 }

  const bx = block.position.x
  const bz = block.position.z

  // Trace downward to find where the drop will land.
  // The item spawns at block level; gravity pulls it down until a solid floor.
  let dropLandY = block.position.y
  for (let fall = 0; fall < 10; fall++) {
    const floorBlock = bot.blockAt(new Vec3(bx, dropLandY - 1, bz))
    if (!floorBlock) break // unloaded chunk — stop, treat as safe
    if (isDropHazardBlock(floorBlock)) {
      return { score: 0.0, verticalRisk: fall + 1, safeStandCandidates: 0 }
    }
    if (isSolidBlock(floorBlock)) break
    dropLandY -= 1
  }

  const verticalRisk = block.position.y - dropLandY
  const dropLandPos = new Vec3(bx, dropLandY, bz)

  // Check for hazard blocks in a 3×3 column around the landing spot.
  for (let dx = -1; dx <= 1; dx++) {
    for (let dz = -1; dz <= 1; dz++) {
      if (isDropHazardBlock(bot.blockAt(dropLandPos.offset(dx, 0, dz)))) {
        return { score: 0.0, verticalRisk, safeStandCandidates: 0 }
      }
    }
  }

  // Count safe stand positions around the landing spot.
  // Check the 9 nearest XZ cells at the landing level and one block above.
  // No botY constraint — we are predicting the future bot position near the drop.
  let safeStandCandidates = 0
  for (const [dx, dz] of [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]) {
    if (
      isSafeStandPosition(dropLandPos.offset(dx, 0, dz)) ||
      isSafeStandPosition(dropLandPos.offset(dx, 1, dz))
    ) {
      safeStandCandidates += 1
    }
  }

  // Score: 1.0 for a flat, open landing; penalise fall depth and missing stands.
  let score = 1.0
  if (verticalRisk >= 3) score -= 0.6
  else if (verticalRisk === 2) score -= 0.25
  else if (verticalRisk === 1) score -= 0.1
  if (safeStandCandidates === 0) score -= 0.4
  else if (safeStandCandidates <= 1) score -= 0.1

  return { score: Math.max(0.0, score), verticalRisk, safeStandCandidates }
}

function isDropHazardBlock(block) {
  if (!block) return false
  const name = block.name || ''
  return (
    isLiquidBlock(block) ||
    name.includes('fire') ||
    name.includes('lava') ||
    name.includes('cactus') ||
    name.includes('magma')
  )
}

function isDropSafeStandPosition(position) {
  if (!bot.entity || !isSafeStandPosition(position)) return false
  const body = bot.blockAt(position)
  const head = bot.blockAt(position.offset(0, 1, 0))
  const floor = bot.blockAt(position.offset(0, -1, 0))
  if (isDropHazardBlock(body) || isDropHazardBlock(head) || isDropHazardBlock(floor)) return false

  for (const offset of [
    new Vec3(1, 0, 0),
    new Vec3(-1, 0, 0),
    new Vec3(0, 0, 1),
    new Vec3(0, 0, -1),
    new Vec3(1, 0, 1),
    new Vec3(1, 0, -1),
    new Vec3(-1, 0, 1),
    new Vec3(-1, 0, -1)
  ]) {
    const nearBody = bot.blockAt(position.plus(offset))
    const nearFloor = bot.blockAt(position.plus(offset).offset(0, -1, 0))
    if (isDropHazardBlock(nearBody) || isDropHazardBlock(nearFloor)) return false
  }
  return true
}

function findDropSafeStandCandidates(dropPosition, diagnostics) {
  if (!bot.entity || !dropPosition) return []
  const base = dropPosition.floored()
  const botY = Math.floor(bot.entity.position.y)
  const candidates = []
  const seen = new Set()

  for (const dy of [1, 0, -1]) {
    for (let r = 1; r <= 2; r++) {
      for (let dx = -r; dx <= r; dx++) {
        for (let dz = -r; dz <= r; dz++) {
          if (Math.max(Math.abs(dx), Math.abs(dz)) !== r) continue
          const candidate = new Vec3(base.x + dx, base.y + dy, base.z + dz)
          const verticalDelta = candidate.y - botY
          if (verticalDelta < -2 || verticalDelta > 1) continue
          const key = positionKey(candidate)
          if (seen.has(key)) continue
          seen.add(key)
          if (!isDropSafeStandPosition(candidate)) continue
          candidates.push(candidate)
        }
      }
    }
  }

  diagnostics.dropSafeStandCandidatesFound = candidates.length
  return candidates.sort((a, b) => {
    const aPreferredY = Math.min(Math.abs(a.y - base.y), Math.abs(a.y - (base.y + 1)))
    const bPreferredY = Math.min(Math.abs(b.y - base.y), Math.abs(b.y - (base.y + 1)))
    if (aPreferredY !== bPreferredY) return aPreferredY - bPreferredY
    const aDropDist = a.distanceTo(dropPosition)
    const bDropDist = b.distanceTo(dropPosition)
    if (Math.abs(aDropDist - bDropDist) > 0.1) return aDropDist - bDropDist
    return bot.entity.position.distanceTo(a) - bot.entity.position.distanceTo(b)
  })
}

function findDropBlockingBlock(dropPosition, diagnostics) {
  if (!bot.entity || !dropPosition) return null
  const from = bot.entity.position
  const to = dropPosition
  const dx = to.x - from.x
  const dz = to.z - from.z
  const horizontal = Math.sqrt(dx * dx + dz * dz)
  if (horizontal < 0.5) return null

  // Movement volume: bot feet block (footY) and head clearance (headY = footY + 1).
  // Blocks above headY are above the player's head and do not block horizontal movement.
  const footY = Math.floor(from.y)
  const headY = footY + 1
  const dropFloorY = Math.floor(to.y)
  const bodyMaxY = Math.max(footY, dropFloorY)

  const steps = Math.min(6, Math.max(2, Math.ceil(horizontal * 2)))
  const checked = new Set()
  for (let i = 1; i <= steps; i++) {
    const t = i / steps
    const x = Math.floor(from.x + dx * t)
    const z = Math.floor(from.z + dz * t)
    for (const y of [footY, headY, dropFloorY, dropFloorY + 1]) {
      const pos = new Vec3(x, y, z)
      const key = positionKey(pos)
      if (checked.has(key)) continue
      checked.add(key)
      const block = bot.blockAt(pos)
      if (!block || canReplaceBlock(block)) continue

      const intersects = y <= headY
      const blockerReason = !intersects ? 'above_route_ignored'
        : y <= bodyMaxY ? 'body_space'
        : 'head_space'
      diagnostics.blockerIntersectsMovementVolume = intersects
      diagnostics.blockerReason = blockerReason

      if (!intersects) continue

      diagnostics.dropBlockedBy = { name: block.name, position: positionJson(block.position) }
      return block
    }
  }
  return null
}

function isBlockSupportingBot(block) {
  if (!block || !bot.entity) return false
  const support = bot.entity.position.floored().offset(0, -1, 0)
  return block.position.x === support.x && block.position.y === support.y && block.position.z === support.z
}

function canMineDropLocalBlock(block) {
  if (!block || !DROP_LOCAL_EXCAVATION_BLOCK_NAMES.has(block.name)) return false
  if (block.name === 'deepslate') return hasPickaxeAtLeast('stone_pickaxe')
  if (['stone', 'cobblestone', 'andesite', 'diorite', 'granite'].includes(block.name)) return hasPickaxe()
  return true
}

function dropBlockerSafety(block, diagnostics) {
  const allowed = Boolean(block && DROP_LOCAL_EXCAVATION_BLOCK_NAMES.has(block.name))
  const diggable = Boolean(block && allowed && canMineDropLocalBlock(block))
  const safeToDig = Boolean(
    block &&
    diggable &&
    !isLiquidBlock(block) &&
    !isDirectlyUnderBot(block) &&
    !isBlockSupportingBot(block) &&
    !isDangerousAdjacent(block) &&
    !isProtectedBlock(block)
  )
  const withinReach = Boolean(block && bot.canDigBlock && bot.canDigBlock(block))
  diagnostics.dropBlockedByDiggable = diggable
  diagnostics.dropBlockedBySafeToDig = safeToDig
  diagnostics.dropBlockedByWithinReach = withinReach
  return { allowed, diggable, safeToDig, withinReach }
}

async function excavateDropBlocker(block, targets, startingCount, deadline, diagnostics, aroundPosition, radius) {
  if (!block) return false
  diagnostics.dropLocalExcavationAttempted = true
  diagnostics.currentSubstep = 'drop_local_excavation'

  if (diagnostics.dropLocalExcavationSteps >= DROP_LOCAL_EXCAVATION_STEP_LIMIT) {
    diagnostics.dropRecoveryFailureReason = 'drop_local_excavation_limit_reached'
    return false
  }

  let safety = dropBlockerSafety(block, diagnostics)
  if (!safety.safeToDig) {
    diagnostics.dropRecoveryFailureReason = safety.diggable
      ? 'drop_blocker_not_safe_to_dig'
      : 'drop_blocker_not_diggable'
    return false
  }

  try {
    await equipBestToolForBlock(block)
  } catch (_) {}

  safety = dropBlockerSafety(block, diagnostics)
  if (!safety.withinReach) {
    const before = bot.entity ? bot.entity.position.clone() : null
    await cautiousMoveTowardPosition(block.position, Math.min(deadline, Date.now() + 1800), diagnostics)
    const moved = Boolean(before && bot.entity && bot.entity.position.distanceTo(before) > 0.25)
    const freshAfterMove = bot.blockAt(block.position)
    if (!freshAfterMove || canReplaceBlock(freshAfterMove)) {
      diagnostics.dropBlockedByWithinReach = true
      return true
    }
    block = freshAfterMove
    safety = dropBlockerSafety(block, diagnostics)
    if (!safety.withinReach && !moved) {
      diagnostics.dropRecoveryFailureReason = 'drop_blocker_not_reachable'
      return false
    }
  }

  safety = dropBlockerSafety(block, diagnostics)
  if (!safety.safeToDig) {
    diagnostics.dropRecoveryFailureReason = 'drop_blocker_became_unsafe'
    return false
  }

  try {
    await equipBestToolForBlock(block)
    await bot.lookAt(block.position.offset(0.5, 0.5, 0.5), true)
    await digBlockWithTimeout(block, 3000)
    diagnostics.dropLocalExcavationSteps += 1
    diagnostics.dropLocalExcavationBlocksDug += 1
    await delay(250)

    const delta = inventoryCountForTargets(targets) - startingCount
    diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, delta)
    const nearby = droppedItemEntitiesNear(aroundPosition || (bot.entity ? bot.entity.position : null), radius)
    diagnostics.nearbyDropsFound = nearby.length
    diagnostics.relevantDropsFound = nearby.length
    const nearest = nearby[0] || null
    if (nearest && bot.entity) {
      updateDropDistanceDiagnostics(nearest, bot.entity.position.distanceTo(nearest.position), diagnostics)
      diagnostics.distanceToDropAfterExcavation = diagnostics.distanceToDropEnd
    }
    return true
  } catch (error) {
    stopMovement()
    diagnostics.dropRecoveryFailureReason = `drop_blocker_dig_failed:${errorMessage(error)}`
    return false
  }
}

async function cautiousMoveTowardPosition(position, deadline, diagnostics) {
  if (!bot.entity || !position) return false
  const start = bot.entity.position.clone()
  const end = Math.min(Date.now() + 1500, deadline)
  try {
    while (Date.now() < end && bot.entity && bot.entity.position.distanceTo(position) > 1.5) {
      try {
        await bot.lookAt(position.offset(0.5, 0.2, 0.5), true)
      } catch (_) {}
      bot.setControlState('forward', true)
      bot.setControlState('sprint', true)
      bot.setControlState('jump', Boolean(bot.entity.isCollidedHorizontally))
      await delay(100)
    }
  } finally {
    clearDropWalkControls()
  }
  const moved = Boolean(bot.entity && bot.entity.position.distanceTo(start) > 0.35)
  diagnostics.botPositionChanged = diagnostics.botPositionChanged || moved
  return moved
}

async function localDropRecovery(targets, startingCount, deadline, diagnostics, aroundPosition, radius) {
  diagnostics.localDropRecoveryAttempted = true
  diagnostics.currentSubstep = 'local_drop_recovery'

  let drop = nearestRelevantDrop(radius, aroundPosition)
  if (!drop || !drop.position) {
    diagnostics.dropEntityStillExists = false
    diagnostics.dropRecoveryFailureReason = 'drop_missing_before_local_recovery'
    const delta = inventoryCountForTargets(targets) - startingCount
    diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, delta)
    return delta > 0 ? { collected: delta, reason: 'success' } : { collected: 0, reason: 'drop_disappeared_without_inventory_delta' }
  }

  diagnostics.dropEntityStillExists = true
  updateDropDistanceDiagnostics(drop, bot.entity.position.distanceTo(drop.position), diagnostics)

  const blockingBlock = findDropBlockingBlock(drop.position, diagnostics)
  let blockerDug = false
  if (blockingBlock) {
    blockerDug = await excavateDropBlocker(blockingBlock, targets, startingCount, deadline, diagnostics, aroundPosition, radius)
    const excavationDelta = inventoryCountForTargets(targets) - startingCount
    if (excavationDelta > 0) {
      return { collected: excavationDelta, reason: 'success' }
    }

    drop = nearestRelevantDrop(radius, aroundPosition)
    if (!drop || !drop.position) {
      diagnostics.dropEntityStillExists = false
      diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, excavationDelta)
      return excavationDelta > 0
        ? { collected: excavationDelta, reason: 'success' }
        : { collected: 0, reason: 'drop_disappeared_without_inventory_delta' }
    }

    if (blockerDug && Date.now() < deadline - 500) {
      const walkResult = await directWalkToDrop(drop, targets, startingCount, deadline, diagnostics, aroundPosition, radius)
      const walkDelta = inventoryCountForTargets(targets) - startingCount
      if (walkResult.reason === 'success' || walkDelta > 0) {
        return { collected: Math.max(walkResult.collected || 0, walkDelta), reason: 'success' }
      }
      diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, walkDelta)
    }
  }

  drop = nearestRelevantDrop(radius, aroundPosition)
  if (!drop || !drop.position) {
    const delta = inventoryCountForTargets(targets) - startingCount
    diagnostics.dropEntityStillExists = false
    diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, delta)
    return delta > 0 ? { collected: delta, reason: 'success' } : { collected: 0, reason: 'drop_disappeared_without_inventory_delta' }
  }

  const standCandidates = findDropSafeStandCandidates(drop.position, diagnostics)
  if (standCandidates.length <= 0) {
    diagnostics.dropRecoveryFailureReason = 'no_safe_stand_near_drop'
    diagnostics.distanceToDropAfterLocalRecovery = diagnostics.distanceToDropEnd
    return { collected: 0, reason: 'drop_no_safe_stand' }
  }

  const standPosition = standCandidates[0]
  diagnostics.selectedDropStandPosition = positionJson(standPosition)

  diagnostics.dropLocalPathAttempted = true
  try {
    await withTimeout(
      bot.pathfinder.goto(new goals.GoalNear(standPosition.x, standPosition.y, standPosition.z, 1)),
      Math.min(DROP_LOCAL_PATH_TIMEOUT_MS, Math.max(500, deadline - Date.now())),
      'local drop recovery path'
    )
    diagnostics.dropLocalPathSucceeded = true
  } catch (error) {
    stopMovement()
    diagnostics.dropLocalPathSucceeded = false
    diagnostics.dropRecoveryFailureReason = `local_path_failed:${errorMessage(error)}`
    await cautiousMoveTowardPosition(standPosition, deadline, diagnostics)
  }

  await delay(250)
  const delta = inventoryCountForTargets(targets) - startingCount
  diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, delta)
  if (delta > 0) return { collected: delta, reason: 'success' }

  const finalDrop = nearestRelevantDrop(radius, aroundPosition)
  diagnostics.dropEntityStillExists = Boolean(finalDrop)
  if (!finalDrop || !finalDrop.position) {
    diagnostics.dropEntityDisappeared = true
    return { collected: 0, reason: 'drop_disappeared_without_inventory_delta' }
  }

  const finalDistance = bot.entity.position.distanceTo(finalDrop.position)
  updateDropDistanceDiagnostics(finalDrop, finalDistance, diagnostics)
  diagnostics.distanceToDropAfterLocalRecovery = diagnostics.distanceToDropEnd

  if (diagnostics.dropDistanceImproved) {
    if (diagnostics.dropLocalExcavationBlocksDug > 0) {
      diagnostics.dropRecoveryFailureReason = 'drop_local_excavation_progress'
      return { collected: 0, reason: 'drop_local_excavation_progress' }
    }
    return { collected: 0, reason: 'drop_collection_partial_progress' }
  }
  if (diagnostics.dropLocalExcavationBlocksDug > 0) {
    diagnostics.dropRecoveryFailureReason = 'drop_local_excavation_progress'
    return { collected: 0, reason: 'drop_local_excavation_progress' }
  }
  if (!diagnostics.dropRecoveryFailureReason) {
    diagnostics.dropRecoveryFailureReason = 'local_recovery_no_progress'
  }
  return { collected: 0, reason: 'drop_direct_walk_no_progress' }
}

async function closeDropPickup(dropEntity, targets, startingCount, pickupDeadline, diagnostics, aroundPosition, radius) {
  diagnostics.closeDropPickupAttempted = true
  diagnostics.dropCollectionMethod = diagnostics.dropCollectionMethod || 'close_pickup'

  const startPos = bot.entity ? bot.entity.position.clone() : null

  try {
    while (Date.now() < pickupDeadline) {
      const delta = inventoryCountForTargets(targets) - startingCount
      if (delta > 0) {
        clearDropWalkControls()
        diagnostics.inventoryDeltaAfterDropCollection = delta
        return { collected: delta, reason: 'success' }
      }

      if (!bot.entity) {
        clearDropWalkControls()
        return { collected: 0, reason: 'bot_not_ready' }
      }

      const entity = nearestRelevantDrop(radius, aroundPosition)
      if (!entity || !entity.position) {
        clearDropWalkControls()
        const afterDelta = inventoryCountForTargets(targets) - startingCount
        diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, afterDelta)
        diagnostics.dropEntityStillExists = false
        if (afterDelta > 0) return { collected: afterDelta, reason: 'success' }
        return { collected: 0, reason: 'drop_disappeared_without_inventory_delta' }
      }

      const dropPos = entity.position
      const botPos = bot.entity.position
      const dist3d = botPos.distanceTo(dropPos)
      const vertDelta = dropPos.y - botPos.y

      diagnostics.dropEntityStillExists = true
      updateDropDistanceDiagnostics(entity, dist3d, diagnostics)
      diagnostics.closeDropPickupTicks += 1
      diagnostics.botPositionChanged = Boolean(startPos && botPos.distanceTo(startPos) > 0.2)

      try { await bot.lookAt(new Vec3(dropPos.x, dropPos.y + 0.2, dropPos.z), true) } catch (_) {}

      const stuckHoriz = Boolean(bot.entity.isCollidedHorizontally)

      if (dist3d < 1.0 && Math.abs(vertDelta) < 0.5) {
        // Very close, same level — micro nudge in all directions until auto-pickup
        bot.setControlState('forward', true)
        await delay(80)
        clearDropWalkControls()
        await delay(80)
      } else if (vertDelta < -0.3) {
        // Drop is below — walk toward it without sneaking so the bot can step off the ledge
        if (isWalkDirectionSafe(dropPos)) {
          bot.setControlState('forward', true)
          bot.setControlState('sprint', false)
          bot.setControlState('jump', stuckHoriz)
          await delay(150)
          clearDropWalkControls()
          await delay(80)
        } else {
          // Horizontal direction is not safe; try a brief nudge toward drop anyway
          bot.setControlState('forward', true)
          bot.setControlState('sprint', false)
          await delay(120)
          clearDropWalkControls()
          await delay(100)
        }
      } else {
        // Normal — walk toward drop, jump over obstacles
        const shouldJump = stuckHoriz || vertDelta > 0.3
        if (isWalkDirectionSafe(dropPos)) {
          bot.setControlState('forward', true)
          bot.setControlState('sprint', false)
          bot.setControlState('jump', shouldJump)
          await delay(130)
          clearDropWalkControls()
          await delay(80)
        } else {
          bot.setControlState('forward', true)
          bot.setControlState('sprint', false)
          bot.setControlState('jump', true)
          await delay(130)
          clearDropWalkControls()
          await delay(80)
        }
      }
    }
  } finally {
    clearDropWalkControls()
  }

  const finalDelta = Math.max(0, inventoryCountForTargets(targets) - startingCount)
  diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, finalDelta)
  diagnostics.botPositionChanged = Boolean(startPos && bot.entity && bot.entity.position.distanceTo(startPos) > 0.2)

  if (finalDelta > 0) return { collected: finalDelta, reason: 'success' }
  if (diagnostics.botPositionChanged || diagnostics.dropDistanceImproved) {
    return { collected: 0, reason: 'drop_collection_partial_progress' }
  }
  return { collected: 0, reason: 'drop_close_pickup_no_progress' }
}

async function collectNearbyDrops({ aroundPosition, targets, radius = DROP_COLLECTION_RADIUS, timeoutMs = DROP_COLLECTION_TIMEOUT_MS }, diagnostics) {
  diagnostics.dropCollectionAttempted = true
  diagnostics.dropCollectionTimeoutMs = timeoutMs
  diagnostics.targetBlockStillExists = Boolean(
    aroundPosition && (() => { const b = bot.blockAt(aroundPosition); return b && b.name !== 'air' })()
  )

  const startingCount = inventoryCountForTargets(targets)
  const deadline = Date.now() + timeoutMs

  const succeed = (delta) => {
    diagnostics.dropCollectionSucceeded = true
    diagnostics.dropsCollectedThisAction = (diagnostics.dropsCollectedThisAction || 0) + delta
    diagnostics.targetInventoryDelta = (diagnostics.targetInventoryDelta || 0) + delta
    diagnostics.dropEntityStillExists = Boolean(nearestRelevantDrop(radius, aroundPosition || (bot.entity ? bot.entity.position : null)))
    diagnostics.stop_reason = diagnostics.dropLocalExcavationBlocksDug > 0
      ? 'collected_drop_after_local_excavation'
      : 'collected_drop'
    diagnostics.collected = delta
    diagnostics.inventoryDeltaAfterDig = delta
    diagnostics.inventoryDeltaAfterDropCollection = delta
    if (bot.entity && diagnostics.dropEntityPosition) {
      const ep = diagnostics.dropEntityPosition
      try {
        diagnostics.distanceToDropEnd = Math.round(
          bot.entity.position.distanceTo(new Vec3(ep.x, ep.y, ep.z)) * 10
        ) / 10
      } catch (_) {}
    }
    return { collected: delta, reason: 'success' }
  }

  // Wait for drop entity to spawn after mining
  await delay(750)

  while (Date.now() < deadline) {
    const currentCount = inventoryCountForTargets(targets)
    const delta = currentCount - startingCount
    if (delta > 0) return succeed(delta)

    diagnostics.dropCollectionPasses += 1

    if (!bot.entity) return { collected: 0, reason: 'bot_not_ready' }

    const scanPos = aroundPosition || bot.entity.position
    const nearby = droppedItemEntitiesNear(scanPos, radius)
    diagnostics.nearbyDropsFound = nearby.length
    diagnostics.relevantDropsFound = nearby.length

    if (nearby.length === 0) {
      diagnostics.dropEntityStillExists = false
      const remaining = deadline - Date.now()
      if (remaining > 200) { await delay(Math.min(300, remaining - 100)); continue }
      break
    }

    const nearest = nearby[0]
    const nearestDist = bot.entity.position.distanceTo(nearest.position)
    diagnostics.dropEntityStillExists = true
    updateDropDistanceDiagnostics(nearest, nearestDist, diagnostics)

    // Record drop position and start distance on first sighting
    diagnostics.dropEntityPosition = positionJson(nearest.position)
    diagnostics.dropVerticalDelta = Math.round((nearest.position.y - bot.entity.position.y) * 10) / 10

    // Very close drop: use dedicated close pickup routine on the first encounter.
    // Handles vertical deltas (drop 1 block below), micro-nudges, and step-downs.
    // Only runs once; on failure the outer loop falls through to directWalkToDrop.
    if (nearestDist <= CLOSE_DROP_PICKUP_RADIUS && !diagnostics.closeDropPickupAttempted) {
      const pickupDeadline = Math.min(deadline, Date.now() + CLOSE_DROP_PICKUP_TIMEOUT_MS)
      const pickupResult = await closeDropPickup(nearest, targets, startingCount, pickupDeadline, diagnostics, aroundPosition, radius)
      const pickupDelta = inventoryCountForTargets(targets) - startingCount
      if (pickupResult.reason === 'success' || pickupDelta > 0) return succeed(Math.max(pickupResult.collected || 0, pickupDelta))
      if (pickupResult.reason === 'drop_disappeared_without_inventory_delta') {
        diagnostics.inventoryDeltaAfterDig = 0
        diagnostics.inventoryDeltaAfterDropCollection = 0
        return pickupResult
      }
      if (pickupResult.reason === 'drop_collection_partial_progress') {
        if (deadline - Date.now() >= 1000) continue
        diagnostics.inventoryDeltaAfterDig = 0
        return pickupResult
      }
      // drop_close_pickup_no_progress: fall through to directWalkToDrop below
    }

    const entityId = nearest.id

    if (nearestDist <= DROP_DIRECT_WALK_RADIUS) {
      // Close enough: skip pathfinder, walk directly
      diagnostics.dropCollectionMethod = diagnostics.dropCollectionMethod || 'direct_walk'
      const result = await directWalkToDrop(nearest, targets, startingCount, deadline, diagnostics, aroundPosition, radius)
      const afterDelta = inventoryCountForTargets(targets) - startingCount
      if (result.reason === 'success' || afterDelta > 0) return succeed(Math.max(result.collected || 0, afterDelta))
      if (result.reason === 'drop_direct_walk_no_progress') {
        const recovery = await localDropRecovery(targets, startingCount, deadline, diagnostics, aroundPosition, radius)
        const recoveryDelta = inventoryCountForTargets(targets) - startingCount
        if (recovery.reason === 'success' || recoveryDelta > 0) return succeed(Math.max(recovery.collected || 0, recoveryDelta))
        diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, recoveryDelta)
        // Retry from new position if time allows (pass 2+)
        if (deadline - Date.now() >= 1000) continue
        diagnostics.inventoryDeltaAfterDig = 0
        return recovery
      }
      diagnostics.inventoryDeltaAfterDig = 0
      diagnostics.inventoryDeltaAfterDropCollection = 0
      return result
    }

    // Farther drop: try pathfinder first
    diagnostics.dropCollectionMethod = diagnostics.dropCollectionMethod || 'pathfinder'
    diagnostics.dropPathAttempts += 1
    const pathMs = Math.min(4000, deadline - Date.now() - 800)
    if (pathMs < 500) break

    try {
      await withTimeout(
        bot.pathfinder.goto(new goals.GoalNear(nearest.position.x, nearest.position.y, nearest.position.z, 1)),
        pathMs,
        'collect dropped item path'
      )
      await delay(300)
    } catch (_) {
      stopMovement()
      const afterDelta = inventoryCountForTargets(targets) - startingCount
      if (afterDelta > 0) return succeed(afterDelta)

      const stillPresent = Boolean(bot.entities && bot.entities[entityId] && bot.entities[entityId].position)
      if (!stillPresent) {
        diagnostics.dropEntityDisappeared = true
        diagnostics.inventoryDeltaAfterDig = 0
        diagnostics.inventoryDeltaAfterDropCollection = 0
        return { collected: 0, reason: 'drop_disappeared_without_inventory_delta' }
      }

      // Pathfinder failed but drop is still there — fall back to direct walk
      const distNow = bot.entity.position.distanceTo(nearest.position)
      if (distNow <= DROP_DIRECT_WALK_RADIUS * 1.5 && deadline - Date.now() >= 1000) {
        diagnostics.dropCollectionMethod = 'direct_walk'
        const walkResult = await directWalkToDrop(nearest, targets, startingCount, deadline, diagnostics, aroundPosition, radius)
        const walkDelta = inventoryCountForTargets(targets) - startingCount
        if (walkResult.reason === 'success' || walkDelta > 0) return succeed(Math.max(walkResult.collected || 0, walkDelta))
        if (walkResult.reason === 'drop_direct_walk_no_progress') {
          const recovery = await localDropRecovery(targets, startingCount, deadline, diagnostics, aroundPosition, radius)
          const recoveryDelta = inventoryCountForTargets(targets) - startingCount
          if (recovery.reason === 'success' || recoveryDelta > 0) return succeed(Math.max(recovery.collected || 0, recoveryDelta))
          diagnostics.inventoryDeltaAfterDropCollection = Math.max(0, recoveryDelta)
          // Retry from new position if time allows (pass 2+)
          if (deadline - Date.now() >= 1000) continue
          diagnostics.inventoryDeltaAfterDig = 0
          return recovery
        }
        diagnostics.inventoryDeltaAfterDig = 0
        diagnostics.inventoryDeltaAfterDropCollection = 0
        return walkResult
      }

      diagnostics.inventoryDeltaAfterDig = 0
      diagnostics.inventoryDeltaAfterDropCollection = 0
      return { collected: 0, reason: 'drop_unreachable' }
    }
  }

  const finalDelta = Math.max(0, inventoryCountForTargets(targets) - startingCount)
  diagnostics.inventoryDeltaAfterDig = finalDelta
  diagnostics.inventoryDeltaAfterDropCollection = finalDelta
  if (finalDelta > 0) {
    return succeed(finalDelta)
  }

  // Bug guard: a close drop was observed but no pickup was ever attempted.
  if (
    diagnostics.dropEntityStillExists === true &&
    diagnostics.nearestDropDistance !== null &&
    diagnostics.nearestDropDistance <= CLOSE_DROP_PICKUP_RADIUS &&
    !diagnostics.closeDropPickupAttempted &&
    !diagnostics.dropDirectWalkAttempted
  ) {
    return { collected: 0, reason: 'internal_drop_collection_bug' }
  }

  return { collected: 0, reason: 'drop_collection_timeout' }
}

async function closeRangeAccessFallback(targetBlock, targetSet, diagnostics) {
  diagnostics.closeRangeFallbackAttempted += 1
  diagnostics.closeRangeFailureReason = null

  // 1. Try direct dig if in arm reach
  diagnostics.directDigAttempted += 1
  let directDigThrew = false
  try {
    if (bot.canDigBlock && bot.canDigBlock(targetBlock)) {
      await equipBestToolForBlock(targetBlock)
      await bot.lookAt(targetBlock.position.offset(0.5, 0.5, 0.5), true)
      await digBlockWithTimeout(targetBlock, ACQUIRE_DIG_TIMEOUT_MS)
      return { ok: true, mined: true }
    }
  } catch (_) {
    directDigThrew = true
  }

  // 2. Short local stand adjustment: GoalNear within 1 block, then retry direct dig
  diagnostics.localStandAdjustmentAttempted = true
  let goalNearFailed = false
  try {
    const tp = targetBlock.position
    await withTimeout(
      bot.pathfinder.goto(new goals.GoalNear(tp.x, tp.y, tp.z, 1)),
      CLOSE_RANGE_PATH_TIMEOUT_MS,
      'close range stand adjustment'
    )
    const freshBlock = bot.blockAt(targetBlock.position)
    if (!freshBlock || !isTargetBlock(freshBlock, targetSet)) {
      diagnostics.closeRangeFailureReason = 'target_missing'
      return { ok: false }
    }
    if (bot.canDigBlock && bot.canDigBlock(freshBlock)) {
      await equipBestToolForBlock(freshBlock)
      await bot.lookAt(freshBlock.position.offset(0.5, 0.5, 0.5), true)
      await digBlockWithTimeout(freshBlock, ACQUIRE_DIG_TIMEOUT_MS)
      return { ok: true, mined: true }
    }
    return { ok: true, moved: true }
  } catch (_) {
    stopMovement()
    goalNearFailed = true
  }

  // 3. Local excavation: dig blocking non-dangerous blocks toward the target
  if (!bot.entity) {
    diagnostics.closeRangeFailureReason = 'target_out_of_reach'
    return { ok: false }
  }
  const base = bot.entity.position.floored()
  const direction = staircaseDirection(base, targetBlock.position)
  let excavated = 0
  let hadLiquid = false
  let hadDangerous = false
  const checkPositions = localAccessExcavationPositions(base, targetBlock.position, direction)
  for (const pos of checkPositions) {
    if (excavated >= LOCAL_EXCAVATION_STEP_LIMIT) break
    const b = bot.blockAt(pos)
    if (!b || canReplaceBlock(b)) continue
    if (isTargetBlock(b, targetSet)) continue
    if (isDirectlyUnderBot(b)) continue
    if (isLiquidBlock(b)) { hadLiquid = true; continue }
    if (isDangerousAdjacent(b)) { hadDangerous = true; continue }
    if (!canExcavateAccessBlock(b, diagnostics)) continue
    try {
      diagnostics.dropBlockedBy = diagnostics.dropBlockedBy || { name: b.name, position: positionJson(b.position) }
      diagnostics.dropBlockedByDiggable = true
      diagnostics.dropBlockedBySafeToDig = true
      diagnostics.dropBlockedByWithinReach = bot.canDigBlock ? bot.canDigBlock(b) : null
      await digAccessBlock(b, diagnostics)
      excavated += 1
      diagnostics.localExcavationSteps += 1
    } catch (_) {
      continue
    }
  }

  // After excavation retry direct dig
  if (excavated > 0) {
    const positionBeforePostExcavationMove = bot.entity ? bot.entity.position.clone() : null
    try {
      const tp = targetBlock.position
      await withTimeout(
        bot.pathfinder.goto(new goals.GoalNear(tp.x, tp.y, tp.z, 1)),
        Math.min(3000, CLOSE_RANGE_PATH_TIMEOUT_MS),
        'close range stand adjustment after local excavation'
      )
    } catch (_) {
      stopMovement()
      try {
        await cautiousMoveTowardPosition(targetBlock.position, Date.now() + 1800, diagnostics)
      } catch (_) {
        stopMovement()
      }
    }

    try {
      const freshBlock = bot.blockAt(targetBlock.position)
      if (freshBlock && isTargetBlock(freshBlock, targetSet) && bot.canDigBlock && bot.canDigBlock(freshBlock)) {
        await equipBestToolForBlock(freshBlock)
        await bot.lookAt(freshBlock.position.offset(0.5, 0.5, 0.5), true)
        await digBlockWithTimeout(freshBlock, ACQUIRE_DIG_TIMEOUT_MS)
        return { ok: true, mined: true }
      }
      const movedAfterExcavation = Boolean(
        bot.entity &&
        positionBeforePostExcavationMove &&
        bot.entity.position.distanceTo(positionBeforePostExcavationMove) > 0.25
      )
      if (freshBlock && isTargetBlock(freshBlock, targetSet) && movedAfterExcavation) {
        return { ok: true, moved: true }
      }
    } catch (_) {
      // fall through
    }
    diagnostics.closeRangeFailureReason = excavated >= LOCAL_EXCAVATION_STEP_LIMIT
      ? 'local_excavation_limit_reached'
      : 'target_out_of_reach'
    return { ok: false }
  }

  // No excavation was possible — set the most specific reason
  if (hadLiquid) {
    diagnostics.closeRangeFailureReason = 'water_or_lava_risk'
  } else if (hadDangerous) {
    diagnostics.closeRangeFailureReason = 'unsafe_blocks_between_bot_and_target'
  } else if (directDigThrew) {
    diagnostics.closeRangeFailureReason = 'direct_dig_failed'
  } else {
    diagnostics.closeRangeFailureReason = 'no_diggable_block_toward_target'
  }
  return { ok: false }
}

async function approachTarget(_block, standPosition) {
  await withTimeout(
    bot.pathfinder.goto(new goals.GoalBlock(standPosition.x, standPosition.y, standPosition.z)),
    ACQUIRE_PATH_TIMEOUT_MS,
    'pathing to target block'
  )
}

async function mineBlockSafe(block, targets) {
  const freshBlock = bot.blockAt(block.position)

  if (!isTargetBlock(freshBlock, targets)) {
    throw new Error('Target block changed before mining.')
  }

  if (isDirectlyUnderBot(freshBlock) || isProtectedBlock(freshBlock) || isDangerousAdjacent(freshBlock) || !canMineBlock(freshBlock)) {
    throw new Error(`Refusing unsafe target block: ${freshBlock ? freshBlock.name : 'missing'}.`)
  }

  await equipBestToolForBlock(freshBlock)
  await bot.lookAt(freshBlock.position.offset(0.5, 0.5, 0.5), true)
  await digBlockWithTimeout(freshBlock, ACQUIRE_DIG_TIMEOUT_MS)
}

async function findNearestExcavationTarget(targets, radius, ignoredPositions, diagnostics) {
  // Candidates are already distance-sorted by findTargetCandidates; return the first passing block.
  const cap = RESOURCE_DEBUG_FULL_SCAN ? Infinity : MAX_RESOURCE_CANDIDATES_EVALUATED
  let checked = 0
  for (const block of await findTargetCandidates(targets, radius, diagnostics)) {
    if (++checked > cap) break
    if (ignoredPositions.has(positionKey(block.position))) continue
    if (isProtectedBlock(block)) continue
    if (isDirectlyUnderBot(block)) continue
    if (!canMineBlock(block)) continue
    if (isDangerousAdjacent(block)) continue
    return block
  }
  return null
}

async function safeStaircaseStep(target, targets, diagnostics) {
  if (!bot.entity || diagnostics.excavatedBlocks >= ACQUIRE_MAX_EXCAVATED_BLOCKS) {
    return false
  }

  if (isDangerousAdjacent(bot.blockAt(bot.entity.position.floored()))) {
    diagnostics.rejectedDangerous += 1
    return false
  }

  const base = bot.entity.position.floored()
  const direction = staircaseDirection(base, target.position)
  const spaces = [
    base.offset(direction.x, 0, direction.z),
    base.offset(direction.x, 1, direction.z)
  ]

  for (const position of spaces) {
    const block = bot.blockAt(position)
    if (canReplaceBlock(block)) {
      continue
    }

    if (isTargetBlock(block, targets)) {
      return true
    }

    if (!canExcavateAccessBlock(block, diagnostics)) {
      return false
    }

    await digAccessBlock(block, diagnostics)
  }

  let standPosition = spaces[0]
  if (target.position.y < base.y) {
    const downForward = base.offset(direction.x, -1, direction.z)
    const downBlock = bot.blockAt(downForward)
    if (!isTargetBlock(downBlock, targets) && !canReplaceBlock(downBlock)) {
      if (!canExcavateAccessBlock(downBlock, diagnostics)) {
        return false
      }
      await digAccessBlock(downBlock, diagnostics)
    }

    if (isSafeStandPosition(downForward)) {
      standPosition = downForward
    }
  }

  if (!isSafeStandPosition(standPosition)) {
    diagnostics.rejectedNoSafeStand += 1
    return false
  }

  await withTimeout(
    bot.pathfinder.goto(new goals.GoalBlock(standPosition.x, standPosition.y, standPosition.z)),
    ACQUIRE_PATH_TIMEOUT_MS,
    'pathing along safe staircase'
  )
  return true
}

function staircaseDirection(from, to) {
  const dx = to.x - from.x
  const dz = to.z - from.z

  if (Math.abs(dx) >= Math.abs(dz)) {
    return new Vec3(Math.sign(dx) || 1, 0, 0)
  }

  return new Vec3(0, 0, Math.sign(dz) || 1)
}

function localAccessExcavationPositions(from, to, direction) {
  const positions = []
  const seen = new Set()
  const add = (position) => {
    const key = positionKey(position)
    if (seen.has(key)) return
    seen.add(key)
    positions.push(position)
  }

  const dx = to.x - from.x
  const dz = to.z - from.z
  const steps = Math.max(Math.abs(dx), Math.abs(dz), 1)
  const yLevels = [from.y, from.y + 1, from.y - 1, to.y + 1, to.y]
  const sideOffsets = [
    [0, 0],
    [Math.sign(dx) || 0, 0],
    [0, Math.sign(dz) || 0],
    [-(Math.sign(dx) || 0), 0],
    [0, -(Math.sign(dz) || 0)],
  ]

  for (let i = 1; i <= steps; i++) {
    const x = Math.round(from.x + (dx * i) / steps)
    const z = Math.round(from.z + (dz * i) / steps)
    for (const y of yLevels) {
      for (const [ox, oz] of sideOffsets) {
        add(new Vec3(x + ox, y, z + oz))
      }
    }
  }

  // Keep the original single-axis probes as a cheap fallback for tight corners.
  for (const pos of [
    from.offset(direction.x, 0, direction.z),
    from.offset(direction.x, 1, direction.z),
    from.offset(direction.x, -1, direction.z),
    from.offset(0, 0, direction.z),
    from.offset(0, 1, direction.z),
    from.offset(direction.x, 2, direction.z),
  ]) {
    add(pos)
  }

  return positions
}

function canExcavateAccessBlock(block, diagnostics) {
  if (!block || canReplaceBlock(block)) {
    return true
  }

  if (isDirectlyUnderBot(block)) {
    diagnostics.rejectedDangerous += 1
    return false
  }

  if (isProtectedBlock(block)) {
    diagnostics.rejectedProtected += 1
    return false
  }

  if (isDangerousAdjacent(block)) {
    diagnostics.rejectedDangerous += 1
    return false
  }

  if (!isSoftExposureBlock(block) && !HARD_EXCAVATE_BLOCK_NAMES.has(block.name)) {
    diagnostics.rejectedUnsupported += 1
    return false
  }

  return true
}

async function digAccessBlock(block, diagnostics) {
  if (diagnostics.excavatedBlocks >= ACQUIRE_MAX_EXCAVATED_BLOCKS) {
    throw new Error('Excavation limit reached.')
  }

  await equipBestToolForBlock(block)
  await bot.lookAt(block.position.offset(0.5, 0.5, 0.5), true)
  await digBlockWithTimeout(block, ACQUIRE_DIG_TIMEOUT_MS)
  diagnostics.excavatedBlocks += 1
  await delay(100)
}

function canMineBlock(block) {
  if (!block || !ACQUIRE_ALLOWED_TARGETS.has(block.name)) {
    return false
  }

  if (isProtectedBlock(block)) {
    return false
  }

  if (WOOD_BLOCK_NAMES.has(block.name)) {
    return true
  }

  if (['stone', 'cobblestone', 'coal_ore'].includes(block.name)) {
    return hasPickaxe()
  }

  if (['deepslate', 'deepslate_coal_ore'].includes(block.name)) {
    return hasPickaxeAtLeast('stone_pickaxe')
  }

  if (['iron_ore', 'deepslate_iron_ore', 'copper_ore', 'deepslate_copper_ore'].includes(block.name)) {
    return hasPickaxeAtLeast('stone_pickaxe')
  }

  return true
}

async function equipBestToolForBlock(block) {
  if (!block) {
    return null
  }

  if (WOOD_BLOCK_NAMES.has(block.name)) {
    return await equipBestAvailableTool(AXE_PRIORITY)
  }

  if (['stone', 'cobblestone', 'deepslate', 'andesite', 'diorite', 'granite', 'coal_ore', 'deepslate_coal_ore', 'iron_ore', 'deepslate_iron_ore', 'copper_ore', 'deepslate_copper_ore'].includes(block.name)) {
    return await equipBestPickaxe()
  }

  if (['dirt', 'grass_block', 'sand', 'gravel', 'snow', 'snow_block', 'moss_block'].includes(block.name)) {
    return await equipBestAvailableTool(SHOVEL_PRIORITY)
  }

  return null
}

async function equipBestAvailableTool(priority) {
  const tool = firstInventoryItemByNames(priority)
  if (!tool) {
    return null
  }

  await withTimeout(bot.equip(tool, 'hand'), 5000, `equipping ${tool.name}`)
  return tool
}

async function craftPlanks(requestedCount) {
  const targetCrafts = requestedCount === undefined ? 4 : requestedCount
  let remainingCrafts = targetCrafts
  let completedCrafts = 0
  const startingPlanks = countPlanksInInventory()

  while (remainingCrafts > 0) {
    const logItem = firstInventoryItemByNames(Object.keys(LOG_TO_PLANK))
    if (!logItem) {
      break
    }

    const plankName = LOG_TO_PLANK[logItem.name]
    const plankType = itemType(plankName)
    if (!plankType) {
      return fail('craft_planks', `This Minecraft version does not know item ${plankName}.`)
    }

    const craftCount = Math.min(remainingCrafts, countItemInInventory(logItem.name))
    const recipe = bot.recipesFor(plankType.id, null, 4, null)[0]
    if (!recipe) {
      return fail('craft_planks', `No safe inventory recipe found for ${plankName}.`)
    }

    try {
      await craftWithTimeout(recipe, craftCount, null)
    } catch (error) {
      return fail('craft_planks', `Crafting failed: ${errorMessage(error)}`)
    }
    completedCrafts += craftCount
    remainingCrafts -= craftCount
  }

  const craftedPlanks = Math.max(0, countPlanksInInventory() - startingPlanks)

  if (completedCrafts === 0) {
    return fail('craft_planks', 'Missing materials: no logs or stems found in inventory.')
  }

  return ok('craft_planks', {
    crafts: completedCrafts,
    requestedCrafts: targetCrafts,
    craftedPlanks,
    inventory: inventoryJson()
  })
}

async function craftSticks(requestedCount) {
  const craftCount = requestedCount === undefined ? 1 : requestedCount
  const availablePlanks = countPlanksInInventory()
  const requiredPlanks = craftCount * 2

  if (availablePlanks < requiredPlanks) {
    return fail('craft_sticks', `Missing materials: need ${requiredPlanks} planks, have ${availablePlanks}.`)
  }

  const stickType = itemType('stick')
  if (!stickType) {
    return fail('craft_sticks', 'This Minecraft version does not know item stick.')
  }

  const recipe = bot.recipesFor(stickType.id, null, craftCount * 4, null)[0]
  if (!recipe) {
    return fail('craft_sticks', 'No safe inventory recipe found for sticks.')
  }

  try {
    await craftWithTimeout(recipe, craftCount, null)
  } catch (error) {
    return fail('craft_sticks', `Crafting failed: ${errorMessage(error)}`)
  }

  return ok('craft_sticks', {
    crafts: craftCount,
    craftedSticks: craftCount * 4,
    inventory: inventoryJson()
  })
}

async function craftCraftingTable(requestedCount) {
  const craftCount = requestedCount === undefined ? 1 : requestedCount
  const availablePlanks = countPlanksInInventory()
  const requiredPlanks = craftCount * 4

  if (availablePlanks < requiredPlanks) {
    return fail('craft_crafting_table', `Missing materials: need ${requiredPlanks} planks, have ${availablePlanks}.`)
  }

  const craftingTableType = itemType('crafting_table')
  if (!craftingTableType) {
    return fail('craft_crafting_table', 'This Minecraft version does not know item crafting_table.')
  }

  const recipe = bot.recipesFor(craftingTableType.id, null, craftCount, null)[0]
  if (!recipe) {
    return fail('craft_crafting_table', 'No safe inventory recipe found for crafting_table.')
  }

  try {
    await craftWithTimeout(recipe, craftCount, null)
  } catch (error) {
    return fail('craft_crafting_table', `Crafting failed: ${errorMessage(error)}`)
  }

  return ok('craft_crafting_table', {
    crafts: craftCount,
    craftedCraftingTables: craftCount,
    inventory: inventoryJson()
  })
}

async function placeCraftingTable() {
  return await placeStationRobust('place_crafting_table', 'crafting_table', ['crafting_table'], findNearbyCraftingTable)
}

// place_block — generic solid-block placement from the allowlist.
async function placeBlock(args) {
  const itemName = String(args.item || '')
  const mode = args.mode || 'nearby'

  if (itemName === 'water_bucket' || itemName === 'lava_bucket') {
    return fail('place_block', 'Use place_water or place_lava for liquid bucket placement.')
  }
  if (!isAllowedPlaceItem(itemName)) {
    return fail('place_block', `Item '${itemName}' is not allowed for placement.`)
  }

  const item = findPlaceableItem(itemName)
  return await placeItemSafely(itemName, {
    action: 'place_block',
    item,
    mode,
    direction: args.direction,
    verifyBlockNames: blockNamesForItem(itemName),
    requireOpenArea: mode !== 'wall',
    avoidEntities: true,
    avoidWater: false,
    avoidLava: true,
  })
}

// place_water — place water from a water_bucket.
async function placeWater(mode) {
  const safeMode = mode || 'nearby'

  if (safeMode === 'mlg') {
    return fail('place_water', 'MLG water requires mlg_water_bucket action.',
      { suggested_next_action: 'mlg_water_bucket' })
  }
  if (!WATER_MODES.has(safeMode)) {
    return fail('place_water', `Unknown mode '${safeMode}'. Valid: ${[...WATER_MODES].join(', ')}.`)
  }

  const waterItem = firstInventoryItemByNames(['water_bucket'])
  return await placeItemSafely('water_bucket', {
    action: 'place_water',
    item: waterItem,
    verifyBlockNames: ['water'],
    placementKind: 'liquid',
    mode: safeMode,
    allowLiquid: true,
    requireOpenArea: false,
    avoidWater: false,
    avoidLava: true,
    minHeadroom: 1,
    minBotDistance: safeMode === 'downward_safety' ? 1 : 0,
    radius: 4.5,
  })
}

// place_lava — high-risk lava placement restricted to safe modes only.
async function placeLava(mode) {
  const safeMode = mode || 'controlled_source'

  if (!LAVA_SAFE_MODES.has(safeMode)) {
    return fail('place_lava', `Mode '${safeMode}' is not allowed. Valid: ${[...LAVA_SAFE_MODES].join(', ')}.`)
  }

  const lavaItem = firstInventoryItemByNames(['lava_bucket'])
  return await placeItemSafely('lava_bucket', {
    action: 'place_lava',
    item: lavaItem,
    verifyBlockNames: ['lava'],
    placementKind: 'liquid',
    mode: safeMode,
    allowLiquid: true,
    requireOpenArea: false,
    avoidWater: false,
    avoidLava: true,
    minHeadroom: 1,
    minBotDistance: LAVA_MIN_SAFE_DISTANCE,
    radius: 4.5,
    customCandidateFilter: ({ targetPosition }) => isLavaPlacementSafe(targetPosition),
  })
}

// place_bed — place a bed with 2-block footprint check; warns if not in Overworld.
async function placeBed() {
  const bedItem = firstInventoryItemByNames(Array.from(BED_ITEM_NAMES))
  return await placeItemSafely(bedItem ? bedItem.name : 'bed', {
    action: 'place_bed',
    item: bedItem,
    verifyBlockNames: Array.from(BED_ITEM_NAMES),
    placementKind: 'bed',
    requireOpenArea: true,
    avoidEntities: true,
    avoidWater: true,
    avoidLava: true,
  })
}

/*
async function legacyPlaceBedLoopDisabled() {
  for (const candidate of []) {
    const freshRef  = bot.blockAt(candidate.referenceBlock.position)
    if (!isSolidBlock(freshRef)) continue
    if (!canReplaceBlock(bot.blockAt(candidate.placePosition))) continue
    if (!canReplaceBlock(bot.blockAt(candidate.placePosition.plus(candidate.headDirection)))) continue

    stopMovement()
    await delay(50)

    try {
      // Orient the bot toward the head block so the server places the bed correctly.
      const lookTarget = candidate.placePosition.plus(candidate.headDirection).offset(0.5, 0.5, 0.5)
      await bot.lookAt(lookTarget, true)
      await delay(80)
      await bot.equip(bedItem, 'hand')
      await placeBlockWithTimeout(freshRef, candidate.faceVector, PLACE_TIMEOUT_MS)
    } catch (_error) {
      // may have placed despite error
    }

    const verified = await waitForBlockAt(candidate.placePosition, Array.from(BED_ITEM_NAMES), PLACE_VERIFY_MS)
    if (verified) {
      const dimension = getBotDimension()
      const notOverworld = dimension && !dimension.includes('overworld')
      const result = { placed: true, position: positionJson(candidate.placePosition), bedItem: bedItem.name, inventory: inventoryJson() }
      if (notOverworld) {
        result.warning = `Bed placed in dimension '${dimension}'. Using/sleeping will cause explosion — only use for bed_bomb.`
      }
      return ok('place_bed', result)
    }
  }

  return fail('place_bed', 'Bed placement failed. All candidates exhausted.')
}

// place_boat — place a boat on a nearby water surface.
*/
async function placeBoat() {
  const boatItem = firstInventoryItemByNames(Array.from(BOAT_ITEM_NAMES))
  return await placeItemSafely(boatItem ? boatItem.name : 'boat', {
    action: 'place_boat',
    item: boatItem,
    placementKind: 'boat',
    requireOpenArea: false,
    avoidWater: false,
    avoidLava: true,
  })
}

  /*
    try {
    } catch (_error) {
      // Boats become entities — skip block verification
    }

    // Boats are entities, not blocks — check for a new nearby boat entity.
    await delay(350)
    const boatEntity = Object.values(bot.entities || {}).find(e =>
      e && e !== bot.entity && e.name && e.name.includes('boat') &&
      e.position && bot.entity && e.position.distanceTo(bot.entity.position) < 6
    )

    if (boatEntity) {
      return ok('place_boat', {
        placed: true,
        boatType: boatItem.name,
        position: positionJson(boatEntity.position),
        inventory: inventoryJson()
      })
    }
  }

  return fail('place_boat', 'Boat placement failed. No boat entity detected after placement attempt.')
}

// place_chest — delegate to generic placement.
*/
async function placeChest() {
  const item = firstInventoryItemByNames(['chest'])
  return await placeItemSafely('chest', {
    action: 'place_chest',
    item,
    verifyBlockNames: ['chest'],
    requireOpenArea: true,
    avoidEntities: true,
    avoidWater: true,
    avoidLava: true,
  })

}

// place_furnace — robust placement with expanded search and optional nuisance clearing.
async function placeFurnace(args = {}) {
  return await placeStationRobust('place_furnace', 'furnace', ['furnace'], findNearbyFurnace, args)
}

// place_torch — floor placement on the nearest valid solid surface.
async function placeTorch() {
  const item = firstInventoryItemByNames(['torch'])
  return await placeItemSafely('torch', {
    action: 'place_torch',
    item,
    verifyBlockNames: ['torch', 'wall_torch'],
    placementKind: 'torch',
    requireOpenArea: false,
    avoidEntities: false,
    avoidWater: false,
    avoidLava: true,
    minHeadroom: 1,
  })

}

async function craftItem(itemName, requestedCount) {
  const item = String(itemName || '').trim()
  if (!CRAFT_ITEM_ALLOWED_ITEMS.has(item)) {
    return fail('craft_item', `Craft item is not allowed: ${item}.`)
  }
  if (item === 'iron_armor') {
    return await craftIronArmor()
  }

  const count = CRAFT_ITEM_SINGLE_COUNT.has(item)
    ? 1
    : Math.max(1, Math.min(requestedCount === undefined ? 1 : requestedCount, CRAFT_MAX_COUNT))
  return await craftAllowedItem('craft_item', item, count)
}

async function craftFurnace() {
  return await craftAllowedItem('craft_furnace', 'furnace', 1)
}

async function craftTorches(requestedCount) {
  const count = Math.max(1, Math.min(requestedCount === undefined ? 4 : requestedCount, CRAFT_MAX_COUNT))
  return await craftAllowedItem('craft_torches', 'torch', count)
}

async function craftChest() {
  return await craftAllowedItem('craft_chest', 'chest', 1)
}

async function craftShield() {
  return await craftAllowedItem('craft_shield', 'shield', 1)
}

async function craftBucket() {
  return await craftAllowedItem('craft_bucket', 'bucket', 1)
}

async function craftIronPickaxe() {
  return await craftAllowedItem('craft_iron_pickaxe', 'iron_pickaxe', 1)
}

async function craftIronSword() {
  return await craftAllowedItem('craft_iron_sword', 'iron_sword', 1)
}

async function craftAllowedItem(action, itemName, desiredOutputCount) {
  const spec = CRAFT_ITEM_REQUIREMENTS[itemName]
  if (!spec) return fail(action, `Craft item is not allowed: ${itemName}.`)

  const outputCount = CRAFT_ITEM_OUTPUT_COUNTS[itemName] || 1
  const craftIterations = Math.max(1, Math.ceil(desiredOutputCount / outputCount))
  const missing = missingCraftMaterials(spec, craftIterations)
  if (missing.length > 0) {
    return fail(action, `Missing materials: ${formatMissingMaterials(missing)}.`, {
      missing_materials: missing,
      inventory: inventoryJson()
    })
  }

  let craftingTable = null
  if (spec.table) {
    craftingTable = findNearbyCraftingTable(STATION_USE_RADIUS)
    if (!craftingTable) {
      return noCraftingTableFail(action)
    }
  }

  const type = itemType(itemName)
  if (!type) return fail(action, `This Minecraft version does not know item ${itemName}.`)

  const recipe = bot.recipesFor(type.id, null, desiredOutputCount, craftingTable)[0]
    || bot.recipesFor(type.id, null, 1, craftingTable)[0]
  if (!recipe) {
    return fail(action, `No ${craftingTable ? 'crafting-table' : 'inventory'} recipe found for ${itemName}.`)
  }

  const before = countItemInInventory(itemName)
  try {
    await craftWithTimeout(recipe, craftIterations, craftingTable)
  } catch (error) {
    return fail(action, `Crafting failed: ${errorMessage(error)}`, { inventory: inventoryJson() })
  }

  const produced = Math.max(0, countItemInInventory(itemName) - before)
  return ok(action, {
    item: itemName,
    requested: desiredOutputCount,
    crafts: craftIterations,
    produced,
    craftingTable: blockJson(craftingTable),
    inventory: inventoryJson()
  })
}

async function craftIronArmor() {
  const craftingTable = findNearbyCraftingTable(STATION_USE_RADIUS)
  if (!craftingTable) {
    return noCraftingTableFail('craft_iron_armor')
  }

  const crafted = []
  const equipped = []
  const skipped = []
  const errors = []

  for (const piece of IRON_ARMOR_PIECES) {
    const available = countItemInInventory('iron_ingot')
    if (available < piece.ingots) {
      skipped.push({ name: piece.name, need: piece.ingots, have: available })
      continue
    }

    const type = itemType(piece.name)
    if (!type) {
      skipped.push({ name: piece.name, reason: 'unknown_item' })
      continue
    }

    const recipe = bot.recipesFor(type.id, null, 1, craftingTable)[0]
    if (!recipe) {
      skipped.push({ name: piece.name, reason: 'no_recipe' })
      continue
    }

    try {
      await craftWithTimeout(recipe, 1, craftingTable)
      crafted.push(piece.name)
      const armorItem = firstInventoryItemByNames([piece.name])
      if (armorItem) {
        await withTimeout(bot.equip(armorItem, piece.slot), EQUIP_TIMEOUT_MS, `equipping ${piece.name}`)
        equipped.push({ name: piece.name, slot: piece.slot })
      }
    } catch (error) {
      errors.push({ name: piece.name, error: errorMessage(error) })
    }
  }

  if (crafted.length === 0) {
    return fail('craft_iron_armor', 'Missing materials: need at least 4 iron_ingot for boots, or more for higher-priority armor pieces.', {
      missing_materials: [{ name: 'iron_ingot', need: 4, have: countItemInInventory('iron_ingot') }],
      skipped,
      inventory: inventoryJson()
    })
  }

  return ok('craft_iron_armor', { crafted, equipped, skipped, errors, inventory: inventoryJson() })
}

async function craftWoodenPickaxe() {
  const craftingTable = findNearbyCraftingTable(STATION_USE_RADIUS)
  if (!craftingTable) {
    return noCraftingTableFail('craft_wooden_pickaxe')
  }

  const availablePlanks = countPlanksInInventory()
  const availableSticks = countItemInInventory('stick')

  if (availablePlanks < 3) {
    return fail('craft_wooden_pickaxe', `Missing materials: need 3 planks, have ${availablePlanks}.`)
  }

  if (availableSticks < 2) {
    return fail('craft_wooden_pickaxe', `Missing materials: need 2 sticks, have ${availableSticks}.`)
  }

  const pickaxeType = itemType('wooden_pickaxe')
  if (!pickaxeType) {
    return fail('craft_wooden_pickaxe', 'This Minecraft version does not know item wooden_pickaxe.')
  }

  const recipe = bot.recipesFor(pickaxeType.id, null, 1, craftingTable)[0]
  if (!recipe) {
    return fail('craft_wooden_pickaxe', 'No crafting-table recipe found for wooden_pickaxe.')
  }

  try {
    await craftWithTimeout(recipe, 1, craftingTable)
  } catch (error) {
    return fail('craft_wooden_pickaxe', `Crafting failed: ${errorMessage(error)}`)
  }

  return ok('craft_wooden_pickaxe', {
    crafts: 1,
    craftingTable: blockJson(craftingTable),
    inventory: inventoryJson()
  })
}

async function mineStone(requestedCount) {
  const targetCount = requestedCount === undefined ? MINE_STONE_DEFAULT_COUNT : requestedCount
  if (!hasPickaxe()) {
    return fail('mine_stone', 'Missing tool: wooden_pickaxe or better is required.')
  }

  return await acquireBlocksForAction('mine_stone', {
    targets: ['stone'],
    count: targetCount,
    radius: ACQUIRE_BLOCKS_DEFAULT_RADIUS,
    allowExcavate: true,
    accessMode: 'safe_staircase'
  })
}

async function mineCoal(args) {
  const argsObj = args && typeof args === 'object' ? args : {}
  const targetCount = argsObj.count !== undefined ? argsObj.count : MINE_COAL_DEFAULT_COUNT
  const radius = argsObj.radius !== undefined ? argsObj.radius : ACQUIRE_BLOCKS_DEFAULT_RADIUS
  const accessMode = argsObj.accessMode !== undefined ? argsObj.accessMode : 'safe_staircase'
  const allowExcavate = argsObj.allowExcavate !== undefined ? argsObj.allowExcavate : true
  const coalTargets = ['coal_ore', 'deepslate_coal_ore']
  const coalTargetSet = new Set(coalTargets)

  if (!hasPickaxe()) {
    return fail('mine_coal', 'Missing tool: wooden_pickaxe or better is required.')
  }

  const inventoryBefore = inventoryCounts()
  const nearbyBefore = nearbyBlockCountsJson(Math.min(radius, 32), 64)
  const positionBefore = bot.entity ? { x: bot.entity.position.x, y: bot.entity.position.y, z: bot.entity.position.z } : null
  const coalBefore = inventoryCountForTargets(coalTargets)

  const visibleFloorDrops = bot.entity
    ? droppedItemEntitiesNear(bot.entity.position, Math.min(radius, DROP_COLLECTION_RADIUS))
    : []
  if (visibleFloorDrops.length > 0) {
    const floorDropDiagnostics = emptyAcquireResult({ targets: coalTargets, count: targetCount }, 'floor_drop')
    floorDropDiagnostics.inventoryBefore = inventoryBefore
    floorDropDiagnostics.currentSubstep = 'collect_floor_coal_drop'
    floorDropDiagnostics.floorDropCollectionAttempted = true
    const dropResult = await collectNearbyDrops({
      aroundPosition: bot.entity.position,
      targets: coalTargets,
      radius: Math.min(radius, DROP_COLLECTION_RADIUS),
      timeoutMs: Math.min(5000, DROP_COLLECTION_TIMEOUT_MS)
    }, floorDropDiagnostics)
    const coalAfterDrop = inventoryCountForTargets(coalTargets)
    const coalDelta = Math.max(0, coalAfterDrop - coalBefore)
    if (dropResult.collected > 0 || coalDelta > 0) {
      updateResourceInventoryDiagnostics(floorDropDiagnostics, coalTargets, inventoryBefore, targetCount)
      floorDropDiagnostics.dropCollectionSucceeded = true
      floorDropDiagnostics.bot_position = bot.entity ? positionJson(bot.entity.position) : null
      floorDropDiagnostics.allowExcavate = allowExcavate
      floorDropDiagnostics.accessMode = accessMode
      return resourceSuccessFromInventory('mine_coal', floorDropDiagnostics, 'collected_floor_drop') || ok('mine_coal', floorDropDiagnostics)
    }
  }

  // Quick pre-scan to understand burial state before committing to excavation.
  const preScanDiag = emptyAcquireResult({ targets: coalTargets, count: 0 }, 'scan')
  const preCandidates = await findTargetCandidates(coalTargetSet, Math.min(radius, MAX_SCAN_RADIUS), preScanDiag)
  const preExposedCount = preCandidates.filter(
    (b) => hasExposedFace(b) && !isDangerousAdjacent(b) && !isProtectedBlock(b)
  ).length
  const preTotalFound = preScanDiag.targetCandidatesFound
  const preNearestDist = preScanDiag.nearestTargetDistance
  const preNearestPos = preScanDiag.nearestTargetPosition

  const result = await acquireBlocksForAction('mine_coal', {
    targets: coalTargets,
    count: targetCount,
    radius,
    allowExcavate,
    accessMode
  })

  if (result.result) {
    const r = result.result
    const positionAfter = bot.entity ? positionJson(bot.entity.position) : null

    r.bot_position = positionAfter
    r.inventoryBefore = inventoryBefore
    updateResourceInventoryDiagnostics(r, coalTargets, inventoryBefore, targetCount)
    r.allowExcavate = allowExcavate
    r.accessMode = accessMode

    const successResponse = resourceSuccessFromInventory('mine_coal', r, r.drop_collection_reason)
    if (successResponse) return successResponse

    if (!result.ok) {
      const isTimeout = r.failure_type === 'action_timeout'

      // partial_progress_timeout: timed out but inventory gained or position changed > 2 blocks.
      if (isTimeout) {
        const hasInvGain = Object.values(r.inventory_delta || {}).some((v) => v > 0)
        let posDist = 0
        if (positionBefore && positionAfter) {
          const dx = (positionAfter.x || 0) - positionBefore.x
          const dy = (positionAfter.y || 0) - positionBefore.y
          const dz = (positionAfter.z || 0) - positionBefore.z
          posDist = Math.sqrt(dx * dx + dy * dy + dz * dz)
        }
        if (hasInvGain || posDist > 2) {
          r.failure_type = 'partial_progress_timeout'
          r.partial_success = true
        }
      }

      // resource_buried: candidates found pre-scan but none exposed (and not a timeout).
      if (!isTimeout && preTotalFound > 0 && preExposedCount === 0) {
        r.failure_type = 'resource_buried'
        r.failed_because = [{
          kind: 'resource_target_buried',
          block: 'coal_ore',
          candidates_found: preTotalFound,
          nearest_distance: preNearestDist,
          nearest_position: preNearestPos,
          exposed_faces: 0,
          safe_stand_candidate: false
        }]
      }

      // scan_mismatch: no candidates in range but nearbyBlockCounts sees coal.
      if (r.targetCandidatesFound === 0 && preTotalFound === 0 && !r.failure_type) {
        const nearbyCoal = (nearbyBefore['coal_ore'] || 0) + (nearbyBefore['deepslate_coal_ore'] || 0)
        if (nearbyCoal > 0) {
          r.failure_type = 'scan_mismatch'
          r.scan_mismatch_detail = {
            nearby_coal_ore: nearbyBefore['coal_ore'] || 0,
            nearby_deepslate_coal_ore: nearbyBefore['deepslate_coal_ore'] || 0
          }
        } else {
          r.failure_type = 'target_not_found'
        }
      }

      // resource_candidates_rejected: candidates found but none accessible (fallback).
      if (r.targetCandidatesFound > 0 && r.accessCandidatesFound === 0 && !r.failure_type) {
        r.failure_type = 'resource_candidates_rejected'
      }

      // Enrich navigation_failed with nearest target distance.
      if (r.failure_type === 'navigation_failed' && r.nearestTargetDistance !== null) {
        const fb = Array.isArray(r.failed_because) ? r.failed_because : []
        if (!fb.some((e) => typeof e === 'object' && e !== null && e.kind === 'path_timeout')) {
          fb.push({
            kind: 'path_timeout',
            nearestTargetDistance: r.nearestTargetDistance,
            nearestTargetPosition: r.nearestTargetPosition
          })
          r.failed_because = fb
        }
      }
    }
  }

  return result
}

async function debugFindBlocks(targets, radius) {
  const targetList = Array.isArray(targets) ? targets.filter((t) => typeof t === 'string' && t.length > 0) : []
  const searchRadius = typeof radius === 'number' && radius > 0 ? Math.min(radius, MAX_SCAN_RADIUS) : ACQUIRE_BLOCKS_DEFAULT_RADIUS
  const targetSet = new Set(targetList)
  const botPos = bot.entity ? bot.entity.position : null

  if (targetList.length === 0) {
    return fail('debug_find_blocks', 'No targets specified.')
  }

  const matching = targetList
    .map((name) => bot.registry.blocksByName[name])
    .filter((blockType) => blockType)
    .map((blockType) => blockType.id)

  const positions = matching.length > 0
    ? bot.findBlocks({ matching, maxDistance: searchRadius, count: 64 }) || []
    : []

  const blocks = positions
    .map((position) => bot.blockAt(position))
    .filter((block) => block && targetSet.has(block.name))
    .sort((a, b) => (botPos ? botPos.distanceTo(a.position) - botPos.distanceTo(b.position) : 0))

  const entries = []
  for (const block of blocks) {
    const distance = botPos ? Math.round(botPos.distanceTo(block.position) * 10) / 10 : null
    const exposed = hasExposedFace(block)
    const dangerous = isDangerousAdjacent(block)
    const protected_ = isProtectedBlock(block)
    let safeStandCandidate = false
    if (exposed && !dangerous && !protected_) {
      const faceInfo = findExposedFace(block)
      if (faceInfo) {
        const standPos = findSafeStandNearFace(block, faceInfo)
        safeStandCandidate = standPos !== null
      }
    }
    entries.push({
      name: block.name,
      position: positionJson(block.position),
      distance,
      exposedFaces: MINE_FACE_OFFSETS.filter((o) => {
        const n = bot.blockAt(block.position.plus(o))
        return n && canReplaceBlock(n)
      }).length,
      isProtected: protected_,
      isDangerous: dangerous,
      hasSafeStandCandidate: safeStandCandidate
    })
  }

  return ok('debug_find_blocks', {
    targets: targetList,
    radius: searchRadius,
    bot_position: botPos ? positionJson(botPos) : null,
    total_found: entries.length,
    blocks: entries
  })
}

async function debugCollectDrops(targetItems, radius) {
  const DEFAULT_TARGETS = ['coal', 'raw_iron', 'cobblestone', 'stone']
  const targets = Array.isArray(targetItems) && targetItems.length > 0
    ? targetItems.filter((t) => typeof t === 'string' && t.length > 0)
    : DEFAULT_TARGETS
  const searchRadius = typeof radius === 'number' && radius > 0 ? Math.min(radius, 32) : 8

  if (!bot.entity) return fail('debug_collect_drops', 'Bot not ready.')

  const diagnostics = emptyAcquireResult({ targets, count: 0 }, 'failed')
  diagnostics.minedTargetBlocks = 0
  diagnostics.inventoryBefore = inventoryCountForTargets(targets)

  const aroundPosition = bot.entity.position.clone()
  const collectResult = await collectNearbyDrops(
    { aroundPosition, targets, radius: searchRadius, timeoutMs: DROP_COLLECTION_TIMEOUT_MS },
    diagnostics
  )

  diagnostics.inventoryAfter = inventoryCountForTargets(targets)

  const collected = diagnostics.targetInventoryDelta || 0

  if (collectResult && (collectResult.reason === 'success' || collected > 0)) {
    return ok('debug_collect_drops', {
      ...diagnostics,
      collected,
      targets,
      radius: searchRadius,
      bot_position: positionJson(aroundPosition),
    })
  }

  return {
    ok: false,
    action: 'debug_collect_drops',
    result: {
      ...diagnostics,
      collected,
      targets,
      radius: searchRadius,
      bot_position: positionJson(aroundPosition),
      stop_reason: (collectResult && collectResult.reason) || 'drop_collection_timeout',
    },
    error: `debug_collect_drops: ${(collectResult && collectResult.reason) || 'drop_collection_timeout'}`,
  }
}

async function mineIronOre(requestedCount) {
  const targetCount = requestedCount === undefined ? MINE_IRON_DEFAULT_COUNT : requestedCount
  if (!hasPickaxeAtLeast('stone_pickaxe')) {
    return fail('mine_iron_ore', 'Missing tool: stone_pickaxe or better is required.')
  }

  const before = countItemInInventory('raw_iron')
  const result = await acquireBlocksForAction('mine_iron_ore', {
    targets: ['iron_ore', 'deepslate_iron_ore'],
    count: targetCount,
    radius: ACQUIRE_BLOCKS_DEFAULT_RADIUS,
    allowExcavate: true,
    accessMode: 'safe_staircase'
  })
  if (result.result) {
    result.result.raw_iron_count = countItemInInventory('raw_iron')
    result.result.raw_iron_gained = Math.max(0, result.result.raw_iron_count - before)
  }
  return result
}

async function smeltIron(requestedCount) {
  return await smeltItem('raw_iron', undefined, requestedCount === undefined ? SMELT_DEFAULT_COUNT : requestedCount, 'smelt_iron')
}

async function smeltItem(inputName, fuelName, requestedCount, action = 'smelt_item') {
  const input = String(inputName || '').trim()
  const output = SMELT_INPUTS[input]
  if (!output) return fail(action, `Smelt input is not allowed: ${input}.`)

  const furnaceBlock = findNearbyFurnace(STATION_USE_RADIUS)
  if (!furnaceBlock) {
    return noFurnaceFail(action)
  }

  const availableInput = countItemInInventory(input)
  const count = Math.max(1, Math.min(requestedCount === undefined ? 1 : requestedCount, SMELT_MAX_COUNT, availableInput))
  if (availableInput <= 0) {
    return fail(action, `Missing materials: need ${input}.`, {
      missing_materials: [{ name: input, need: 1, have: 0 }],
      inventory: inventoryJson()
    })
  }

  const fuelItem = resolveSmeltFuel(fuelName)
  if (!fuelItem) {
    return fail(action, 'Missing materials: need fuel (coal or charcoal preferred; planks/logs allowed only if no coal is available).', {
      missing_materials: [{ name: 'fuel', need: 1, have: 0 }],
      inventory: inventoryJson()
    })
  }

  const inputType = itemType(input)
  if (!inputType) return fail(action, `This Minecraft version does not know item ${input}.`)

  const startedOutput = countItemInInventory(output)
  let furnace = null
  let smeltingStarted = false
  let produced = 0

  try {
    furnace = await withTimeout(bot.openFurnace(furnaceBlock), CONTAINER_TIMEOUT_MS, 'opening furnace')
    const fuelCount = Math.min(fuelItem.count, fuelItem.name === 'coal' || fuelItem.name === 'charcoal' ? Math.ceil(count / 8) : count)
    await withTimeout(furnace.putInput(inputType.id, null, count), CONTAINER_TIMEOUT_MS, `putting ${input}`)
    await withTimeout(furnace.putFuel(fuelItem.type, null, Math.max(1, fuelCount)), CONTAINER_TIMEOUT_MS, `putting ${fuelItem.name}`)
    smeltingStarted = true

    const deadline = Date.now() + 5000 + (count * SMELT_TIMEOUT_PER_ITEM_MS)
    while (Date.now() < deadline) {
      const outputItem = typeof furnace.outputItem === 'function' ? furnace.outputItem() : null
      if (outputItem) {
        await withTimeout(furnace.takeOutput(), CONTAINER_TIMEOUT_MS, 'taking furnace output')
        produced = Math.max(0, countItemInInventory(output) - startedOutput)
        if (produced >= count) break
      }
      await delay(1000)
    }

    const finalOutput = typeof furnace.outputItem === 'function' ? furnace.outputItem() : null
    if (finalOutput) {
      try {
        await withTimeout(furnace.takeOutput(), CONTAINER_TIMEOUT_MS, 'taking furnace output')
      } catch (_) {}
    }
  } catch (error) {
    if (furnace) {
      try { furnace.close() } catch (_) {}
    }
    produced = Math.max(0, countItemInInventory(output) - startedOutput)
    if (smeltingStarted || produced > 0) {
      return fail(action, `Smelting started but did not complete: ${errorMessage(error)}`, {
        input,
        output,
        requested: count,
        produced,
        partial_success: true,
        can_retry: true,
        stop_reason: 'smelt_interrupted',
        inventory: inventoryJson()
      })
    }
    return fail(action, `Smelting failed: ${errorMessage(error)}`, { inventory: inventoryJson() })
  } finally {
    if (furnace) {
      try { furnace.close() } catch (_) {}
    }
  }

  produced = Math.max(0, countItemInInventory(output) - startedOutput)
  const result = {
    input,
    output,
    fuel: fuelItem.name,
    requested: count,
    produced,
    position: positionJson(furnaceBlock.position),
    inventory: inventoryJson()
  }

  if (produced < count) {
    return {
      ok: produced > 0,
      action,
      result: {
        ...result,
        partial_success: smeltingStarted || produced > 0,
        can_retry: true,
        stop_reason: 'smelt_timeout'
      },
      error: produced > 0 ? null : 'Smelting timed out before output was produced.'
    }
  }

  return ok(action, result)
}

async function craftStonePickaxe() {
  const craftingTable = findNearbyCraftingTable(STATION_USE_RADIUS)
  if (!craftingTable) {
    return noCraftingTableFail('craft_stone_pickaxe')
  }

  const availableCobblestone = countItemInInventory('cobblestone')
  const availableSticks = countItemInInventory('stick')

  if (availableCobblestone < 3) {
    return fail('craft_stone_pickaxe', `Missing materials: need 3 cobblestone, have ${availableCobblestone}.`)
  }

  if (availableSticks < 2) {
    return fail('craft_stone_pickaxe', `Missing materials: need 2 sticks, have ${availableSticks}.`)
  }

  const pickaxeType = itemType('stone_pickaxe')
  if (!pickaxeType) {
    return fail('craft_stone_pickaxe', 'This Minecraft version does not know item stone_pickaxe.')
  }

  const recipe = bot.recipesFor(pickaxeType.id, null, 1, craftingTable)[0]
  if (!recipe) {
    return fail('craft_stone_pickaxe', 'No crafting-table recipe found for stone_pickaxe.')
  }

  try {
    await craftWithTimeout(recipe, 1, craftingTable)
  } catch (error) {
    return fail('craft_stone_pickaxe', `Crafting failed: ${errorMessage(error)}`)
  }

  return ok('craft_stone_pickaxe', {
    crafts: 1,
    craftingTable: blockJson(craftingTable),
    inventory: inventoryJson()
  })
}

// craft_blaze_powder: 1 blaze_rod → 2 blaze_powder (inventory crafting, no table needed)
async function craftBlazePowder() {
  const available = countItemInInventory('blaze_rod')
  if (available < 1) {
    return fail('craft_blaze_powder', 'Missing materials: need at least 1 blaze_rod, have 0.')
  }

  const powderType = itemType('blaze_powder')
  if (!powderType) {
    return fail('craft_blaze_powder', 'This Minecraft version does not know item blaze_powder.')
  }

  const recipe = bot.recipesFor(powderType.id, null, 2, null)[0]
  if (!recipe) {
    return fail('craft_blaze_powder', 'No inventory recipe found for blaze_powder.')
  }

  const startPowder = countItemInInventory('blaze_powder')
  try {
    await craftWithTimeout(recipe, available, null)
  } catch (error) {
    return fail('craft_blaze_powder', `Crafting failed: ${errorMessage(error)}`)
  }

  const produced = Math.max(0, countItemInInventory('blaze_powder') - startPowder)
  return ok('craft_blaze_powder', { crafts: available, produced, inventory: inventoryJson() })
}

// craft_diamond_pickaxe: 3 diamonds + 2 sticks, requires crafting table
async function craftDiamondPickaxe() {
  const craftingTable = findNearbyCraftingTable(STATION_USE_RADIUS)
  if (!craftingTable) {
    return noCraftingTableFail('craft_diamond_pickaxe')
  }

  const availableDiamonds = countItemInInventory('diamond')
  const availableSticks = countItemInInventory('stick')
  const missing = []
  if (availableDiamonds < 3) missing.push(`diamond x${3 - availableDiamonds}`)
  if (availableSticks < 2)   missing.push(`stick x${2 - availableSticks}`)
  if (missing.length > 0) {
    return fail('craft_diamond_pickaxe', `Missing materials: ${missing.join(', ')}.`)
  }

  const pickaxeType = itemType('diamond_pickaxe')
  if (!pickaxeType) {
    return fail('craft_diamond_pickaxe', 'This Minecraft version does not know item diamond_pickaxe.')
  }

  const recipe = bot.recipesFor(pickaxeType.id, null, 1, craftingTable)[0]
  if (!recipe) {
    return fail('craft_diamond_pickaxe', 'No crafting-table recipe found for diamond_pickaxe.')
  }

  try {
    await craftWithTimeout(recipe, 1, craftingTable)
  } catch (error) {
    return fail('craft_diamond_pickaxe', `Crafting failed: ${errorMessage(error)}`)
  }

  return ok('craft_diamond_pickaxe', { crafts: 1, craftingTable: blockJson(craftingTable), inventory: inventoryJson() })
}

// craft_diamond_sword: 2 diamonds + 1 stick, requires crafting table
async function craftDiamondSword() {
  const craftingTable = findNearbyCraftingTable(STATION_USE_RADIUS)
  if (!craftingTable) {
    return noCraftingTableFail('craft_diamond_sword')
  }

  const availableDiamonds = countItemInInventory('diamond')
  const availableSticks = countItemInInventory('stick')
  const missing = []
  if (availableDiamonds < 2) missing.push(`diamond x${2 - availableDiamonds}`)
  if (availableSticks < 1)   missing.push('stick x1')
  if (missing.length > 0) {
    return fail('craft_diamond_sword', `Missing materials: ${missing.join(', ')}.`)
  }

  const swordType = itemType('diamond_sword')
  if (!swordType) {
    return fail('craft_diamond_sword', 'This Minecraft version does not know item diamond_sword.')
  }

  const recipe = bot.recipesFor(swordType.id, null, 1, craftingTable)[0]
  if (!recipe) {
    return fail('craft_diamond_sword', 'No crafting-table recipe found for diamond_sword.')
  }

  try {
    await craftWithTimeout(recipe, 1, craftingTable)
  } catch (error) {
    return fail('craft_diamond_sword', `Crafting failed: ${errorMessage(error)}`)
  }

  return ok('craft_diamond_sword', { crafts: 1, craftingTable: blockJson(craftingTable), inventory: inventoryJson() })
}

// craft_diamond_armor: craft pieces in priority order (chestplate→leggings→helmet→boots)
// Each piece uses as many diamonds as available. Equips each piece after crafting.
async function craftDiamondArmor() {
  const craftingTable = findNearbyCraftingTable(STATION_USE_RADIUS)
  if (!craftingTable) {
    return noCraftingTableFail('craft_diamond_armor')
  }

  const crafted = []
  const skipped = []
  const errors = []

  for (const piece of DIAMOND_ARMOR_PIECES) {
    const available = countItemInInventory('diamond')
    if (available < piece.diamonds) {
      skipped.push({ name: piece.name, need: piece.diamonds, have: available })
      continue
    }

    const armorType = itemType(piece.name)
    if (!armorType) {
      skipped.push({ name: piece.name, reason: 'unknown_item' })
      continue
    }

    const recipe = bot.recipesFor(armorType.id, null, 1, craftingTable)[0]
    if (!recipe) {
      skipped.push({ name: piece.name, reason: 'no_recipe' })
      continue
    }

    try {
      await craftWithTimeout(recipe, 1, craftingTable)
      crafted.push(piece.name)
      // Equip the freshly crafted piece immediately
      const armorItem = firstInventoryItemByNames([piece.name])
      if (armorItem) {
        await withTimeout(bot.equip(armorItem, piece.slot), EQUIP_TIMEOUT_MS, `equipping ${piece.name}`)
      }
    } catch (error) {
      errors.push({ name: piece.name, error: errorMessage(error) })
    }
  }

  if (crafted.length === 0) {
    const detail = skipped.length > 0
      ? `Need: ${skipped.map(s => `${s.name}(${s.need})`).join(', ')}.`
      : 'No diamond armor could be crafted.'
    return fail('craft_diamond_armor', detail)
  }

  return ok('craft_diamond_armor', { crafted, skipped, errors, inventory: inventoryJson() })
}

// equip_best_armor: equip best available piece per slot, prefer diamond > iron > gold > leather
async function equipBestArmor() {
  const equipped = []
  const skipped = []

  for (const [slot, priority] of Object.entries(ARMOR_PRIORITY_BY_SLOT)) {
    const piece = firstInventoryItemByNames(priority)
    if (!piece) {
      skipped.push(slot)
      continue
    }
    try {
      await withTimeout(bot.equip(piece, slot), EQUIP_TIMEOUT_MS, `equipping ${piece.name}`)
      equipped.push({ slot, name: piece.name })
    } catch (error) {
      skipped.push(slot)
    }
  }

  if (equipped.length === 0) {
    return fail('equip_best_armor', 'No armor found in inventory.')
  }

  return ok('equip_best_armor', { equipped, skipped })
}

// equip_best_tool: equip best tool, optionally matched to a target block name
async function equipBestTool(blockName) {
  // If a block name was given, match to the appropriate tool type
  if (blockName) {
    const name = String(blockName).toLowerCase()
    let tool = null
    if (WOOD_BLOCK_NAMES.has(name)) {
      tool = await equipBestAvailableTool(AXE_PRIORITY)
    } else if (['stone', 'cobblestone', 'deepslate', 'cobbled_deepslate', 'coal_ore',
                'deepslate_coal_ore', 'iron_ore', 'deepslate_iron_ore', 'copper_ore',
                'deepslate_copper_ore', 'gold_ore', 'deepslate_gold_ore', 'redstone_ore',
                'deepslate_redstone_ore', 'diamond_ore', 'deepslate_diamond_ore', 'obsidian'].includes(name)) {
      tool = await equipBestPickaxe().catch(() => null)
    } else if (['dirt', 'grass_block', 'sand', 'gravel', 'snow', 'snow_block'].includes(name)) {
      tool = await equipBestAvailableTool(SHOVEL_PRIORITY)
    } else {
      // Unknown block — fall back to best pickaxe
      tool = await equipBestPickaxe().catch(() => null)
    }

    if (!tool) {
      return fail('equip_best_tool', `No suitable tool found for block: ${blockName}.`)
    }
    return ok('equip_best_tool', { equipped: tool.name, block: blockName })
  }

  // No block specified — equip best overall tool (pickaxe priority)
  const pickaxe = await equipBestPickaxe().catch(() => null)
  if (pickaxe) {
    return ok('equip_best_tool', { equipped: pickaxe.name })
  }
  const axe = await equipBestAvailableTool(AXE_PRIORITY)
  if (axe) {
    return ok('equip_best_tool', { equipped: axe.name })
  }
  return fail('equip_best_tool', 'No usable tool found in inventory.')
}

// equip_best_weapon: equip best sword by tier, fall back to axe
async function equipBestWeapon() {
  const sword = firstInventoryItemByNames(SWORD_PRIORITY)
  if (sword) {
    await withTimeout(bot.equip(sword, 'hand'), EQUIP_TIMEOUT_MS, `equipping ${sword.name}`)
    return ok('equip_best_weapon', { equipped: sword.name, type: 'sword' })
  }

  const axe = firstInventoryItemByNames(AXE_PRIORITY)
  if (axe) {
    await withTimeout(bot.equip(axe, 'hand'), EQUIP_TIMEOUT_MS, `equipping ${axe.name}`)
    return ok('equip_best_weapon', { equipped: axe.name, type: 'axe' })
  }

  return fail('equip_best_weapon', 'No weapon found in inventory.')
}

function craftWithTimeout(recipe, count, craftingTable) {
  const timeoutMs = CRAFT_TIMEOUT_MS + (count * 2000)
  return withTimeout(bot.craft(recipe, count, craftingTable), timeoutMs, 'crafting')
}

function withTimeout(promise, ms, label) {
  let timeoutId = null
  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      if (String(label || '').toLowerCase().includes('path')) {
        stopMovement()
      }
      reject(new Error(`Timed out ${label} after ${ms}ms.`))
    }, ms)
  })

  return Promise.race([promise, timeout]).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
  })
}

async function yieldToEventLoop() {
  await new Promise((resolve) => setImmediate(resolve))
}

function gotoNearBlockWithTimeout(block, timeoutMs) {
  let timeoutId = null
  const goal = new goals.GoalNear(block.position.x, block.position.y, block.position.z, 2)
  lastPathGoal = { type: 'GoalNear', x: block.position.x, y: block.position.y, z: block.position.z, radius: 2, target: block.name }

  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      stopMovement()
      reject(new Error(`Timed out pathing near ${block.name} after ${timeoutMs}ms.`))
    }, timeoutMs)
  })

  return Promise.race([bot.pathfinder.goto(goal), timeout]).catch((err) => {
    if (isGoalChangedError(err)) lastPathCancelReason = 'path_goal_changed'
    throw err
  }).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
  })
}

function digBlockWithTimeout(block, timeoutMs) {
  let timeoutId = null

  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Timed out digging ${block.name} after ${timeoutMs}ms.`))
    }, timeoutMs)
  })

  return Promise.race([bot.dig(block), timeout]).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
  })
}

function gotoPositionWithTimeout(position, timeoutMs) {
  return gotoPositionNearWithTimeout(position, 2, timeoutMs)
}

function gotoPositionNearWithTimeout(position, radius, timeoutMs) {
  let timeoutId = null
  const goal = new goals.GoalNear(position.x, position.y, position.z, radius)
  lastPathGoal = { type: 'GoalNear', x: position.x, y: position.y, z: position.z, radius }

  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      stopMovement()
      reject(new Error(`Timed out pathing after ${timeoutMs}ms.`))
    }, timeoutMs)
  })

  return Promise.race([bot.pathfinder.goto(goal), timeout]).catch((err) => {
    if (isGoalChangedError(err)) lastPathCancelReason = 'path_goal_changed'
    throw err
  }).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
  })
}

function consumeWithTimeout(timeoutMs) {
  let timeoutId = null

  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Timed out eating after ${timeoutMs}ms.`))
    }, timeoutMs)
  })

  return Promise.race([bot.consume(), timeout]).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
  })
}

function placeBlockWithTimeout(referenceBlock, faceVector, timeoutMs) {
  let timeoutId = null

  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Timed out placing block after ${timeoutMs}ms.`))
    }, timeoutMs)
  })

  return Promise.race([bot.placeBlock(referenceBlock, faceVector), timeout]).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
  })
}

async function waitForCraftingTable(position, timeoutMs) {
  const started = Date.now()

  while (Date.now() - started <= timeoutMs) {
    const exact = bot.blockAt(position)
    if (exact && exact.name === 'crafting_table') {
      return true
    }

    const nearby = findNearbyCraftingTable(STATION_USE_RADIUS)
    if (nearby) {
      return true
    }

    await delay(100)
  }

  return false
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// ---------------------------------------------------------------------------
// Generic placement primitives
// ---------------------------------------------------------------------------

// Look-target for a placement: center of the clicked face on the reference block.
function faceCenter(refPos, faceVector) {
  return refPos.offset(
    0.5 + faceVector.x * 0.5,
    0.5 + faceVector.y * 0.5,
    0.5 + faceVector.z * 0.5
  )
}

// Wait until a block with one of the given names appears at position (or nearby).
async function waitForBlockAt(position, blockNames, timeoutMs) {
  const names = new Set(Array.isArray(blockNames) ? blockNames : [blockNames])
  const started = Date.now()

  while (Date.now() - started <= timeoutMs) {
    const exact = bot.blockAt(position)
    if (exact && names.has(exact.name)) return true

    // Proximity fallback for server race conditions
    const ids = [...names]
      .map(n => (bot.registry.blocksByName[n] ? bot.registry.blocksByName[n].id : null))
      .filter(id => id !== null)
    if (ids.length > 0) {
      const found = bot.findBlock({ matching: ids, maxDistance: 4 })
      if (found) return true
    }

    await delay(100)
  }
  return false
}

// Map an item name to the block name(s) we expect to appear after placement.
function blockNamesForItem(itemName) {
  if (itemName === 'water_bucket') return ['water']
  if (itemName === 'lava_bucket')  return ['lava']
  if (itemName === 'torch')        return ['torch', 'wall_torch']
  return [itemName]
}

// Find an inventory item supporting family matching (planks, beds, boats).
function findPlaceableItem(itemName) {
  if (itemName === 'planks') return firstInventoryItemByNames(Array.from(PLANK_ITEM_NAMES))
  if (itemName === 'bed')    return firstInventoryItemByNames(Array.from(BED_ITEM_NAMES))
  if (itemName === 'boat')   return firstInventoryItemByNames(Array.from(BOAT_ITEM_NAMES))
  return firstInventoryItemByNames([itemName])
}

// True if name is on the place_block allowlist (includes _planks / _bed suffix families).
function isAllowedPlaceItem(name) {
  if (!name || typeof name !== 'string') return false
  if (PLACE_BLOCK_ALLOWED_ITEMS.has(name)) return true
  if (name.endsWith('_planks')) return true
  if (name.endsWith('_bed'))    return true
  return false
}

// Generalized floor placement candidates — same geometry as findCraftingTableCandidates.
function placementDiagnostics() {
  return {
    rejectedNoFloor: 0,
    rejectedBlocked: 0,
    rejectedNoHeadroom: 0,
    rejectedLiquidNearby: 0,
    rejectedEntityCollision: 0,
    rejectedTooFar: 0,
    rejectedUnsafeFloor: 0,
    rejectedNoReference: 0,
    candidatesChecked: 0,
  }
}

function makePlacementFailure(action, reason, diagnostics = {}, overrides = {}) {
  const templates = {
    no_safe_workspace: {
      failure_type: 'no_safe_workspace',
      stop_reason: 'area_cramped',
      suggested_next_action: 'find_safe_workspace',
      fallback_suggested_next_action: 'return_to_surface',
      can_retry: true,
      needed: 'safe open area with solid floor and 2-block head clearance',
      error: 'No safe placement position found nearby.',
    },
    missing_item: {
      failure_type: 'missing_materials',
      stop_reason: 'missing_placeable_item',
      suggested_next_action: 'craft_or_acquire_item',
      fallback_suggested_next_action: 'status',
      can_retry: true,
      needed: 'placeable item in inventory',
      error: 'Missing materials: no placeable item in inventory.',
    },
    danger: {
      failure_type: 'danger_detected',
      stop_reason: 'unsafe_placement_area',
      suggested_next_action: 'avoid_hazard',
      fallback_suggested_next_action: 'find_safe_workspace',
      can_retry: true,
      needed: 'safe area away from liquid, lava, mobs, or edges',
      error: 'Placement area is unsafe.',
    },
    failed: {
      failure_type: 'no_safe_placement',
      stop_reason: 'placement_failed',
      suggested_next_action: 'find_safe_workspace',
      fallback_suggested_next_action: 'return_to_surface',
      can_retry: true,
      needed: 'valid reference block and clear target space',
      error: 'Placement failed after trying safe candidates.',
    },
  }

  const base = templates[reason] || templates.failed
  const result = {
    ...base,
    ...overrides,
    diagnostics: { ...diagnostics, ...(overrides.diagnostics || {}) },
  }
  const error = overrides.error || base.error
  delete result.error
  return fail(action, error, result)
}

function placementCandidateFailure(reason, diagnostics, overrides = {}) {
  const templates = {
    danger: {
      failure_type: 'danger_detected',
      stop_reason: 'unsafe_placement_area',
      suggested_next_action: 'avoid_hazard',
      fallback_suggested_next_action: 'find_safe_workspace',
      can_retry: true,
      needed: 'safe area away from hazards',
    },
    no_safe_workspace: {
      failure_type: 'no_safe_workspace',
      stop_reason: 'area_cramped',
      suggested_next_action: 'find_safe_workspace',
      fallback_suggested_next_action: 'return_to_surface',
      can_retry: true,
      needed: 'safe open area with solid floor and 2-block head clearance',
    },
  }
  return {
    ok: false,
    ...(templates[reason] || templates.no_safe_workspace),
    ...overrides,
    diagnostics,
  }
}

function normalizePlacementCandidate(candidate, placementKind, diagnostics) {
  if (!candidate) return null
  return {
    ok: true,
    referenceBlock: candidate.referenceBlock,
    faceVector: candidate.faceVector,
    targetPosition: candidate.targetPosition || candidate.placePosition,
    placementKind: candidate.placementKind || placementKind || 'floor',
    headDirection: candidate.headDirection || null,
    diagnostics,
  }
}

function placementHasUnsafeLiquidNearby(targetPosition, options = {}) {
  const avoidLava = options.avoidLava !== false
  const avoidWater = options.avoidWater === true
  if (!avoidLava && !avoidWater) return false

  for (const offset of MINE_FACE_OFFSETS) {
    const neighbor = bot.blockAt(targetPosition.plus(offset))
    if (!neighbor) continue
    if (avoidLava && neighbor.name && neighbor.name.includes('lava')) return true
    if (avoidWater && neighbor.name && neighbor.name.includes('water')) return true
  }
  return false
}

function placementIntersectsEntity(targetPosition, options = {}) {
  if (options.avoidEntities === false || !bot.entities) return false
  const center = targetPosition.offset(0.5, 0.5, 0.5)
  return Object.values(bot.entities).some((entity) => {
    if (!entity || entity === bot.entity || !entity.position) return false
    return entity.position.distanceTo(center) < 0.85
  })
}

function buildFloorPlacementCandidates(options, diagnostics) {
  if (!bot.entity) return []
  const base = bot.entity.position.floored()
  const faceUp = new Vec3(0, 1, 0)
  const radius = Math.min(6, Math.max(1, Number(options.radius || 4.5)))
  const minHeadroom = Math.max(1, Number(options.minHeadroom || 2))
  const requireOpenArea = options.requireOpenArea !== false
  const allowLiquid = options.allowLiquid === true
  const minBotDistance = Math.max(0, Number(options.minBotDistance || 0))

  const refOffsets = [
    new Vec3(2, -1, 0),  new Vec3(-2, -1, 0), new Vec3(0, -1, 2),  new Vec3(0, -1, -2),
    new Vec3(2, -1, 1),  new Vec3(2, -1, -1), new Vec3(-2, -1, 1), new Vec3(-2, -1, -1),
    new Vec3(1, -1, 2),  new Vec3(-1, -1, 2), new Vec3(1, -1, -2), new Vec3(-1, -1, -2),
    new Vec3(1, -1, 0),  new Vec3(-1, -1, 0), new Vec3(0, -1, 1),  new Vec3(0, -1, -1),
    new Vec3(1, 0, 0),   new Vec3(-1, 0, 0),  new Vec3(0, 0, 1),   new Vec3(0, 0, -1),
    new Vec3(0, -1, 0),
  ]

  const candidates = []
  for (const offset of refOffsets) {
    diagnostics.candidatesChecked++
    const refPos = base.plus(offset)
    const refBlock = bot.blockAt(refPos)
    if (!isSolidBlock(refBlock)) {
      diagnostics.rejectedNoReference++
      continue
    }

    const targetPosition = refPos.offset(0, 1, 0)
    const placeBlock = bot.blockAt(targetPosition)
    if (!canReplaceBlock(placeBlock)) {
      diagnostics.rejectedBlocked++
      continue
    }

    if (!allowLiquid && isLiquidBlock(placeBlock)) {
      diagnostics.rejectedLiquidNearby++
      continue
    }

    let headroomOk = true
    if (requireOpenArea) {
      for (let dy = 1; dy <= minHeadroom; dy++) {
        if (!canReplaceBlock(bot.blockAt(targetPosition.offset(0, dy, 0)))) {
          headroomOk = false
          break
        }
      }
    }
    if (!headroomOk) {
      diagnostics.rejectedNoHeadroom++
      continue
    }

    if (placementHasUnsafeLiquidNearby(targetPosition, options)) {
      diagnostics.rejectedLiquidNearby++
      continue
    }
    if (placementIntersectsBot(targetPosition) || placementIntersectsEntity(targetPosition, options)) {
      diagnostics.rejectedEntityCollision++
      continue
    }
    if (bot.entity.position.distanceTo(refPos.offset(0.5, 1.0, 0.5)) > radius) {
      diagnostics.rejectedTooFar++
      continue
    }
    if (minBotDistance > 0 && bot.entity.position.distanceTo(targetPosition) < minBotDistance) {
      diagnostics.rejectedTooFar++
      continue
    }
    if (typeof options.customCandidateFilter === 'function' && !options.customCandidateFilter({ referenceBlock: refBlock, targetPosition })) {
      diagnostics.rejectedUnsafeFloor++
      continue
    }

    candidates.push({ referenceBlock: refBlock, faceVector: faceUp, targetPosition })
  }
  return candidates
}

// Station-specific diagnostics with richer field set than the generic placementDiagnostics.
function stationPlacementDiagnostics(stationName, item) {
  return {
    station: stationName,
    bot_position: bot.entity ? positionJson(bot.entity.position) : null,
    item_in_inventory: Boolean(item),
    candidates_checked: 0,
    candidates_found: 0,
    rejected_no_support: 0,
    rejected_not_replaceable: 0,
    rejected_blocked_headroom: 0,
    rejected_too_far: 0,
    rejected_dangerous: 0,
    rejected_entity_collision: 0,
    placement_reference_block: null,
    placement_face: null,
    selected_candidate: null,
  }
}

// Expanded candidate search for station placement. Covers radius 1..5, no headroom
// requirement (stations are accessed from the side, not the top).
function buildExpandedStationCandidates(options, diag) {
  if (!bot.entity) return []
  const base = bot.entity.position.floored()
  const faceUp = new Vec3(0, 1, 0)
  const maxRadius = Math.min(5, Math.max(2, Number(options.radius || 4)))

  // Collect all (dx, dz) within radius, sorted closest-first.
  const pairs = []
  for (let dx = -maxRadius; dx <= maxRadius; dx++) {
    for (let dz = -maxRadius; dz <= maxRadius; dz++) {
      const dist = Math.sqrt(dx * dx + dz * dz)
      if (dist < 0.5 || dist > maxRadius + 0.5) continue
      pairs.push({ dx, dz, dist })
    }
  }
  pairs.sort((a, b) => a.dist - b.dist)

  const candidates = []
  for (const { dx, dz } of pairs) {
    // Try floor-based (dy=-1: reference below target) then wall-based (dy=0: reference same level).
    for (const dy of [-1, 0]) {
      diag.candidates_checked++
      const refPos = base.offset(dx, dy, dz)
      const refBlock = bot.blockAt(refPos)
      if (!isSolidBlock(refBlock)) { diag.rejected_no_support++; continue }
      if (STATION_BLOCK_TYPES.has(refBlock.name)) continue   // don't stack on stations

      const targetPos = refPos.offset(0, 1, 0)
      const targetBlock = bot.blockAt(targetPos)
      if (!canReplaceBlock(targetBlock)) { diag.rejected_not_replaceable++; continue }
      if (isLiquidBlock(targetBlock)) { diag.rejected_dangerous++; continue }

      // No headroom check: stations are usable from the side even under a 1-block ceiling.
      if (placementHasUnsafeLiquidNearby(targetPos, { avoidLava: true, avoidWater: false })) {
        diag.rejected_dangerous++; continue
      }
      if (placementIntersectsBot(targetPos) || placementIntersectsEntity(targetPos, options)) {
        diag.rejected_entity_collision++; continue
      }
      if (bot.entity.position.distanceTo(targetPos) > maxRadius + 1) {
        diag.rejected_too_far++; continue
      }

      diag.candidates_found++
      candidates.push({ referenceBlock: refBlock, faceVector: faceUp, targetPosition: targetPos })
    }
  }
  return candidates
}

// Dig at most STATION_NUISANCE_MAX_DIG vegetation/leaf blocks blocking placement candidates.
async function digNuisanceBlocksForStationArea(diag) {
  if (!bot.entity) return 0
  const base = bot.entity.position.floored()
  let count = 0

  const toCheck = []
  for (let dx = -3; dx <= 3; dx++) {
    for (let dz = -3; dz <= 3; dz++) {
      for (let dy = -1; dy <= 2; dy++) {
        if (dx === 0 && dz === 0 && dy <= 0) continue   // never dig directly below self
        toCheck.push(base.offset(dx, dy, dz))
      }
    }
  }
  toCheck.sort((a, b) => base.distanceTo(a) - base.distanceTo(b))

  for (const pos of toCheck) {
    if (count >= STATION_NUISANCE_MAX_DIG) break
    const block = bot.blockAt(pos)
    if (!block || !STATION_NUISANCE_BLOCK_NAMES.has(block.name)) continue
    if (isDangerousAdjacent(block)) continue
    if (isDirectlyUnderBot(block)) continue
    try {
      await digBlockWithTimeout(block, 3000)
      count++
    } catch (_) { /* skip un-diggable */ }
  }
  return count
}

// Robust station placement: expanded search → optional nuisance clearing → up to 3 attempts.
async function placeStationRobust(action, itemName, verifyBlockNames, findFn, opts = {}) {
  const searchRadius = Math.max(1, Math.min(8, Number(opts.radius || 4)))
  const allowPrepareArea = opts.allowPrepareArea !== false

  // 1. Already nearby and usable?
  const existing = findFn(STATION_USE_RADIUS)
  if (existing) {
    return ok(action, {
      alreadyPresent: true,
      already_satisfied: true,
      stop_reason: 'station_already_available',
      [`has_${itemName}`]: true,
      [`${itemName}_position`]: positionJson(existing.position),
      position: positionJson(existing.position),
      workspace_position: bot.entity ? positionJson(bot.entity.position) : null,
      has_nearby_furnace: itemName === 'furnace' ? true : undefined,
      has_inventory_furnace: itemName === 'furnace' ? Boolean(firstInventoryItemByNames([itemName])) : undefined,
      inventory: inventoryJson(),
    })
  }

  // 2. Need the item in inventory.
  const item = firstInventoryItemByNames([itemName])
  const diag = stationPlacementDiagnostics(itemName, item)
  diag.radius = searchRadius
  diag.allow_prepare_area = allowPrepareArea
  diag.has_nearby_item = false
  diag.has_inventory_item = Boolean(item)

  if (!item) {
    return makePlacementFailure(action, 'missing_item', diag, {
      failed_because: [{ kind: 'missing_item', station: itemName, needed: `${itemName} in inventory` }],
    })
  }

  const searchOpts = { itemName, avoidLava: true, avoidWater: true, avoidEntities: true, radius: searchRadius }

  // 3. First candidate search.
  let candidates = buildExpandedStationCandidates(searchOpts, diag)

  // 4. Area preparation if no candidates found (only when allowPrepareArea).
  let preparedBlocksDug = 0
  if (candidates.length === 0 && allowPrepareArea) {
    preparedBlocksDug = await digNuisanceBlocksForStationArea(diag)
    if (preparedBlocksDug > 0) {
      diag.candidates_checked = 0; diag.candidates_found = 0
      diag.rejected_no_support = 0; diag.rejected_not_replaceable = 0
      diag.rejected_blocked_headroom = 0; diag.rejected_too_far = 0
      diag.rejected_dangerous = 0; diag.rejected_entity_collision = 0
      candidates = buildExpandedStationCandidates(searchOpts, diag)
    }
  }

  // 5. No candidate even after prep → rich failure.
  if (candidates.length === 0) {
    return fail(action, 'No safe placement position found nearby.', {
      failure_type: 'no_safe_placement',
      stop_reason: 'no_station_placement_candidate',
      area_cramped: true,
      failed_because: [{ kind: 'no_safe_placement', station: itemName, candidate_positions_found: 0, area_cramped: true }],
      diagnostics: diag,
    })
  }

  // 6. Try up to 3 candidates.
  const maxAttempts = Math.min(3, candidates.length)
  for (let i = 0; i < maxAttempts; i++) {
    const cand = candidates[i]
    diag.selected_candidate = positionJson(cand.targetPosition)
    diag.placement_reference_block = positionJson(cand.referenceBlock.position)
    diag.placement_face = 'up'

    stopMovement()
    await delay(50)

    const freshRef = bot.blockAt(cand.referenceBlock.position)
    if (!freshRef || !isSolidBlock(freshRef)) continue   // reference block gone, try next

    try {
      await bot.equip(item, 'hand')
      const lookTarget = faceCenter(freshRef.position, cand.faceVector)
      await bot.lookAt(lookTarget, true)
      await delay(80)
      await placeBlockWithTimeout(freshRef, cand.faceVector, PLACE_TIMEOUT_MS)
    } catch (_) { /* verify below */ }

    const verified = await waitForBlockAt(cand.targetPosition, verifyBlockNames, PLACE_VERIFY_MS)
    if (verified) {
      rememberPlacementWaypoint(action, cand.targetPosition)
      return ok(action, {
        placed: true,
        [`${itemName}_position`]: positionJson(cand.targetPosition),
        [`has_${itemName}`]: true,
        workspace_position: bot.entity ? positionJson(bot.entity.position) : null,
        position: positionJson(cand.targetPosition),
        ...(preparedBlocksDug > 0 ? { preparedArea: true, preparedBlocksDug } : {}),
        diagnostics: diag,
        inventory: inventoryJson(),
      })
    }
  }

  return fail(action, 'Placement failed after trying safe candidates.', {
    failure_type: 'no_safe_placement',
    stop_reason: 'placement_failed',
    failed_because: [{ kind: 'no_safe_placement', station: itemName, candidate_positions_found: diag.candidates_found, area_cramped: diag.candidates_found === 0 }],
    diagnostics: diag,
  })
}

function findSafePlacementCandidate(options = {}) {
  const diagnostics = placementDiagnostics()
  if (!bot.entity) {
    return placementCandidateFailure('no_safe_workspace', diagnostics, {
      failure_type: 'not_ready',
      stop_reason: 'bot_not_ready',
      suggested_next_action: 'status',
      can_retry: true,
      needed: 'spawned bot entity',
    })
  }

  if (isBotInLiquid() && options.allowLiquid !== true) {
    return placementCandidateFailure('danger', diagnostics, {
      stop_reason: 'unsafe_placement_area',
      needed: 'dry stable footing before placing blocks',
    })
  }

  const itemName = options.itemName || ''
  const placementKind = options.placementKind || (
    BOAT_ITEM_NAMES.has(itemName) || itemName === 'boat' ? 'boat'
      : BED_ITEM_NAMES.has(itemName) || itemName === 'bed' ? 'bed'
        : itemName === 'torch' ? 'torch'
          : options.mode === 'directional' ? 'directional'
            : 'floor'
  )

  if (placementKind === 'boat') {
    const candidate = findWaterSurfaceCandidates()[0]
    if (!candidate) {
      return placementCandidateFailure('no_safe_workspace', diagnostics, {
        stop_reason: 'no_water_surface_nearby',
        needed: 'nearby open water surface',
      })
    }
    return normalizePlacementCandidate(candidate, placementKind, diagnostics)
  }

  if (placementKind === 'bed') {
    const candidate = findBedPlacementCandidates()[0]
    if (!candidate) {
      return placementCandidateFailure('no_safe_workspace', diagnostics, {
        needed: '2-block bed footprint with solid floor and head clearance',
      })
    }
    return normalizePlacementCandidate(candidate, placementKind, diagnostics)
  }

  const requestedDirection = options.direction
    || (options.mode === 'forward' ? 'forward' : null)
    || (options.mode === 'under_self' ? 'down' : null)
  if (placementKind === 'directional' || (requestedDirection && options.mode !== 'nearby')) {
    const candidate = findDirectionalPlacementCandidate(requestedDirection || 'forward')
    if (!candidate) {
      return placementCandidateFailure('no_safe_workspace', diagnostics, {
        stop_reason: 'no_solid_reference_block',
        needed: 'solid reference block in the requested direction',
      })
    }
    return normalizePlacementCandidate(candidate, placementKind, diagnostics)
  }

  const candidates = placementKind === 'torch'
    ? findTorchCandidates().map(c => ({ ...c, targetPosition: c.placePosition }))
    : buildFloorPlacementCandidates(options, diagnostics)

  if (candidates.length === 0) return placementCandidateFailure('no_safe_workspace', diagnostics)
  return normalizePlacementCandidate(candidates[0], placementKind, diagnostics)
}

async function placeItemSafely(itemName, options = {}) {
  const action = options.action || 'place_block'
  const item = options.item || findPlaceableItem(itemName)
  const diagnostics = placementDiagnostics()

  if (!item && !options.bucketSpecialCase) {
    return makePlacementFailure(action, 'missing_item', diagnostics, {
      needed: `${itemName} in inventory`,
      error: `Missing materials: no ${itemName} in inventory.`,
    })
  }

  const candidate = findSafePlacementCandidate({ ...options, itemName })
  if (!candidate.ok) {
    const reason = candidate.failure_type === 'danger_detected' ? 'danger' : 'no_safe_workspace'
    return makePlacementFailure(action, reason, candidate.diagnostics, candidate)
  }

  stopMovement()
  await delay(50)

  const freshRef = bot.blockAt(candidate.referenceBlock.position)
  if (!freshRef || (!isSolidBlock(freshRef) && candidate.placementKind !== 'boat')) {
    return makePlacementFailure(action, 'failed', candidate.diagnostics, {
      stop_reason: 'no_solid_reference_block',
      needed: 'solid reference block for placement',
    })
  }

  try {
    await bot.equip(item, 'hand')
    const lookTarget = candidate.placementKind === 'bed' && candidate.headDirection
      ? candidate.targetPosition.plus(candidate.headDirection).offset(0.5, 0.5, 0.5)
      : faceCenter(freshRef.position, candidate.faceVector)
    await bot.lookAt(lookTarget, true)
    await delay(80)
    await placeBlockWithTimeout(freshRef, candidate.faceVector, PLACE_TIMEOUT_MS)
  } catch (_error) {
    // The server can report an error after accepting placement; verify below.
  }

  if (candidate.placementKind === 'boat') {
    await delay(350)
    const boatEntity = findNearestBoatEntity(8)
    if (boatEntity) {
      return ok(action, {
        placed: true,
        placementKind: candidate.placementKind,
        boatType: item.name,
        position: positionJson(boatEntity.position),
        diagnostics: candidate.diagnostics,
        inventory: inventoryJson(),
      })
    }
    return makePlacementFailure(action, 'failed', candidate.diagnostics, {
      error: 'Boat placement failed. No boat entity detected after placement attempt.',
    })
  }

  const verifyBlockNames = options.verifyBlockNames || blockNamesForItem(itemName)
  const verified = await waitForBlockAt(candidate.targetPosition, verifyBlockNames, PLACE_VERIFY_MS)
  if (verified) {
    rememberPlacementWaypoint(action, candidate.targetPosition)
    const result = {
      placed: true,
      placementKind: candidate.placementKind,
      position: positionJson(candidate.targetPosition),
      diagnostics: candidate.diagnostics,
      inventory: inventoryJson(),
    }
    if (candidate.placementKind === 'bed') {
      result.bedItem = item.name
      const dimension = getBotDimension()
      if (dimension && !dimension.includes('overworld')) {
        result.warning = `Bed placed in dimension '${dimension}'. Using/sleeping will cause explosion; only use for bed_bomb.`
      }
    }
    return ok(action, result)
  }

  return makePlacementFailure(action, 'failed', candidate.diagnostics)
}

function rememberPlacementWaypoint(action, position) {
  if (!position) return
  if (action === 'place_crafting_table') {
    rememberWaypointAt('workspace', 'workspace', position)
    rememberWaypointAt('crafting_area', 'crafting_area', position)
  } else if (action === 'place_furnace') {
    rememberWaypointAt('workspace', 'workspace', position)
    rememberWaypointAt('furnace_area', 'furnace_area', position)
  } else if (action === 'place_chest') {
    rememberWaypointAt('workspace', 'workspace', position)
  }
}

// Generalized floor placement candidates 窶・same geometry as findCraftingTableCandidates.
function findGeneralFloorCandidates() {
  if (!bot.entity) return []
  const base = bot.entity.position.floored()
  const faceUp = new Vec3(0, 1, 0)

  const refOffsets = [
    new Vec3(2, -1, 0),  new Vec3(-2, -1, 0), new Vec3(0, -1, 2),  new Vec3(0, -1, -2),
    new Vec3(2, -1, 1),  new Vec3(2, -1, -1), new Vec3(-2, -1, 1), new Vec3(-2, -1, -1),
    new Vec3(1, -1, 2),  new Vec3(-1, -1, 2), new Vec3(1, -1, -2), new Vec3(-1, -1, -2),
    new Vec3(1, -1, 0),  new Vec3(-1, -1, 0), new Vec3(0, -1, 1),  new Vec3(0, -1, -1),
    new Vec3(1, 0, 0),   new Vec3(-1, 0, 0),  new Vec3(0, 0, 1),   new Vec3(0, 0, -1),
    new Vec3(0, -1, 0)
  ]

  const candidates = []
  for (const offset of refOffsets) {
    const refPos   = base.plus(offset)
    const refBlock = bot.blockAt(refPos)
    if (!isSolidBlock(refBlock)) continue

    const placePos   = refPos.offset(0, 1, 0)
    const placeBlock = bot.blockAt(placePos)
    if (!canReplaceBlock(placeBlock)) continue

    const headBlock = bot.blockAt(placePos.offset(0, 1, 0))
    if (!canReplaceBlock(headBlock)) continue

    if (placementIntersectsBot(placePos)) continue
    if (bot.entity.position.distanceTo(refPos.offset(0.5, 1.0, 0.5)) > 4.5) continue

    candidates.push({ referenceBlock: refBlock, faceVector: faceUp, placePosition: placePos })
  }
  return candidates
}

// Torch candidates: relaxed (no head-clearance, no intersect check — torches are non-solid).
function findTorchCandidates() {
  if (!bot.entity) return []
  const base = bot.entity.position.floored()
  const faceUp = new Vec3(0, 1, 0)

  const refOffsets = [
    new Vec3(1, -1, 0), new Vec3(-1, -1, 0), new Vec3(0, -1, 1),  new Vec3(0, -1, -1),
    new Vec3(2, -1, 0), new Vec3(-2, -1, 0), new Vec3(0, -1, 2),  new Vec3(0, -1, -2),
    new Vec3(0, -1, 0)
  ]

  const candidates = []
  for (const offset of refOffsets) {
    const refPos   = base.plus(offset)
    const refBlock = bot.blockAt(refPos)
    if (!isSolidBlock(refBlock)) continue

    const placePos = refPos.offset(0, 1, 0)
    if (!canReplaceBlock(bot.blockAt(placePos))) continue
    if (bot.entity.position.distanceTo(refPos.offset(0.5, 1.0, 0.5)) > 4.5) continue

    candidates.push({ referenceBlock: refBlock, faceVector: faceUp, placePosition: placePos })
  }
  return candidates
}

// Bed candidates: require a 2-block footprint (foot + head) in at least one cardinal direction.
function findBedPlacementCandidates() {
  if (!bot.entity) return []
  const base = bot.entity.position.floored()
  const faceUp = new Vec3(0, 1, 0)
  const cardinals = [
    new Vec3(1, 0, 0), new Vec3(-1, 0, 0), new Vec3(0, 0, 1), new Vec3(0, 0, -1)
  ]

  const refOffsets = [
    new Vec3(1, -1, 0), new Vec3(-1, -1, 0), new Vec3(0, -1, 1),  new Vec3(0, -1, -1),
    new Vec3(2, -1, 0), new Vec3(-2, -1, 0), new Vec3(0, -1, 2),  new Vec3(0, -1, -2),
  ]

  const candidates = []
  for (const offset of refOffsets) {
    const refPos   = base.plus(offset)
    const refBlock = bot.blockAt(refPos)
    if (!isSolidBlock(refBlock)) continue

    const footPos = refPos.offset(0, 1, 0)
    if (!canReplaceBlock(bot.blockAt(footPos))) continue
    if (placementIntersectsBot(footPos)) continue
    if (bot.entity.position.distanceTo(refPos.offset(0.5, 1.0, 0.5)) > 4.5) continue

    for (const card of cardinals) {
      const headPos = footPos.plus(card)
      if (!canReplaceBlock(bot.blockAt(headPos))) continue
      if (!isSolidBlock(bot.blockAt(headPos.offset(0, -1, 0)))) continue

      candidates.push({ referenceBlock: refBlock, faceVector: faceUp, placePosition: footPos, headDirection: card })
      break
    }
  }
  return candidates
}

// Water-surface candidates for boat placement.
function findWaterSurfaceCandidates() {
  if (!bot.entity) return []
  const base = bot.entity.position.floored()
  const faceUp = new Vec3(0, 1, 0)

  const horizOffsets = [
    ...PLACEMENT_OFFSETS,
    new Vec3(3, 0, 0), new Vec3(-3, 0, 0), new Vec3(0, 0, 3), new Vec3(0, 0, -3)
  ]

  const candidates = []
  for (const horiz of horizOffsets) {
    for (let dy = 2; dy >= -4; dy--) {
      const waterPos = base.plus(horiz).offset(0, dy, 0)
      const waterBlock = bot.blockAt(waterPos)
      if (!waterBlock || !waterBlock.name.includes('water')) continue

      const above = bot.blockAt(waterPos.offset(0, 1, 0))
      if (!above || above.name !== 'air') continue

      if (bot.entity.position.distanceTo(waterPos.offset(0.5, 1.0, 0.5)) > 5) continue

      candidates.push({ referenceBlock: waterBlock, faceVector: faceUp, placePosition: waterPos.offset(0, 1, 0) })
      break
    }
  }
  return candidates
}

// Floor candidates with optional minimum bot distance — used for liquid placement.
function findLiquidPlacementCandidates(minBotDistance) {
  const base = findGeneralFloorCandidates()
  if (!minBotDistance || minBotDistance <= 0) return base
  return base.filter(c => bot.entity && bot.entity.position.distanceTo(c.placePosition) >= minBotDistance)
}

// True if lava can be safely placed at position.
function isLavaPlacementSafe(placePosition) {
  if (!bot.entity) return false
  if (bot.entity.position.distanceTo(placePosition) < LAVA_MIN_SAFE_DISTANCE) return false
  if (placePosition.y < 10) return false

  const flammableKeywords = ['wood', 'log', 'plank', 'leaves', 'wool', 'carpet', 'fence']
  for (const offset of MINE_FACE_OFFSETS) {
    const neighbor = bot.blockAt(placePosition.plus(offset))
    if (!neighbor) continue
    if (flammableKeywords.some(k => neighbor.name.includes(k))) return false
  }
  return true
}

// Return current dimension as a string.
function getBotDimension() {
  return (bot.game && bot.game.dimension) ? String(bot.game.dimension) : 'overworld'
}

// Shared placement loop used by all placement actions.
// Returns an ok result or null if all candidates failed; caller emits the final fail().
async function placeBlockItem(actionName, item, candidates, verifyBlockNames) {
  stopMovement()
  await delay(50)

  for (const { referenceBlock, faceVector, placePosition } of candidates) {
    const freshRef   = bot.blockAt(referenceBlock.position)
    if (!isSolidBlock(freshRef)) continue
    const freshPlace = bot.blockAt(placePosition)
    if (!canReplaceBlock(freshPlace)) continue

    try {
      await bot.equip(item, 'hand')
      await bot.lookAt(faceCenter(freshRef.position, faceVector), true)
      await delay(80)
      await placeBlockWithTimeout(freshRef, faceVector, PLACE_TIMEOUT_MS)
    } catch (_error) {
      const verified = await waitForBlockAt(placePosition, verifyBlockNames, PLACE_VERIFY_MS)
      if (verified) {
        return ok(actionName, { placed: true, position: positionJson(placePosition), verifiedAfterError: true, inventory: inventoryJson() })
      }
      continue
    }

    const verified = await waitForBlockAt(placePosition, verifyBlockNames, PLACE_VERIFY_MS)
    if (verified) {
      return ok(actionName, { placed: true, position: positionJson(placePosition), inventory: inventoryJson() })
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// Movement / positioning helpers
// ---------------------------------------------------------------------------

// Mineflayer yaw: 0=south, π/2=west, π=north, 3π/2=east
function yawToCardinalOffset(yaw) {
  const norm = ((yaw % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
  if (norm < Math.PI / 4 || norm >= 7 * Math.PI / 4) return new Vec3(0, 0, 1)   // south
  if (norm < 3 * Math.PI / 4)                         return new Vec3(-1, 0, 0)  // west
  if (norm < 5 * Math.PI / 4)                         return new Vec3(0, 0, -1)  // north
  return new Vec3(1, 0, 0)                                                        // east
}

// Resolve a direction string to a unit Vec3.  Returns null if unknown.
function resolveMovementDirection(dir) {
  if (!dir) return null
  const fixed = {
    north: new Vec3(0, 0, -1), south: new Vec3(0, 0, 1),
    east:  new Vec3(1, 0, 0),  west:  new Vec3(-1, 0, 0),
    up:    new Vec3(0, 1, 0),  down:  new Vec3(0, -1, 0),
  }
  if (fixed[dir]) return fixed[dir]
  if (!bot.entity) return new Vec3(0, 0, 1)
  const fwd = yawToCardinalOffset(bot.entity.yaw)
  if (dir === 'forward') return fwd
  if (dir === 'back')    return new Vec3(-fwd.x, 0, -fwd.z)
  if (dir === 'left')    return new Vec3(-fwd.z, 0,  fwd.x)
  if (dir === 'right')   return new Vec3( fwd.z, 0, -fwd.x)
  return null
}

// True if there are ≥ SKY_AIR_BLOCKS consecutive air blocks above pos.
const SKY_AIR_BLOCKS = 20
function isSkyVisible(pos) {
  if (!pos) return false
  for (let dy = 1; dy <= SKY_AIR_BLOCKS; dy++) {
    const block = bot.blockAt(pos.offset(0, dy, 0))
    if (block && !canReplaceBlock(block)) return false
  }
  return true
}

// Find a flat safe workspace position within radius blocks.
function findWorkspacePosition(radius) {
  if (!bot.entity) return null
  const base = bot.entity.position.floored()
  for (let dist = 8; dist <= radius; dist += 4) {
    const offsets = [
      new Vec3(dist, 0, 0), new Vec3(-dist, 0, 0),
      new Vec3(0, 0, dist), new Vec3(0, 0, -dist),
      new Vec3(Math.ceil(dist * 0.7), 0, Math.ceil(dist * 0.7)),
      new Vec3(-Math.ceil(dist * 0.7), 0, Math.ceil(dist * 0.7)),
    ]
    for (const off of offsets) {
      const standPos = nearestSafeStandPosition(base.plus(off), 4)
      if (standPos && isGoodWorkspace(standPos)) return standPos
    }
  }
  return null
}

// True if feetPos is a good workspace: solid floor, 2-block clearance, no liquids.
function isGoodWorkspace(feetPos) {
  const floor = bot.blockAt(feetPos.offset(0, -1, 0))
  const body  = bot.blockAt(feetPos)
  const head  = bot.blockAt(feetPos.offset(0, 1, 0))
  if (!isSolidBlock(floor)) return false
  if (!canReplaceBlock(body) || !canReplaceBlock(head)) return false
  if (isLiquidBlock(body) || isLiquidBlock(head)) return false
  // Need at least one adjacent placeable spot
  for (const off of [new Vec3(1,0,0), new Vec3(-1,0,0), new Vec3(0,0,1), new Vec3(0,0,-1)]) {
    const af = bot.blockAt(feetPos.plus(off).offset(0, -1, 0))
    const ab = bot.blockAt(feetPos.plus(off))
    if (isSolidBlock(af) && canReplaceBlock(ab)) return true
  }
  return true
}

// Count adjacent grid cells where a block can be placed (solid floor + clear body space).
function countAdjacentPlaceableSpots(feetPos) {
  let count = 0
  for (const off of [new Vec3(1,0,0), new Vec3(-1,0,0), new Vec3(0,0,1), new Vec3(0,0,-1)]) {
    const adj = feetPos.plus(off)
    const af = bot.blockAt(adj.offset(0, -1, 0))
    const ab = bot.blockAt(adj)
    if (isSolidBlock(af) && canReplaceBlock(ab)) count++
  }
  return count
}

// Derive the most useful next action given the workspace purpose and placeable capacity.
function workspaceSuggestedNextAction(purpose, canPlaceCraftingTable, canPlaceFurnace, canPlaceChest) {
  if (purpose === 'crafting' && canPlaceCraftingTable) {
    return firstInventoryItemByNames(['crafting_table']) ? 'place_crafting_table' : 'craft_crafting_table'
  }
  if (purpose === 'smelting' && canPlaceFurnace) {
    return firstInventoryItemByNames(['furnace']) ? 'place_furnace' : 'craft_furnace'
  }
  if (purpose === 'storage' && canPlaceChest) {
    return firstInventoryItemByNames(['chest']) ? 'place_chest' : 'craft_chest'
  }
  return 'scan_workspace'
}

// Find best pillar/bridge block from inventory.
function resolvePillarItem(blockName) {
  if (blockName) {
    if (blockName === 'planks')         return firstInventoryItemByNames(Array.from(PLANK_ITEM_NAMES))
    if (blockName.endsWith('_planks')) return firstInventoryItemByNames([blockName]) || firstInventoryItemByNames(Array.from(PLANK_ITEM_NAMES))
    if (PILLAR_BLOCK_NAMES.includes(blockName)) return firstInventoryItemByNames([blockName])
    return null
  }
  return firstInventoryItemByNames([...PILLAR_BLOCK_NAMES, ...Array.from(PLANK_ITEM_NAMES)])
}

// Find the nearest boat entity within radius blocks.
function findNearestBoatEntity(radius) {
  if (!bot.entity || !bot.entities) return null
  return Object.values(bot.entities)
    .filter(e => e && e !== bot.entity && e.name && e.name.includes('boat') &&
                 e.position && bot.entity.position.distanceTo(e.position) <= radius)
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null
}

// Find a directional placement candidate for place_block_in_direction.
function findDirectionalPlacementCandidate(direction) {
  if (!bot.entity) return null
  const base = bot.entity.position.floored()
  const faceUp = new Vec3(0, 1, 0)
  const dir = resolveMovementDirection(direction || 'forward')
  if (!dir) return null

  if (direction === 'up') {
    const refPos = base.offset(0, 1, 0)
    const refBlock = bot.blockAt(refPos)
    if (refBlock && isSolidBlock(refBlock)) {
      const pp = refPos.offset(0, 1, 0)
      if (canReplaceBlock(bot.blockAt(pp))) return { referenceBlock: refBlock, faceVector: faceUp, placePosition: pp }
    }
    return null
  }

  if (direction === 'down') {
    const refPos = base.offset(0, -2, 0)
    const refBlock = bot.blockAt(refPos)
    if (refBlock && isSolidBlock(refBlock)) {
      const pp = base.offset(0, -1, 0)
      if (canReplaceBlock(bot.blockAt(pp))) return { referenceBlock: refBlock, faceVector: faceUp, placePosition: pp }
    }
    return null
  }

  // Horizontal: ref = current floor, face = horizontal direction
  const floorBlock = bot.blockAt(base.offset(0, -1, 0))
  if (floorBlock && isSolidBlock(floorBlock)) {
    const faceVec = new Vec3(dir.x, 0, dir.z)
    const pp = base.offset(0, -1, 0).plus(faceVec)
    if (canReplaceBlock(bot.blockAt(pp)) && !placementIntersectsBot(pp)) {
      return { referenceBlock: floorBlock, faceVector: faceVec, placePosition: pp }
    }
  }
  return null
}

async function findSafeExplorePosition(radius) {
  if (!bot.entity) {
    return null
  }

  const base = bot.entity.position.floored()
  const candidates = [
    new Vec3(radius, 0, 0),
    new Vec3(-radius, 0, 0),
    new Vec3(0, 0, radius),
    new Vec3(0, 0, -radius),
    new Vec3(Math.floor(radius / 2), 0, Math.floor(radius / 2)),
    new Vec3(-Math.floor(radius / 2), 0, Math.floor(radius / 2)),
    new Vec3(Math.floor(radius / 2), 0, -Math.floor(radius / 2)),
    new Vec3(-Math.floor(radius / 2), 0, -Math.floor(radius / 2))
  ]

  for (const offset of candidates) {
    await yieldToEventLoop()
    const candidate = base.plus(offset)
    const safe = nearestSafeStandPosition(candidate, 4)
    if (safe) {
      return safe
    }
  }

  return null
}

function nearestSafeStandPosition(center, verticalRange) {
  for (let dy = verticalRange; dy >= -verticalRange; dy--) {
    const feet = center.offset(0, dy, 0)
    const floor = bot.blockAt(feet.offset(0, -1, 0))
    const body = bot.blockAt(feet)
    const head = bot.blockAt(feet.offset(0, 1, 0))

    if (isSolidBlock(floor) && canReplaceBlock(body) && canReplaceBlock(head)) {
      return feet
    }
  }

  return null
}

function findNearbyCraftingTable(radius) {
  if (!bot.entity || !bot.registry.blocksByName.crafting_table) {
    return null
  }

  const position = bot.findBlock({
    matching: bot.registry.blocksByName.crafting_table.id,
    maxDistance: radius
  })

  return position || null
}

function findNearestStationBlock(station, radius) {
  if (!bot.entity) return null
  if (station === 'crafting_table') return findNearbyCraftingTable(radius)
  if (station === 'furnace') return findNearbyFurnace(radius)
  if (station === 'chest') return findNearbyChest(radius)
  return null
}

// Kept for compatibility — delegates to the generalised version.
function findCraftingTableCandidates() {
  return findGeneralFloorCandidates()
}

function findNearbyFurnace(radius) {
  if (!bot.entity || !bot.registry.blocksByName.furnace) {
    return null
  }

  return bot.findBlock({
    matching: bot.registry.blocksByName.furnace.id,
    maxDistance: radius
  }) || null
}

function noCraftingTableFail(action) {
  const visible = findNearbyCraftingTable(STATION_SCAN_RADIUS)
  if (visible) {
    const distance = bot.entity ? bot.entity.position.distanceTo(visible.position) : null
    return fail(action, `Crafting table is visible but too far to use (${formatDistance(distance)} blocks).`, {
      failure_type: 'missing_station',
      stop_reason: 'station_visible_but_too_far',
      station_needed: 'crafting_table',
      nearest_station_distance: distance,
      nearest_station_position: positionJson(visible.position),
      usable_radius: STATION_USE_RADIUS,
      suggested_next_action: 'approach_station',
      fallback_suggested_next_action: 'return_to_workspace',
      possible_next_actions: ['approach_station', 'return_to_workspace', 'setup_workspace', 'place_crafting_table'],
      can_retry: true,
      inventory: inventoryJson()
    })
  }

  return fail(action, `No crafting table found within radius ${STATION_SCAN_RADIUS}.`, {
    failure_type: 'missing_station',
    stop_reason: 'no_crafting_table_nearby',
    station_needed: 'crafting_table',
    suggested_next_action: 'setup_workspace',
    fallback_suggested_next_action: 'place_crafting_table',
    possible_next_actions: ['setup_workspace', 'place_crafting_table', 'craft_crafting_table', 'look_around'],
    can_retry: true,
    inventory: inventoryJson()
  })
}

function noFurnaceFail(action) {
  const visible = findNearbyFurnace(STATION_SCAN_RADIUS)
  if (visible) {
    const distance = bot.entity ? bot.entity.position.distanceTo(visible.position) : null
    return fail(action, `Furnace is visible but too far to use (${formatDistance(distance)} blocks).`, {
      failure_type: 'missing_station',
      stop_reason: 'station_visible_but_too_far',
      station_needed: 'furnace',
      nearest_station_distance: distance,
      nearest_station_position: positionJson(visible.position),
      usable_radius: STATION_USE_RADIUS,
      suggested_next_action: 'approach_station',
      fallback_suggested_next_action: 'return_to_workspace',
      possible_next_actions: ['approach_station', 'return_to_workspace', 'setup_workspace', 'place_furnace'],
      can_retry: true,
      inventory: inventoryJson()
    })
  }

  return fail(action, `No furnace found within radius ${STATION_SCAN_RADIUS}.`, {
    failure_type: 'missing_station',
    stop_reason: 'no_furnace_nearby',
    station_needed: 'furnace',
    suggested_next_action: 'setup_workspace',
    fallback_suggested_next_action: 'place_furnace',
    possible_next_actions: ['setup_workspace', 'place_furnace', 'craft_furnace', 'look_around'],
    can_retry: true,
    inventory: inventoryJson()
  })
}

function formatDistance(distance) {
  return typeof distance === 'number' ? (Math.round(distance * 10) / 10).toFixed(1) : 'unknown'
}

function missingCraftMaterials(spec, craftIterations) {
  const missing = []
  for (const [name, perCraft] of Object.entries(spec.materials || {})) {
    const need = perCraft * craftIterations
    const have = name === 'planks' ? countPlanksInInventory() : countItemInInventory(name)
    if (have < need) missing.push({ name, need, have })
  }

  for (const alternative of spec.alternativeMaterials || []) {
    const need = alternative.count * craftIterations
    const have = alternative.names.reduce((sum, name) => sum + countItemInInventory(name), 0)
    if (have < need) missing.push({ name: alternative.label, need, have, alternatives: alternative.names })
  }
  return missing
}

function formatMissingMaterials(missing) {
  return missing.map(item => `${item.name} x${Math.max(0, item.need - item.have)}`).join(', ')
}

function isAllowedSmeltFuel(name) {
  return SMELT_FUEL_ITEMS.has(name) || PLANK_ITEM_NAMES.has(name) || WOOD_BLOCK_NAMES.has(name)
}

function resolveSmeltFuel(requestedFuel) {
  if (requestedFuel) {
    if (!isAllowedSmeltFuel(requestedFuel)) return null
    if ((PLANK_ITEM_NAMES.has(requestedFuel) || WOOD_BLOCK_NAMES.has(requestedFuel)) && (countItemInInventory('coal') > 0 || countItemInInventory('charcoal') > 0)) {
      return null
    }
    return firstInventoryItemByNames([requestedFuel])
  }

  return firstInventoryItemByNames(['coal'])
    || firstInventoryItemByNames(['charcoal'])
    || firstInventoryItemByNames(Array.from(PLANK_ITEM_NAMES))
    || firstInventoryItemByNames(Array.from(WOOD_BLOCK_NAMES))
}

function _findCraftingTableCandidatesLegacy() {
  const base = bot.entity.position.floored()
  const face = new Vec3(0, 1, 0)

  // Ground-adjacent refs first (most reliable), same-height refs next,
  // then block directly below bot last (placing at bot's feet — server is most likely to reject)
  const refOffsets = [
    new Vec3(2, -1, 0),
    new Vec3(-2, -1, 0),
    new Vec3(0, -1, 2),
    new Vec3(0, -1, -2),
    new Vec3(2, -1, 1),
    new Vec3(2, -1, -1),
    new Vec3(-2, -1, 1),
    new Vec3(-2, -1, -1),
    new Vec3(1, -1, 2),
    new Vec3(-1, -1, 2),
    new Vec3(1, -1, -2),
    new Vec3(-1, -1, -2),
    new Vec3(1, -1, 0),
    new Vec3(-1, -1, 0),
    new Vec3(0, -1, 1),
    new Vec3(0, -1, -1),
    new Vec3(1, 0, 0),
    new Vec3(-1, 0, 0),
    new Vec3(0, 0, 1),
    new Vec3(0, 0, -1),
    new Vec3(0, -1, 0)
  ]

  const candidates = []
  for (const offset of refOffsets) {
    const refPos = base.plus(offset)
    const refBlock = bot.blockAt(refPos)
    if (!isSolidBlock(refBlock)) continue

    const placePos = refPos.offset(0, 1, 0)
    const placeBlock = bot.blockAt(placePos)
    if (!canReplaceBlock(placeBlock)) continue

    const headBlock = bot.blockAt(placePos.offset(0, 1, 0))
    if (!canReplaceBlock(headBlock)) continue

    if (placementIntersectsBot(placePos)) continue

    // Measure reach to the top face of the reference block — the point actually clicked
    if (!bot.entity || bot.entity.position.distanceTo(refPos.offset(0.5, 1.0, 0.5)) > 4.5) continue

    candidates.push({ referenceBlock: refBlock, faceVector: face, placePosition: placePos })
  }

  return candidates
}

function isBotInLiquid() {
  if (!bot.entity) {
    return false
  }

  const currentBlock = bot.blockAt(bot.entity.position)
  const feetBlock = bot.blockAt(bot.entity.position.floored())
  return isLiquidBlock(currentBlock) || isLiquidBlock(feetBlock)
}

function isLiquidBlock(block) {
  return Boolean(block && (block.name.includes('water') || block.name.includes('lava')))
}

function isInNamedLiquid(name) {
  if (!bot.entity) {
    return false
  }

  const currentBlock = bot.blockAt(bot.entity.position)
  const feetBlock = bot.blockAt(bot.entity.position.floored())
  return Boolean(
    (currentBlock && currentBlock.name.includes(name)) ||
    (feetBlock && feetBlock.name.includes(name))
  )
}

function isSolidBlock(block) {
  return Boolean(block && block.boundingBox === 'block' && !isLiquidBlock(block))
}

function canReplaceBlock(block) {
  return Boolean(block && (block.name === 'air' || block.boundingBox === 'empty'))
}

function placementIntersectsBot(placePosition) {
  if (!bot.entity) {
    return false
  }

  const botPosition = bot.entity.position
  const xIntersects = botPosition.x > placePosition.x - 0.35 && botPosition.x < placePosition.x + 1.35
  const zIntersects = botPosition.z > placePosition.z - 0.35 && botPosition.z < placePosition.z + 1.35
  const yIntersects = botPosition.y < placePosition.y + 1 && botPosition.y + 1.8 > placePosition.y
  return xIntersects && yIntersects && zIntersects
}

function isProtectedBlock(block) {
  if (!block) {
    return true
  }

  if (NEVER_MINE_BLOCK_NAMES.has(block.name)) {
    return true
  }

  return (
    block.name.endsWith('_planks') ||
    block.name.endsWith('_door') ||
    block.name.endsWith('_trapdoor') ||
    block.name.endsWith('_sign') ||
    block.name.endsWith('_wall_sign') ||
    block.name.endsWith('_button') ||
    block.name.endsWith('_pressure_plate') ||
    block.name.includes('command_block')
  )
}

function isDirectlyUnderBot(block) {
  if (!block || !bot.entity) {
    return false
  }

  const botBase = bot.entity.position.floored()
  return block.position.x === botBase.x && block.position.z === botBase.z && block.position.y < botBase.y
}

function isSoftExposureBlock(block) {
  return Boolean(block && SOFT_EXPOSURE_BLOCK_NAMES.has(block.name) && !isDangerousAdjacent(block) && !isProtectedBlock(block))
}

function isDangerousAdjacent(block) {
  if (!block) {
    return true
  }

  return MINE_FACE_OFFSETS.some((offset) => {
    const neighbor = bot.blockAt(block.position.plus(offset))
    return isLiquidBlock(neighbor)
  })
}

function hasExposedFace(block) {
  return MINE_FACE_OFFSETS.some((offset) => {
    const neighbor = bot.blockAt(block.position.plus(offset))
    return canReplaceBlock(neighbor)
  })
}

function isHostileEntity(entity) {
  const name = entity && (entity.name || entity.displayName)
  return typeof name === 'string' && HOSTILE_ENTITY_NAMES.has(name)
}

function nearestHostileEntity() {
  if (!bot.entity || !bot.entities) {
    return null
  }

  return Object.values(bot.entities)
    .filter((entity) => entity && entity !== bot.entity && entity.position && isHostileEntity(entity))
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null
}

function countPlanksInInventory() {
  return inventoryJson()
    .filter((item) => PLANK_ITEM_NAMES.has(item.name))
    .reduce((total, item) => total + item.count, 0)
}

function inventoryCount(name) {
  return inventoryJson()
    .filter((item) => item.name === name)
    .reduce((total, item) => total + item.count, 0)
}

function countItemInInventory(itemName) {
  return inventoryCount(itemName)
}

function hasPickaxe() {
  return Boolean(firstInventoryItemByNames(Array.from(PICKAXE_ITEM_NAMES)))
}

function hasPickaxeAtLeast(minimumName) {
  const minimumIndex = PICKAXE_PRIORITY.indexOf(minimumName)
  if (minimumIndex < 0) {
    return false
  }

  return PICKAXE_PRIORITY.slice(0, minimumIndex + 1).some((name) => firstInventoryItemByNames([name]))
}

async function equipBestPickaxe() {
  const pickaxe = firstInventoryItemByNames(PICKAXE_PRIORITY)
  if (!pickaxe) {
    throw new Error('Missing tool: wooden_pickaxe or better is required.')
  }

  await withTimeout(bot.equip(pickaxe, 'hand'), 5000, `equipping ${pickaxe.name}`)
  return pickaxe
}

function firstInventoryItemByNames(names) {
  const allowed = new Set(names)
  if (!bot.inventory || typeof bot.inventory.items !== 'function') {
    return null
  }

  return bot.inventory.items().find((item) => allowed.has(item.name)) || null
}

function itemType(name) {
  return bot.registry.itemsByName[name] || null
}

function errorMessage(error) {
  return error && error.message ? error.message : String(error)
}

function isPathTimeoutError(error) {
  const text = errorMessage(error).toLowerCase()
  return (
    (text.includes('path') && (text.includes('timed out') || text.includes('timeout'))) ||
    text.includes('took too long')
  )
}

function isPlanningTimeoutError(error) {
  return errorMessage(error).toLowerCase().includes('took too long to decide path')
}

function positionKey(position) {
  return `${position.x},${position.y},${position.z}`
}

function stopMovement() {
  safeStopMovement(bot)
}

function shortJump() {
  bot.setControlState('jump', true)
  setTimeout(() => {
    bot.setControlState('jump', false)
  }, 350)
}
