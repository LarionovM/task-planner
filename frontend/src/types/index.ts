// Типы данных — соответствуют backend API схемам (v1.2.0)

export interface User {
  telegram_id: number
  timezone: string
  day_start_time: string // HH:MM
  day_end_time: string
  pomodoro_work_min: number
  pomodoro_short_break_min: number
  pomodoro_long_break_min: number
  pomodoro_cycles_before_long: number
  reminders_paused_until: string | null
  reminders_stopped: boolean
  is_admin: boolean
  is_active: boolean
  created_at: string | null
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
  estimated_time_min: number | null
  priority: 'high' | 'medium' | 'low'
  status: 'grooming' | 'in_progress' | 'blocked' | 'done'
  description: string | null
  link: string | null
  is_recurring: boolean
  recur_days: number[]
  scheduled_date: string | null // YYYY-MM-DD
  deadline: string | null
  tags: string[]
  depends_on: number[]
  spam_enabled: boolean
  is_epic: boolean
  epic_id: number | null
  epic_emoji: string | null
  created_at: string
}

export interface Event {
  id: number
  name: string
  day: string // YYYY-MM-DD
  start_time: string // HH:MM
  end_time: string // HH:MM
  category_id: number | null
  task_id: number | null
  reminder_before_min: number
  status: 'planned' | 'active' | 'done'
  notes: string | null
  created_at: string | null
}

export interface TaskBlock {
  id: number
  task_id: number | null
  day: string // YYYY-MM-DD
  start_time: string // HH:MM
  duration_min: number
  actual_start_at: string | null
  actual_end_at: string | null
  actual_duration_min: number | null
  status: 'planned' | 'active' | 'done' | 'skipped' | 'failed' | 'partial'
  pomodoro_number: number
  notes: string | null
  created_at: string | null
}

export interface BlockWarning {
  type: string
  message: string
  details?: Record<string, unknown>
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
  // Помодоро-статистика
  pomodoros_done: number
  pomodoros_partial: number
  pomodoros_failed: number
  pomodoros_skipped: number
  pomodoros_total: number
  // Задачи
  tasks_done: number
  tasks_in_progress: number
  tasks_total: number
  // По категориям
  categories: CategoryStats[]
  total_planned_min: number
  total_actual_min: number
  free_time_min: number
  overload_percent: number
  upcoming_deadlines: { task_id: number; task_name: string; deadline: string }[]
}

export interface DayStatItem {
  date: string           // YYYY-MM-DD
  pomodoros_done: number
  pomodoros_total: number
  focus_min: number
}

export interface PeriodStatsResponse {
  period: string         // day | week | month
  date_from: string
  date_to: string
  pomodoros_done: number
  pomodoros_partial: number
  pomodoros_failed: number
  pomodoros_skipped: number
  pomodoros_total: number
  focus_min: number
  streak_days: number
  avg_per_day: number
  by_day: DayStatItem[]
  categories: CategoryStats[]
  tasks_done: number
  tasks_in_progress: number
  tasks_total: number
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
