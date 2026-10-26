import type { ExplorationResult } from '../../api/types'
import { openCode } from './actions'

export default function ExplorationFlow({ flow, stale }: { flow: ExplorationResult['flow']; stale: boolean }) {
  if (!flow) return null
  return <section className="exploration-flow" aria-label="局部流程">
    <p className="exploration-section-label">{flow.title}</p>
    <p className="exploration-muted">静态索引关系 · 不代表运行时执行顺序</p>
    <ol>{flow.nodes.map(node => <li key={node.id}><button disabled={stale} type="button" onClick={() => openCode(node.target)} title={`${node.target.path}:${node.target.lineno}`}>
      <strong>{node.label}</strong>{node.role && <span>{node.role}</span>}
    </button></li>)}</ol>
    <ul className="exploration-connections">{flow.edges.map((edge, i) => <li key={i}>
      {flow.nodes.find(n => n.id === edge.source)?.label} → {flow.nodes.find(n => n.id === edge.target)?.label}
      <span> · {{ call: '静态调用', imports: '导入', inherits: '继承', contains: '包含' }[edge.kind] ?? '结构关联'}{edge.uncertain ? ' · 待核对' : ''}</span>
    </li>)}</ul>
  </section>
}
