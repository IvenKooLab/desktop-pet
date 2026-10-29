// Same precedence as comi_home.py and native ComiHome; never migrate user data.
import { statSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'

export function dataRoot() {
  const home = homedir()
  const override = process.env.COMI_HOME || process.env.IVEN_HOME
  if (override) {
    if (override === '~') return home
    return override.startsWith('~/') || override.startsWith('~\\')
      ? join(home, override.slice(2)) : override
  }
  const legacy = join(home, '.iven-pet')
  try { if (statSync(legacy).isDirectory()) return legacy } catch { /* new installation */ }
  return join(home, '.comi-pet')
}
