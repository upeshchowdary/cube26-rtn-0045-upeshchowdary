import { useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowUpRight, BadgeCheck, Boxes, Package } from 'lucide-react'
import { useBatchStore } from '../lib/store'
import { distinctSkus } from '../lib/derive'
import { Header, Metric, Note } from './shared'

export default function Catalogue() {
  const [query, setQuery] = useState('')
  const { rows } = useBatchStore()
  const products = distinctSkus(rows).filter((p) => p.sku.toLowerCase().includes(query.toLowerCase()))

  return (
    <>
      <Header
        eyebrow="RECORDS / PRODUCT DATA"
        title="Product catalogue"
        subtitle="Every SKU seen across processed batch uploads, shown with the first returned photo on file for it."
      />
      <div className="metrics compact-metrics">
        <Metric label="Distinct SKUs" value={String(products.length)} note="Seen in processed returns" icon={Boxes} tone="teal" />
        <Metric label="Total returns" value={String(rows.length)} note="Across all SKUs" icon={Package} tone="blue" />
      </div>
      <section className="panel catalogue-panel">
        <div className="panel-head">
          <div>
            <h2>Products</h2>
            <p>Built from real batch job output - not a separate catalogue import.</p>
          </div>
          <label className="table-search">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search catalogue..." />
          </label>
        </div>
        <div className="product-grid">
          {products.map((p, i) => (
            <motion.div key={p.sku} className="product-card" initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <div>
                {p.image ? <img src={p.image} alt={p.sku} /> : <Package size={28} />}
                <span>{p.asin || 'no ASIN'}</span>
                <ArrowUpRight size={15} />
              </div>
              <b>{p.sku}</b>
              <small>{p.count} return(s) processed</small>
              <span className="catalogue-status">
                <BadgeCheck size={13} /> seen in real batch output
              </span>
            </motion.div>
          ))}
        </div>
        {products.length === 0 && (
          <div className="empty">
            <Boxes size={22} />
            <b>No products yet</b>
            <span>Upload a batch file to populate the catalogue.</span>
          </div>
        )}
      </section>
      <Note>Each image is the first returned-photo URL from a row with that SKU, not a before-sale reference photo.</Note>
    </>
  )
}
