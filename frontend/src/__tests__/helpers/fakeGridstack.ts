/**
 * A stand-in for gridstack in the dashboard edit specs: `vi.mock('gridstack', () =>
 * import('./helpers/fakeGridstack'))`. It keeps the nodes it was given and records each call in
 * `gs`, so a spec can move a panel the way a drop does (`gs.onChange`) and read what the page
 * then asks gridstack to do. A real drag with the mouse is the end-to-end test's job.
 *
 * The edit grid also measures each panel's content with a ResizeObserver, which jsdom does not
 * have: `vi.stubGlobal('ResizeObserver', FakeResizeObserver)`, then `resize(el, height)` reports a
 * new content height the way the browser does.
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
  /** the elements the page measures, and how many times it stopped measuring all of them */
  observed: new Set<Element>(),
  disconnected: 0,
  /** what `top` mode does to the stored places as the grid starts */
  compact: (nodes: FakeNode[]) => nodes,
  /** what `top` mode does to a panel that the page adds: no change event follows */
  pack: (node: FakeNode) => node,
}

export function resetGridstack() {
  Object.assign(gs, { inits: [], nodes: [], onChange: null, updates: [], made: [], removed: [], destroyed: 0 })
  Object.assign(gs, { observed: new Set<Element>(), disconnected: 0 })
  observers.length = 0
  gs.compact = (nodes) => nodes
  gs.pack = (node) => node
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
        gs.nodes.push(gs.pack(nodeOf(item)))
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

const observers: FakeResizeObserver[] = []

export class FakeResizeObserver {
  private readonly els = new Set<Element>()
  constructor(private readonly cb: ResizeObserverCallback) {
    observers.push(this)
  }
  observe(el: Element) {
    this.els.add(el)
    gs.observed.add(el)
  }
  unobserve(el: Element) {
    this.els.delete(el)
    gs.observed.delete(el)
  }
  disconnect() {
    for (const el of this.els) gs.observed.delete(el)
    this.els.clear()
    gs.disconnected++
  }
  report(el: Element, height: number) {
    if (!this.els.has(el)) return
    this.cb([{ target: el, contentRect: { height } } as never], this as never)
  }
}

/** the content of `el` is now `height` px tall */
export function resize(el: Element, height: number) {
  for (const o of observers) o.report(el, height)
}
