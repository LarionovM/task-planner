// Типы данных — соответствуют backend API схемам

export interface User {
  telegram_id: number
  timezone: string
  quiet_start: string // HH:MM
  quiet_end: string
  day_start_time: string
  day_end_time: string
  is_admin: boolean
  is_active: boolean
}

export interface Category {
  id: number
  name: string
  emoji: string | null
  color: string | null
  sort_order: number
}

export interface Task {
  id: number
  name: string
  category_id: number
  minimal_time_min: number
  estimated_time_min: number | null
  priority: 'high' | 'medium' | 'low'
  use_pomodoro: boolean
  is_recurring: boolean
  recur_days: number[]
  preferred_time: string | null // HH:MM — предпочтительное время для автораспределения
  deadline: string | null
  tags: string[]
  depends_on: number[]
  reminder_before_min: number
  allow_grouping: boolean
  spam_enabled: boolean
  allow_multi_per_block: boolean
  device_type: 'desktop' | 'mobile' | 'other'
  is_epic: boolean
  epic_id: number | null
  epic_emoji: string | null
  created_at: string
}

export interface TaskBlock {
  id: number
  task_ids: number[]
  block_name: string | null
  day: string // YYYY-MM-DD
  start_time: string // HH:MM
  duration_type: 'fixed' | 'open' | 'range'
  duration_min: number | null
  min_duration_min: number | null
  max_duration_min: number | null
  actual_start_at: string | null
  actual_end_at: string | null
  actual_duration_min: number | null
  status: 'planned' | 'active' | 'done' | 'skipped' | 'failed'
  is_mixed: boolean
  notes: string | null
}

export interface BlockWarning {
  type: string
  message: string
  block_id?: number
}

export interface WeeklyScheduleItem {
  day_of_week: number // 0=Пн, 6=Вс
  is_day_off: boolean
  active_from: string
  active_to: string
}

export interface WeeklyGoal {
  category_id: number
  target_hours: number
}

export interface SpamConfig {
  initial_interval_sec: number
  multiplier: number
  max_interval_sec: number
  enabled: boolean
  spam_category_ids: number[]
  empty_slots_enabled: boolean
  empty_slots_interval_min: number
}

export interface CategoryStats {
  category_id: number
  category_name: string
  category_emoji: string | null
  planned_min: number
  actual_min: number
  target_hours: number
}

export interface WeekStats {
  week_start: string
  blocks_done: number
  blocks_partial: number
  blocks_failed: number
  blocks_skipped: number
  blocks_planned: number
  categories: CategoryStats[]
  total_planned_min: number
  total_actual_min: number
  free_time_min: number
  overload_percent: number
  upcoming_deadlines: { task_id: number; task_name: string; deadline: string }[]
}

// Экраны приложения
export type Screen =
  | 'timezone'
  | 'categories'
  | 'schedule'
  | 'goals'
  | 'backlog'
  | 'calendar'
  | 'summary'
  | 'settings'
