export type KotlBoard = { name: string; state: string; job_id: number | null; warnings?: string | null }
export type KotlQueued = { job: string; user: string; name: string; state: string; eta: string; used: string; start: string; reason: string }
export type KotlJob = { job_id: number; mode: string; command?: string | null }
export type KotlSnapshot = {
  user: string
  boards: KotlBoard[]
  queue: KotlQueued[]
  running_mine: KotlJob[]
  unread: number
  problem?: string | null
  at: number
}

declare module 'claude-code' {
  interface PluginState {
    'kotl-band': { snapshot: KotlSnapshot | null; isHidden: boolean; error: string | null }
  }
}
