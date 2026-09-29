import { Boxes, FileCheck2, Package, PackageCheck, RotateCcw, Wrench } from 'lucide-react'
import { Header, Note, Pill } from './shared'

const list = [
  { name: 'Receiving', icon: Package, detail: 'Order and inbound records', status: 'Not connected' },
  { name: 'Prep', icon: Wrench, detail: 'Preparation and unit identifiers', status: 'Not connected' },
  { name: 'Pack', icon: Boxes, detail: 'Outbound packaging events', status: 'Not connected' },
  { name: 'Returns (this workspace)', icon: RotateCcw, detail: 'Batch upload, inspection and disposition', status: 'This workspace' },
  { name: 'Recovery', icon: PackageCheck, detail: 'Disposition handoff via the evidence contract', status: 'Not connected' },
] as const

export default function Integrations() {
  return (
    <>
      <Header eyebrow="CONFIGURATION / ECOSYSTEM" title="Integrations" subtitle="This workspace's own API surface, and the wider CUBE recovery pods it is not yet connected to." />
      <section className="panel flow-panel">
        <div className="panel-head">
          <div>
            <h2>Operational flow</h2>
            <p>Round 2 is a solo build - the other pods listed here are not built yet.</p>
          </div>
          <Pill value="Real" />
        </div>
        <div className="flow">
          {list.map(({ name, icon: Icon, detail, status }) => (
            <div className={status === 'This workspace' ? 'flow-item is-current' : 'flow-item'} key={name}>
              <span>
                <Icon size={19} />
              </span>
              <b>{name}</b>
              <small>{detail}</small>
              <i>{status}</i>
            </div>
          ))}
        </div>
      </section>
      <section className="panel contract">
        <FileCheck2 size={19} />
        <div>
          <b>Recovery Manager data contract</b>
          <small>
            Final disposition, identity, missing components, condition findings, evidence record, and
            claim-support signals - exposed as JSON via GET /api/v1/batch/jobs/&#123;id&#125;/rows/&#123;record&#125;/detail.
          </small>
        </div>
      </section>
      <Note>No fabricated "connected" states - a pod is only marked connected once a real call to it succeeds.</Note>
    </>
  )
}
