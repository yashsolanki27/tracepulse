import { useEffect, useState } from 'react'

import { listTickets } from './api'

function App() {
  const [tickets, setTickets] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listTickets()
      .then((data) => {
        console.log('TracePulse API /tickets response:', data)
        setTickets(data)
      })
      .catch((err) => {
        console.error('TracePulse API call failed:', err)
        setError(String(err))
      })
  }, [])

  return (
    <main style={{ fontFamily: 'monospace', padding: '1rem' }}>
      <h1>TracePulse — frontend scaffold (wiring test)</h1>
      {error && <p style={{ color: 'red' }}>API error: {error}</p>}
      {tickets === null && !error && <p>Loading tickets…</p>}
      {tickets && (
        <p>
          Fetched {tickets.length} tickets from the TracePulse API — see browser console.
        </p>
      )}
    </main>
  )
}

export default App
