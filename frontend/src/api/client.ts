// API клиент — все запросы к backend

// В dev: /api (через Vite proxy). В продакшене: полный URL из env (VITE_API_URL)
const API_BASE = import.meta.env.VITE_API_URL || '/api'

// Получаем Telegram User ID
function getTelegramUserId(): number {
  // Из Telegram Web App SDK
  const tg = (window as any).Telegram?.WebApp
  if (tg?.initDataUnsafe?.user?.id) {
    return tg.initDataUnsafe.user.id
  }
  // Fallback для разработки (без Telegram)
  const params = new URLSearchParams(window.location.search)
  const devId = params.get('user_id')
  if (devId) return parseInt(devId)
  // Дефолт для разработки
  return 295681881
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const userId = getTelegramUserId()
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-User-Id': String(userId),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка сервера' }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// === Users ===
export const api = {
  getUser: () => request<any>('/users/me'),
  updateSettings: (data: any) =>
    request<any>('/users/me/settings', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  getSpamConfig: () => request<any>('/users/me/spam-config'),
  updateSpamConfig: (data: any) =>
    request<any>('/users/me/spam-config', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // === Categories ===
  getCategories: () => request<any[]>('/categories'),
  createCategory: (data: any) =>
    request<any>('/categories', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateCategory: (id: number, data: any) =>
    request<any>(`/categories/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteCategory: (id: number) =>
    request<any>(`/categories/${id}`, { method: 'DELETE' }),
  reassignCategory: (id: number, toId: number) =>
    request<any>(`/categories/${id}/reassign`, {
      method: 'POST',
      body: JSON.stringify({ to_category_id: toId }),
    }),
  reorderCategories: (ids: number[]) =>
    request<any>('/categories/reorder', {
      method: 'POST',
      body: JSON.stringify({ category_ids: ids }),
    }),

  // === Tasks ===
  getTasks: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return request<any[]>(`/tasks${qs}`)
  },
  createTask: (data: any) =>
    request<any>('/tasks', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateTask: (id: number, data: any) =>
    request<any>(`/tasks/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteTask: (id: number) =>
    request<any>(`/tasks/${id}`, { method: 'DELETE' }),

  // === Events ===
  getEvents: (weekStart: string) =>
    request<any[]>(`/events?week_start=${weekStart}`),
  createEvent: (data: any) =>
    request<any>('/events', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateEvent: (id: number, data: any) =>
    request<any>(`/events/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteEvent: (id: number) =>
    request<any>(`/events/${id}`, { method: 'DELETE' }),

  // === Blocks ===
  getBlocks: (weekStart: string) =>
    request<any[]>(`/blocks?week_start=${weekStart}`),
  createBlock: (data: any) =>
    request<any>('/blocks', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateBlock: (id: number, data: any) =>
    request<any>(`/blocks/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteBlock: (id: number) =>
    request<any>(`/blocks/${id}`, { method: 'DELETE' }),
  clearBlocks: (weekStart: string) =>
    request<any>(`/blocks/clear?week_start=${weekStart}`, {
      method: 'DELETE',
    }),
  autoCreateRecurring: (taskId: number, weekStart: string) =>
    request<any>(`/blocks/auto-create-recurring?task_id=${taskId}&week_start=${weekStart}`, {
      method: 'POST',
    }),
  autoDistribute: (weekStart: string) =>
    request<any>(`/blocks/auto-distribute?week_start=${weekStart}`, {
      method: 'POST',
    }),
  carryOver: (fromWeek: string) =>
    request<any>(`/blocks/carry-over?from_week=${fromWeek}`, {
      method: 'POST',
    }),

  // === Schedule ===
  getSchedule: () => request<any[]>('/schedule'),
  updateSchedule: (days: any[]) =>
    request<any[]>('/schedule', {
      method: 'PUT',
      body: JSON.stringify({ days }),
    }),

  // === Goals ===
  getGoals: () => request<any[]>('/goals'),
  updateGoals: (goals: any[]) =>
    request<any[]>('/goals', {
      method: 'PUT',
      body: JSON.stringify({ goals }),
    }),

  // === Stats ===
  getWeekStats: (weekStart: string) =>
    request<any>(`/stats/week?week_start=${weekStart}`),
  getPeriodStats: (period: string, refDate: string) =>
    request<any>(`/stats/period?period=${period}&ref_date=${refDate}`),
}
