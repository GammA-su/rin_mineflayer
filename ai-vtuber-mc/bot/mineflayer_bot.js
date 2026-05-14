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
const MINE_STONE_MIN_HEALTH = 10
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
const ACQUIRE_PATH_TIMEOUT_MS = 15000
const ACQUIRE_DIG_TIMEOUT_MS = 8000
const ACQUIRE_MAX_EXCAVATED_BLOCKS = 8
const ACQUIRE_MAX_STEPS = 8
const ACQUIRE_MAX_ATTEMPTS = 64
const ACQUIRE_ACCESS_MODES = new Set(['surface_first', 'safe_staircase'])
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
  'zombie',
  'skeleton',
  'creeper',
  'spider',
  'enderman',
  'witch',
  'drowned',
  'husk',
  'stray',
  'slime',
  'phantom',
  'pillager'
])
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
  'craft_wooden_pickaxe',
  'mine_stone',
  'craft_stone_pickaxe',
  'flee',
  'eat_food'
])

let defaultMovements = null

const botOptions = {
  host: process.env.MC_HOST || 'localhost',
  port: numberEnv('MC_PORT', 25565),
  username: process.env.MC_USERNAME || 'AI_VTuber'
}

if (MC_VERSION) {
  botOptions.version = MC_VERSION
}

const bot = mineflayer.createBot(botOptions)
bot.loadPlugin(pathfinder)
bot.loadPlugin(toolPlugin)
bot.loadPlugin(collectBlock)

bot.on('login', () => {
  console.log(`Mineflayer logged in as ${bot.username}`)
})

bot.on('spawn', () => {
  defaultMovements = new Movements(bot)
  bot.pathfinder.setMovements(defaultMovements)
  bot.collectBlock.movements = defaultMovements
  console.log('Mineflayer bot spawned')
  bot.chat('AI VTuber online!')
})

bot.on('kicked', (reason) => {
  console.log('Mineflayer bot kicked:', reason)
})

bot.on('error', (error) => {
  console.log('Mineflayer error:', error)
})

bot.on('end', () => {
  console.log('Mineflayer bot disconnected')
})

const app = express()
app.use(bodyParser.json({ limit: '10kb' }))

app.get('/status', (_req, res) => {
  res.json(getStatus())
})

