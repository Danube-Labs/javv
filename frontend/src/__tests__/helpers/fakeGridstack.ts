/**
 * A stand-in for gridstack in the dashboard edit specs: `vi.mock('gridstack', () =>
 * import('./helpers/fakeGridstack'))`. It keeps the nodes it was given and records each call in
 * `gs`, so a spec can move a panel the way a drop does (`gs.onChange`) and read what the page
 * then asks gridstack to do. A real drag with the mouse is the end-to-end test's job.
 */
export interface FakeNode {
  id: string
  x: number
  y: number
  w: number
  h: number
  el: HTMLElement
}

export const gs = {
  inits: [] as Record<string, unknown>[],
  nodes: [] as FakeNode[],
  onChange: null as null | ((event: unknown, nodes: FakeNode[]) => void),
  updates: [] as { id: string; opts: Record<string, number> }[],
  made: [] as string[],
  removed: [] as string[],
  destroyed: 0,
  /** what `top` mode does to the stored places as the grid starts */
  compact: (nodes: FakeNode[]) => nodes,
}

export function resetGridstack() {
  Object.assign(gs, { inits: [], nodes: [], onChange: null, updates: [], made: [], removed: [], destroyed: 0 })
  gs.compact = (nodes) => nodes
}

const nodeOf = (el: HTMLElement): FakeNode => ({
  id: el.getAttribute('gs-id')!,
  x: Number(el.getAttribute('gs-x')),
  y: Number(el.getAttribute('gs-y')),
  w: Number(el.getAttribute('gs-w')),
  h: Number(el.getAttribute('gs-h')),
  el,
})

export const GridStack = {
  init(opts: Record<string, unknown>, el: HTMLElement) {
    gs.inits.push(opts)
    gs.nodes = gs.compact([...el.querySelectorAll<HTMLElement>('.grid-stack-item')].map(nodeOf))
    return {
      engine: {
        get nodes() {
          return gs.nodes
        },
      },
      on: (_event: string, cb: (event: unknown, nodes: FakeNode[]) => void) => {
        gs.onChange = cb
      },
      batchUpdate: () => undefined,
      makeWidget: (item: HTMLElement) => {
        gs.made.push(item.getAttribute('gs-id')!)
        gs.nodes.push(nodeOf(item))
      },
      removeWidget: (item: HTMLElement) => {
        const node = gs.nodes.find((n) => n.el === item)!
        gs.removed.push(node.id)
        gs.nodes = gs.nodes.filter((n) => n !== node)
      },
      update: (item: HTMLElement, opts: Record<string, number>) => {
        const node = gs.nodes.find((n) => n.el === item)!
        gs.updates.push({ id: node.id, opts })
        Object.assign(node, opts)
      },
      destroy: () => {
        gs.destroyed++
      },
    }
  },
}
