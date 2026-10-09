// Launch the built Electron app for real and make sure it starts and stays up.
// Run after `npm run build`. The Electron binary is downloaded on first require
// (Electron >= 42 does this lazily), so this also proves a fresh clone can launch it
// despite `.npmrc`'s ignore-scripts=true.
import { spawn } from 'node:child_process'
import { console } from 'node:console'
import { createRequire } from 'node:module'
import process from 'node:process'
import { setTimeout } from 'node:timers'

const STAY_UP_MS = 15_000
const require = createRequire(import.meta.url)

const electronPath = require('electron')
console.log(`Launching ${electronPath}`)

const child = spawn(electronPath, ['.'], {
  stdio: ['ignore', 'inherit', 'inherit'],
  env: { ...process.env, ELECTRON_ENABLE_LOGGING: '1' }
})

let exitedEarly = false
child.on('exit', (code, signal) => {
  exitedEarly = true
  console.error(`SMOKE FAIL: Electron exited early (code=${code}, signal=${signal})`)
  process.exit(1)
})

setTimeout(() => {
  if (exitedEarly) return
  child.removeAllListeners('exit')
  child.once('exit', () => {
    console.log('SMOKE OK: Electron stayed up and shut down on request')
    process.exit(0)
  })
  child.kill()
  setTimeout(() => {
    console.error('SMOKE FAIL: Electron did not exit after kill()')
    process.exit(1)
  }, 10_000)
}, STAY_UP_MS)
