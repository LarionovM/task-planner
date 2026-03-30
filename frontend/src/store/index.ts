// Zustand store — глобальное состояние приложения

import { create } from 'zustand'
import type {
  Screen,
  User,
  Category,
  Task,
  TaskBlock,
  Event,
  WeeklyScheduleItem,
  WeeklyGoal,
  SpamConfig,
} from '../types'
import { api } from '../api/client'

interface AppState {
  // Навигация
  screen: Screen
  setScreen: (s: Screen) => void

  // Защита от потери несохранённых изменений
  hasUnsavedChanges: boolean
  setHasUnsavedChanges: (v: boolean) => void
  pendingScreen: Screen | null
  setPendingScreen: (s: Screen | null) => void
  confirmNavigation: () => void
  cancelNavigation: () => void

  // Пользователь
  user: User | null
  loadUser: () => Promise<void>
  updateSettings: (data: Partial<User>) => Promise<void>

  // Категории
  categories: Category[]
  loadCategories: () => Promise<void>

  // Задачи
  tasks: Task[]
  loadTasks: () => Promise<void>

  // События
  events: Event[]
  loadEvents: () => Promise<void>

  // Блоки
  blocks: TaskBlock[]
  weekStart: string
  setWeekStart: (ws: string) => void
  loadBlocks: () => Promise<void>

  // Расписание
  schedule: WeeklyScheduleItem[]
  loadSchedule: () => Promise<void>

  // Цели
  goals: WeeklyGoal[]
  loadGoals: () => Promise<void>

  // Спам
  spamConfig: SpamConfig | null
  loadSpamConfig: () => Promise<void>

  // Загрузка
  loading: boolean
  error: string | null
}

// Форматирование даты в YYYY-MM-DD без сдвига часового пояса
function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// Понедельник текущей недели
function getMonday(): string {
  const d = new Date()
  const day = d.getDay()
  const diff = d.getDate() - day + (day === 0 ? -6 : 1)
  const monday = new Date(d.setDate(diff))
  return formatLocalDate(monday)
}

export const useStore = create<AppState>((set, get) => ({
  screen: 'calendar',
  setScreen: (s) => {
    const state = get()
    if (state.hasUnsavedChanges) {
      // Не переключаем экран — показываем диалог
      set({ pendingScreen: s })
    } else {
      set({ screen: s })
    }
  },

  hasUnsavedChanges: false,
  setHasUnsavedChanges: (v) => set({ hasUnsavedChanges: v }),
  pendingScreen: null,
  setPendingScreen: (s) => set({ pendingScreen: s }),
  confirmNavigation: () => {
    const { pendingScreen } = get()
    if (pendingScreen) {
      set({ screen: pendingScreen, pendingScreen: null, hasUnsavedChanges: false })
    }
  },
  cancelNavigation: () => set({ pendingScreen: null }),

  user: null,
  loadUser: async () => {
    try {
      const user = await api.getUser()
      set({ user })
      // Если TZ ещё не настроен (дефолт) — показать экран TZ
      // Проверяем по наличию настроек
    } catch (e: any) {
      set({ error: e.message })
    }
  },
  updateSettings: async (data) => {
    try {
      const user = await api.updateSettings(data)
      set({ user })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  categories: [],
  loadCategories: async () => {
    try {
      const categories = await api.getCategories()
      set({ categories })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  tasks: [],
  loadTasks: async () => {
    try {
      const tasks = await api.getTasks()
      set({ tasks })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  events: [],
  loadEvents: async () => {
    try {
      const events = await api.getEvents(get().weekStart)
      set({ events })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  blocks: [],
  weekStart: getMonday(),
  setWeekStart: (ws) => set({ weekStart: ws }),
  loadBlocks: async () => {
    try {
      const blocks = await api.getBlocks(get().weekStart)
      set({ blocks })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  schedule: [],
  loadSchedule: async () => {
    try {
      const schedule = await api.getSchedule()
      set({ schedule })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  goals: [],
  loadGoals: async () => {
    try {
      const goals = await api.getGoals()
      set({ goals })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  spamConfig: null,
  loadSpamConfig: async () => {
    try {
      const spamConfig = await api.getSpamConfig()
      set({ spamConfig })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  loading: false,
  error: null,
}))