app.get('/actions', (_req, res) => {
  res.json({ ok: true, actions: Array.from(ACTIONS).sort() })
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

function numberEnv(name, fallback) {
  const raw = process.env[name]
  if (!raw) {
    return fallback
  }

  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : fallback
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

function ok(action, result = {}) {
  return { ok: true, action, result, error: null }
}

function fail(action, error) {
  return { ok: false, action, result: {}, error }
}

function getStatus() {
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
    nearbyBlocks: nearbyBlocksJson()
  }
}

function inventoryJson() {
  if (!bot.inventory || !Array.isArray(bot.inventory.slots)) {
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
  if (!bot.time) {
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
    distance: bot.entity ? bot.entity.position.distanceTo(block.position) : null
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
    distance: bot.entity && entity.position ? bot.entity.position.distanceTo(entity.position) : null
  }
}

function nearbyBlocksJson() {
  return {
    crafting_table: blockJson(findNearbyCraftingTable(4))
  }
}

function nearbyPlayersJson(radius) {
  if (!bot.entity) {
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
  if (!bot.entity || !bot.entities) {
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
  if (!bot.entity) {
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
    return fail(actionName(request), validation.error)
  }

  const action = request.action
  const args = request.args === undefined ? {} : request.args

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

    case 'craft_wooden_pickaxe':
      return await craftWoodenPickaxe()

    case 'mine_stone':
      return await mineStone(args.count)

    case 'craft_stone_pickaxe':
      return await craftStonePickaxe()

    case 'flee':
      return await flee()

    case 'eat_food':
      return await eatFood()

    default:
      return fail(action, `Unsupported action: ${action}`)
  }
}

function validateActionRequest(request) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    return { ok: false, error: 'Action request must be an object.' }
  }

  if (!ACTIONS.has(request.action)) {
    return { ok: false, error: `Unsupported action: ${request.action}` }
  }

  const args = request.args === undefined ? {} : request.args

  if (!isPlainObject(args)) {
    return { ok: false, error: 'Action args must be an object.' }
  }

  if (actionHasOnlyArgs(request.action, args) === false) {
    return { ok: false, error: `Action ${request.action} received unsupported args.` }
  }

  if (request.action === 'say') {
    return validateSay(args)
  }

  if (['look_at_player', 'follow_player', 'come_here'].includes(request.action)) {
    return validateOptionalUsername(request.action, args)
  }

  if (request.action === 'set_vtuber_mood') {
    return validateMood(args)
  }

  if (request.action === 'collect_wood') {
    return validateCount(args, 'collect_wood', COLLECT_WOOD_MAX_COUNT)
  }

  if (request.action === 'acquire_blocks') {
    return validateAcquireBlocks(args)
  }

  if (request.action === 'navigate_to_block_type') {
    return validateNavigateToBlockType(args)
  }

  if (request.action === 'mine_stone') {
    return validateCount(args, 'mine_stone', MINE_STONE_MAX_COUNT)
  }

  if (request.action === 'explore_nearby') {
    return validateRange(args, 'explore_nearby', 'radius', 8, EXPLORE_MAX_RADIUS)
  }

  if (request.action === 'look_around') {
    return validateRange(args, 'look_around', 'radius', 8, LOOK_AROUND_MAX_RADIUS)
  }

  if (['craft_planks', 'craft_sticks', 'craft_crafting_table'].includes(request.action)) {
    return validateCraftCount(request.action, args)
  }

  return { ok: true }
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
    craft_wooden_pickaxe: [],
    mine_stone: ['count'],
    craft_stone_pickaxe: [],
    flee: [],
    eat_food: []
  }[action]

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
  const target = findSafeExplorePosition(radius)
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

  const candidate = findSurfaceNavigationCandidate(targetSet, radius, diagnostics)
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
    return {
      ok: false,
      action: 'navigate_to_block_type',
      result: {
        targets,
        radius,
        target: blockJson(candidate.block),
        standPosition: positionJson(candidate.standPosition),
        ...navigationDiagnostics(diagnostics)
      },
      error: `Navigation path failed: ${errorMessage(error)}`
    }
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
    exposedCandidatesFound: diagnostics.exposedCandidatesFound,
    accessCandidatesFound: diagnostics.accessCandidatesFound,
    rejectedDangerous: diagnostics.rejectedDangerous,
    rejectedProtected: diagnostics.rejectedProtected,
    rejectedUnsupported: diagnostics.rejectedUnsupported,
    rejectedNoSafeStand: diagnostics.rejectedNoSafeStand,
    rejectedUnreachable: diagnostics.rejectedUnreachable
  }
}

async function acquireBlocksForAction(actionName, options) {
  try {
    return await withTimeout(acquireBlocksCore(actionName, options), ACQUIRE_BLOCKS_TIMEOUT_MS, actionName)
  } catch (error) {
    const result = emptyAcquireResult(options, 'failed')
    result.can_retry = true
    result.suggested_next_action = 'acquire_blocks'
    result.stop_reason = 'action_timeout'
    result.inventory = inventoryJson()

    return {
      ok: false,
      action: actionName,
      result,
      error: `Block acquisition failed: ${errorMessage(error)}`
    }
  }
}

