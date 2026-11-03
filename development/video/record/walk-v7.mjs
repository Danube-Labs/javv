// Video 7, build a dashboard: make it, add panels, move one, change one, save, read it, and open
// it as a viewer. The walk makes a new dashboard each time, so it runs on any store.
import { BASE, record, sleep } from './common.mjs'

const NAME = 'Platform team'
// tall enough for the whole dashboard: a drag that scrolls the page moves the sticky save bar
// into the middle of a full-page shot
const VIEW = { width: 1440, height: 1500 }

await record('v7', async ({ page: first, shot, hoverShot, settle, switchUser }) => {
  let page = first
  await page.goto(`${BASE}/dashboards?cluster=prod-eu-1`)
  await page.getByRole('heading', { name: 'Dashboards' }).waitFor({ timeout: 20000 })
  await settle()
  const create = page.getByRole('button', { name: 'New dashboard' }).first()
  await shot('list', { create })
  await hoverShot('list', create)

  // 1. the details window: name, sharing, the role, Create
  await create.click()
  const dialog = page.getByRole('dialog').first()
  await dialog.waitFor({ timeout: 10000 })
  await settle()
  const name = dialog.locator('#dash-name')
  const someRoles = dialog.getByRole('button', { name: 'Some roles' })
  await shot('details', { dialog, name })
  await name.click()
  const letters = NAME.split(' ')
  for (let i = 1; i <= letters.length; i++) {
    await name.fill(letters.slice(0, i).join(' '))
    await page.mouse.move(5, 5)
    await sleep(60)
    await shot(`type-${i}`)
  }
  await shot('named', { dialog, someRoles })
  await hoverShot('named', someRoles)
  await someRoles.click()
  const roles = dialog.getByRole('group', { name: 'Roles that can see the dashboard' })
  await roles.waitFor({ timeout: 10000 })
  await settle()
  const viewer = roles.getByRole('button', { name: /^viewer$/i })
  await shot('roles', { dialog, roles, viewer })
  await hoverShot('roles', viewer)
  await viewer.click()
  await settle()
  const opensOn = dialog.getByRole('group', { name: 'Opens on' })
  const createBtn = dialog.getByRole('button', { name: 'Create' })
  await shot('roles-on', { dialog, opensOn, createBtn })
  await hoverShot('roles-on', createBtn)
  await createBtn.click()
  // the empty dashboard has a second Add panel button; the walk uses the one in the head
  const addPanel = page.locator('.head-actions').getByRole('button', { name: 'Add panel' })
  await addPanel.waitFor({ timeout: 15000 })
  await settle()

  // 2. the catalog: pick a panel, see its preview, add it; then two more
  await shot('empty', { addPanel })
  await hoverShot('empty', addPanel)
  const panels = ['Findings summary', 'Findings by namespace', 'Top components']
  for (const [i, panel] of panels.entries()) {
    await addPanel.click()
    const cat = page.getByRole('dialog').first()
    await cat.waitFor({ timeout: 10000 })
    await settle()
    const row = cat.locator('.cat-row').filter({ hasText: panel })
    if (i === 0) {
      await shot('catalog', { cat, row, list: cat.locator('.cat-list') })
      await hoverShot('catalog', row)
    }
    await row.click()
    await settle()
    const preview = cat.locator('.cat-detail')
    const half = cat.getByRole('group', { name: 'Width' }).getByRole('button').first()
    const add = cat.getByRole('button', { name: 'Add panel' })
    await shot(`picked-${i + 1}`, { cat, preview, half, add })
    await hoverShot(`picked-${i + 1}`, add)
    await add.click()
    await cat.waitFor({ state: 'detached', timeout: 10000 })
    await settle()
    await shot(`added-${i + 1}`, { addPanel, grid: page.locator('.grid-stack') })
    if (i < panels.length - 1) await hoverShot(`added-${i + 1}`, addPanel)
  }

  // 3. drag the second half panel to the free column at the right of the first one
  const grid = page.locator('.grid-stack')
  const move = page.getByRole('button', { name: `Move ${panels[2]}`, exact: true })
  await shot('before-drag', { move, grid })
  await hoverShot('before-drag', move)
  const from = await move.boundingBox()
  const start = { x: from.x + from.width / 2, y: from.y + from.height / 2 }
  const beside = await page.locator('.grid-stack-item').filter({ has: page.getByRole('button', { name: `Move ${panels[1]}`, exact: true }) }).boundingBox()
  const end = { x: start.x + beside.width, y: beside.y + 20 }
  await page.mouse.move(start.x, start.y)
  await page.mouse.down()
  const steps = 6
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(start.x + ((end.x - start.x) * i) / steps, start.y + ((end.y - start.y) * i) / steps, { steps: 4 })
    await sleep(150)
    await shot(`drag-${i}`)
  }
  await page.mouse.up()
  await settle()
  await shot('dropped', { moved: page.getByRole('button', { name: `Move ${panels[2]}`, exact: true }), grid })
}, { view: VIEW })
