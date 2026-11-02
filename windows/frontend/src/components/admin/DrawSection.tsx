import { useEffect, useRef, useState } from 'react'
import { getJob, postJob, postSketch } from '../../lib/api'
import type { AdminStatus, SketchResponse } from '../../lib/api'

const ACCEPT = ['image/jpeg', 'image/png', 'image/webp']

type Source = 'photo' | 'ink'

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(new Error('no se pudo leer el archivo'))
    reader.readAsDataURL(file)
  })
}

function secondsOf(sketch: SketchResponse): number | null {
  const value = Number(sketch.stats.est_total_seconds)
  return Number.isFinite(value) ? value : null
}

/** Sube una imagen, muestra el dibujo que saldría y solo entonces mueve el brazo. */
export function DrawSection({ status }: { status: AdminStatus | null }) {
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [fileName, setFileName] = useState('')
  const [image, setImage] = useState<string | null>(null)
  const [sketch, setSketch] = useState<SketchResponse | null>(null)
  const [source, setSource] = useState<Source | null>(null)
  const [preparing, setPreparing] = useState<Source | null>(null)
  const [error, setError] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [jobStatus, setJobStatus] = useState<'drawing' | 'done' | 'error' | null>(null)

  const busy = Boolean(status?.busy) || jobStatus === 'drawing'

  useEffect(() => {
    if (!jobId || jobStatus === 'done' || jobStatus === 'error') return
    let stop = false
    const tick = async () => {
      try {
        const job = await getJob(jobId)
        if (stop) return
        setProgress(job.progress)
        if (job.status === 'done' || job.status === 'error') {
          setJobStatus(job.status)
          if (job.error) setError(job.error)
        }
      } catch (reason) {
        if (!stop) setError(reason instanceof Error ? reason.message : 'se perdió el trabajo')
      }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 1000)
    return () => {
      stop = true
      window.clearInterval(timer)
    }
  }, [jobId, jobStatus])

  async function choose(file: File | undefined) {
    if (!file) return
    if (!ACCEPT.includes(file.type)) {
      setError('Usa un jpg, png o webp.')
      return
    }
    setError('')
    setSketch(null)
    setSource(null)
    setJobId(null)
    setJobStatus(null)
    setProgress(0)
    setFileName(file.name)
    try {
      setImage(await readFile(file))
    } catch (reason) {
      setImage(null)
      setError(reason instanceof Error ? reason.message : 'no se pudo leer el archivo')
    }
  }

  async function prepare(next: Source) {
    if (!image || preparing) return
    setPreparing(next)
    setError('')
    setSketch(null)
    setJobId(null)
    setJobStatus(null)
    setProgress(0)
    try {
      const result = await postSketch(image, [], 'caricatura', next, false)
      setSketch(result)
      setSource(next)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'no se pudo preparar el dibujo')
    } finally {
      setPreparing(null)
    }
  }

  async function draw() {
    if (!sketch || busy) return
    setError('')
    try {
      const job = await postJob(sketch.id)
      setJobId(job.job_id)
      setJobStatus('drawing')
      setProgress(0)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'el robot no arrancó')
    }
  }

  const estimate = sketch ? secondsOf(sketch) : null
  const percent = Math.round(Math.min(1, Math.max(0, progress)) * 100)

  return (
    <div className="admin-section admin-draw">
      <section className="admin-card">
        <h3>Imagen</h3>
        <input
          ref={fileRef}
          className="admin-draw-file"
          type="file"
          accept={ACCEPT.join(',')}
          onChange={(event) => {
            void choose(event.target.files?.[0])
            event.target.value = ''
          }}
        />
        <div className="admin-draw-actions">
          <button type="button" className="admin-press" onClick={() => fileRef.current?.click()}>
            Elegir imagen
          </button>
          <button
            type="button"
            className="admin-press"
            disabled={!image || preparing !== null}
            onClick={() => void prepare('photo')}
          >
            {preparing === 'photo' ? 'Preparando…' : 'Retrato con IA'}
          </button>
          <button
            type="button"
            className="admin-press"
            disabled={!image || preparing !== null}
            onClick={() => void prepare('ink')}
          >
            {preparing === 'ink' ? 'Preparando…' : 'Calcar líneas'}
          </button>
        </div>
        <p className="admin-card-note">
          {fileName
            ? fileName
            : 'Retrato con IA hace lo mismo que un visitante, rótulo incluido. Calcar líneas dibuja lo oscuro, sin modelo y sin SYSCOM ROBOTICS.'}
        </p>
        {sketch && (
          <>
            <p className="admin-card-note">
              {source === 'ink' ? 'Calco' : 'Retrato'}
              {estimate !== null ? ` · estimado ${Math.round(estimate)} s` : ''}
              {` · ${sketch.strokes.length} trazos`}
            </p>
            <button type="button" className="admin-press" disabled={busy} onClick={() => void draw()}>
              {jobStatus === 'drawing' ? `Dibujando ${percent}%` : 'Dibujar en el papel'}
            </button>
            {jobStatus === 'drawing' && (
              <span className="admin-progress" aria-hidden="true">
                <i style={{ width: `${percent}%` }} />
              </span>
            )}
            {jobStatus === 'done' && <p className="admin-card-note">Terminado en el papel.</p>}
          </>
        )}
        {error && <p className="admin-empty">{error}</p>}
      </section>

      <section className="admin-card admin-draw-sheet">
        <h3>Vista previa</h3>
        {sketch ? (
          <img src={sketch.image} alt="Lo que va a dibujar el robot" />
        ) : image ? (
          <img src={image} alt="Imagen elegida, todavía sin convertir" />
        ) : (
          <p className="admin-empty">Aquí aparece el dibujo antes de mover el brazo.</p>
        )}
      </section>
    </div>
  )
}