async function acquireBlocksCore(actionName, options) {
  const targets = options.targets.filter((target) => ACQUIRE_ALLOWED_TARGETS.has(target))
  const targetSet = new Set(targets)
  const requested = Math.max(1, Math.min(options.count, ACQUIRE_BLOCKS_MAX_COUNT))
  const radius = Math.max(ACQUIRE_BLOCKS_MIN_RADIUS, Math.min(options.radius, ACQUIRE_BLOCKS_MAX_RADIUS))
  const allowExcavate = options.allowExcavate === true
  const accessMode = ACQUIRE_ACCESS_MODES.has(options.accessMode) ? options.accessMode : 'surface_first'
  const diagnostics = emptyAcquireResult({ targets, count: requested }, 'failed')
  const startingCount = inventoryCountForTargets(targets)
  const targetInventoryCount = startingCount + requested
  const targetLabel = targets.length === 1 ? targets[0] : 'target block'
  const ignoredPositions = new Set()
  let attempts = 0
  let staircaseSteps = 0
  let lastError = null

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

  while (inventoryCountForTargets(targets) < targetInventoryCount && attempts < ACQUIRE_MAX_ATTEMPTS) {
    if (typeof bot.health === 'number' && bot.health <= MINE_STONE_MIN_HEALTH) {
      lastError = `Health too low for block acquisition: ${bot.health}.`
      break
    }

    const candidate = findSurfaceAcquisitionCandidate(targetSet, radius, ignoredPositions, diagnostics)
    if (candidate) {
      attempts++
      ignoredPositions.add(positionKey(candidate.block.position))

      try {
        diagnostics.strategy = bot.entity.position.distanceTo(candidate.standPosition) <= 2.5
          ? 'immediate_surface'
          : 'moved_to_surface'
        diagnostics.last_target_position = positionJson(candidate.block.position)
        diagnostics.last_stand_position = positionJson(candidate.standPosition)
        await approachTarget(candidate.block, candidate.standPosition)
      } catch (error) {
        lastError = errorMessage(error)
        diagnostics.rejectedUnreachable += 1
        stopMovement()
        diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
        diagnostics.inventory = inventoryJson()
        diagnostics.can_retry = true
        diagnostics.suggested_next_action = 'navigate_to_block_type'
        diagnostics.stop_reason = 'path_timeout_before_target'
        diagnostics.partial_success = diagnostics.collected > 0

        return {
          ok: diagnostics.collected > 0,
          action: actionName,
          result: diagnostics,
          error: diagnostics.collected > 0 ? null : lastError
        }
      }

      try {
        await mineBlockSafe(candidate.block, targetSet)
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
      staircaseSteps < ACQUIRE_MAX_STEPS
    ) {
      const target = findNearestExcavationTarget(targetSet, radius, ignoredPositions, diagnostics)
      if (!target) {
        lastError = stopReasonMessage(targetLabel, diagnostics)
        diagnostics.stop_reason = stopReasonForNoCandidate(diagnostics)
        diagnostics.suggested_next_action = suggestedActionForStopReason(diagnostics.stop_reason)
        diagnostics.can_retry = diagnostics.suggested_next_action !== 'explore_nearby'
        break
      }

      diagnostics.last_target_position = positionJson(target.position)
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

  diagnostics.collected = Math.max(0, inventoryCountForTargets(targets) - startingCount)
  diagnostics.inventory = inventoryJson()

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

  if (diagnostics.collected < requested) {
    diagnostics.partial_success = true
    diagnostics.can_retry = true
    diagnostics.suggested_next_action = 'acquire_blocks'
    diagnostics.stop_reason = diagnostics.stop_reason || 'partial_count_not_reached'
  } else {
    diagnostics.partial_success = false
    diagnostics.can_retry = false
    diagnostics.suggested_next_action = null
    diagnostics.stop_reason = 'completed'
  }

  return ok(actionName, diagnostics)
}

function emptyAcquireResult(options, strategy) {
  return {
    requested: options.count || ACQUIRE_BLOCKS_DEFAULT_COUNT,
    collected: 0,
    partial_success: false,
    can_retry: false,
    suggested_next_action: null,
    last_target_position: null,
    last_stand_position: null,
    stop_reason: null,
    targets: options.targets || [],
    strategy,
    targetCandidatesFound: 0,
    exposedCandidatesFound: 0,
    accessCandidatesFound: 0,
    excavatedBlocks: 0,
    rejectedDangerous: 0,
    rejectedProtected: 0,
    rejectedUnsupported: 0,
    rejectedNoSafeStand: 0,
    rejectedUnreachable: 0,
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

function isTargetBlock(block, targets) {
  return Boolean(block && targets.has(block.name))
}

function findTargetCandidates(targets, radius, diagnostics) {
  const matching = Array.from(targets)
    .map((name) => bot.registry.blocksByName[name])
    .filter((blockType) => blockType)
    .map((blockType) => blockType.id)

  if (matching.length === 0) {
    diagnostics.rejectedUnsupported += 1
    return []
  }

  const positions = bot.findBlocks({
    matching,
    maxDistance: radius,
    count: 256
  }) || []

  diagnostics.targetCandidatesFound += positions.length

  return positions
    .map((position) => bot.blockAt(position))
    .filter((block) => block && isTargetBlock(block, targets))
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))
}

function findSurfaceAcquisitionCandidate(targets, radius, ignoredPositions, diagnostics) {
  for (const block of findTargetCandidates(targets, radius, diagnostics)) {
    if (ignoredPositions.has(positionKey(block.position))) {
      continue
    }

    if (isProtectedBlock(block)) {
      diagnostics.rejectedProtected += 1
      continue
    }

    if (isDirectlyUnderBot(block)) {
      diagnostics.rejectedDangerous += 1
      continue
    }

    if (!canMineBlock(block)) {
      diagnostics.rejectedUnsupported += 1
      continue
    }

    if (isDangerousAdjacent(block)) {
      diagnostics.rejectedDangerous += 1
      continue
    }

    const faceInfo = findExposedFace(block)
    if (!faceInfo) {
      diagnostics.rejectedUnreachable += 1
      continue
    }
    diagnostics.exposedCandidatesFound += 1

    const standPosition = findSafeStandNearFace(block, faceInfo)
    if (!standPosition) {
      diagnostics.rejectedNoSafeStand += 1
      continue
    }
    diagnostics.accessCandidatesFound += 1

    return { block, faceInfo, standPosition }
  }

  return null
}

function findSurfaceNavigationCandidate(targets, radius, diagnostics) {
  for (const block of findTargetCandidates(targets, radius, diagnostics)) {
    if (isProtectedBlock(block)) {
      diagnostics.rejectedProtected += 1
      continue
    }

    if (isDirectlyUnderBot(block) || isDangerousAdjacent(block)) {
      diagnostics.rejectedDangerous += 1
      continue
    }

    const faceInfo = findExposedFace(block)
    if (!faceInfo) {
      diagnostics.rejectedUnreachable += 1
      continue
    }
    diagnostics.exposedCandidatesFound += 1

    const standPosition = findSafeStandNearFace(block, faceInfo)
    if (!standPosition) {
      diagnostics.rejectedNoSafeStand += 1
      continue
    }
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

function findNearestExcavationTarget(targets, radius, ignoredPositions, diagnostics) {
  return findTargetCandidates(targets, radius, diagnostics)
    .filter((block) => !ignoredPositions.has(positionKey(block.position)))
    .filter((block) => !isProtectedBlock(block))
    .filter((block) => !isDirectlyUnderBot(block))
    .filter((block) => canMineBlock(block))
    .filter((block) => !isDangerousAdjacent(block))
    .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position))[0] || null
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

  if (!isSoftExposureBlock(block)) {
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

  if (['stone', 'cobblestone', 'deepslate', 'coal_ore', 'deepslate_coal_ore', 'iron_ore', 'deepslate_iron_ore', 'copper_ore', 'deepslate_copper_ore'].includes(block.name)) {
    return await equipBestPickaxe()
  }

  if (['dirt', 'grass_block', 'sand', 'gravel', 'snow', 'snow_block'].includes(block.name)) {
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
  if (isBotInLiquid()) {
    return fail('place_crafting_table', 'Refusing to place crafting table while bot is in water or lava.')
  }

  const existingTable = findNearbyCraftingTable(4)
  if (existingTable) {
    return ok('place_crafting_table', {
      placed: false,
      alreadyPresent: true,
      position: positionJson(existingTable.position),
      inventory: inventoryJson()
    })
  }

  const tableItem = firstInventoryItemByNames(['crafting_table'])
  if (!tableItem) {
    return fail('place_crafting_table', 'Missing materials: no crafting_table item in inventory.')
  }

  const candidates = findCraftingTableCandidates()
  if (candidates.length === 0) {
    return fail('place_crafting_table', 'No safe adjacent solid block found for crafting table placement.')
  }

  // Stop movement so the server accepts the placement packet
  stopMovement()
  await delay(50)

  for (const candidate of candidates) {
    // Re-fetch blocks before placing in case another action changed the world.
    const freshRef = bot.blockAt(candidate.referenceBlock.position)
    if (!isSolidBlock(freshRef)) continue
    const freshPlace = bot.blockAt(candidate.placePosition)
    if (!canReplaceBlock(freshPlace)) continue

    try {
      await bot.equip(tableItem, 'hand')
      // Look at the center of the top face of the reference block — the face being clicked
      await bot.lookAt(freshRef.position.offset(0.5, 1.0, 0.5), true)
      await delay(100)
      await placeBlockWithTimeout(freshRef, candidate.faceVector, PLACE_CRAFTING_TABLE_TIMEOUT_MS)
    } catch (error) {
      // blockUpdate race condition: the server placed the block but the event arrived
      // before mineflayer's listener was registered — verify the block actually exists
      const verified = await waitForCraftingTable(candidate.placePosition, PLACE_CRAFTING_TABLE_VERIFY_MS)
      if (verified) {
        return ok('place_crafting_table', {
          placed: true,
          position: positionJson(candidate.placePosition),
          verifiedAfterError: true,
          inventory: inventoryJson()
        })
      }

      return fail(
        'place_crafting_table',
        `Placement uncertain at ${positionKey(candidate.placePosition)} after server update timeout: ${errorMessage(error)}. Check /status before retrying.`
      )
    }

    const verified = await waitForCraftingTable(candidate.placePosition, PLACE_CRAFTING_TABLE_VERIFY_MS)
    if (!verified) {
      return fail(
        'place_crafting_table',
        `Placement packet completed for ${positionKey(candidate.placePosition)}, but no crafting_table was verified nearby. Check /status before retrying.`
      )
    }

    return ok('place_crafting_table', {
      placed: true,
      position: positionJson(candidate.placePosition),
      inventory: inventoryJson()
    })
  }

  return fail('place_crafting_table', 'No currently valid safe adjacent block found for crafting table placement.')
}

async function craftWoodenPickaxe() {
  const craftingTable = findNearbyCraftingTable(4)
  if (!craftingTable) {
    return fail('craft_wooden_pickaxe', 'No crafting table found within radius 4.')
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

async function craftStonePickaxe() {
  const craftingTable = findNearbyCraftingTable(4)
  if (!craftingTable) {
    return fail('craft_stone_pickaxe', 'No crafting table found within radius 4.')
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

function craftWithTimeout(recipe, count, craftingTable) {
  const timeoutMs = CRAFT_TIMEOUT_MS + (count * 2000)
  return withTimeout(bot.craft(recipe, count, craftingTable), timeoutMs, 'crafting')
}

function withTimeout(promise, ms, label) {
  let timeoutId = null
  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Timed out ${label} after ${ms}ms.`))
    }, ms)
  })

  return Promise.race([promise, timeout]).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
  })
}

function gotoNearBlockWithTimeout(block, timeoutMs) {
  let timeoutId = null
  const goal = new goals.GoalNear(block.position.x, block.position.y, block.position.z, 2)

  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Timed out pathing near ${block.name} after ${timeoutMs}ms.`))
    }, timeoutMs)
  })

  return Promise.race([bot.pathfinder.goto(goal), timeout]).finally(() => {
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
  let timeoutId = null
  const goal = new goals.GoalNear(position.x, position.y, position.z, 2)

  const timeout = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Timed out pathing after ${timeoutMs}ms.`))
    }, timeoutMs)
  })

  return Promise.race([bot.pathfinder.goto(goal), timeout]).finally(() => {
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

    const nearby = findNearbyCraftingTable(4)
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

function findSafeExplorePosition(radius) {
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

function findCraftingTableCandidates() {
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

function positionKey(position) {
  return `${position.x},${position.y},${position.z}`
}

function stopMovement() {
  bot.pathfinder.setGoal(null)
  bot.clearControlStates()
}

function shortJump() {
  bot.setControlState('jump', true)
  setTimeout(() => {
    bot.setControlState('jump', false)
  }, 350)
}
