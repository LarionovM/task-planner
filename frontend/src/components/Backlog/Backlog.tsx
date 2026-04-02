// Экран 4: Бэклог задач — CRUD + фильтры + эпики (v1.2.0)

import { useState, useEffect, useMemo } from 'react'
import { useStore } from '../../store'
import { api } from '../../api/client'
import type { Task, Category } from '../../types'
import EmojiPicker from '../EmojiPicker'
import ThemeToggle from '../ThemeToggle'
import './Backlog.css'

const PRIORITY_EMOJI: Record<string, string> = {
  high: '🔴',
  medium: '🟡',
  low: '🟢',
}

const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 }

const STATUS_EMOJI: Record<string, string> = {
  grooming: '🔘',
  in_progress: '🔵',
  blocked: '🔴',
  done: '✅',
}
const STATUS_LABELS: Record<string, string> = {
  grooming: 'Grooming',
  in_progress: 'В работе',
  blocked: 'Заблокировано',
  done: 'Готово',
}

type SortField = 'priority' | 'deadline' | 'category' | 'name' | 'time' | 'created'
type SortDir = 'asc' | 'desc'

const SORT_OPTIONS: { value: SortField; label: string; icon: string }[] = [
  { value: 'priority', label: 'Приоритет', icon: '🔴' },
  { value: 'deadline', label: 'Дедлайн', icon: '📅' },
  { value: 'category', label: 'Категория', icon: '📁' },
  { value: 'name', label: 'Имя', icon: '🔤' },
  { value: 'time', label: 'Время', icon: '⏱' },
  { value: 'created', label: 'Дата создания', icon: '🕐' },
]

export default function Backlog() {
  const { tasks, categories, loadTasks, loadCategories, weekStart } = useStore()
  const [filterCat, setFilterCat] = useState<number | ''>('')
  const [filterPriority, setFilterPriority] = useState<string>('')
  const [filterStatuses, setFilterStatuses] = useState<string[]>(['grooming', 'in_progress', 'blocked'])
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editTask, setEditTask] = useState<Task | null>(null)
  const [deleteTask, setDeleteTask] = useState<Task | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [expandedEpics, setExpandedEpics] = useState<Set<number>>(new Set())
  const [sortField, setSortField] = useState<SortField>('priority')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['recurring', 'onetime']))
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards')

  // Форма
  const [formName, setFormName] = useState('')
  const [formCatId, setFormCatId] = useState<number>(0)
  const [formPriority, setFormPriority] = useState<'high' | 'medium' | 'low'>('medium')
  const [formStatus, setFormStatus] = useState<'grooming' | 'in_progress' | 'blocked' | 'done'>('grooming')
  const [formDescription, setFormDescription] = useState('')
  const [formLink, setFormLink] = useState('')
  const [formScheduledDate, setFormScheduledDate] = useState('')
  const [formHasDeadline, setFormHasDeadline] = useState(false)
  const [formDeadline, setFormDeadline] = useState('')
  const [formEstTime, setFormEstTime] = useState<string>('')
  const [formRecurring, setFormRecurring] = useState(false)
  const [formRecurDays, setFormRecurDays] = useState<number[]>([])
  const [formRecurTime, setFormRecurTime] = useState('')
  const [formRecurDuration, setFormRecurDuration] = useState('')
  const [formDependsOn, setFormDependsOn] = useState<number | ''>('')
  const [formIsEpic, setFormIsEpic] = useState(false)
  const [formEpicId, setFormEpicId] = useState<number | ''>('')
  const [formEpicEmoji, setFormEpicEmoji] = useState('')

  useEffect(() => {
    loadTasks()
    loadCategories()
  }, [])

  // Сортировка
  const sortTaskList = (list: Task[]): Task[] => {
    const dir = sortDir === 'asc' ? 1 : -1
    return [...list].sort((a, b) => {
      switch (sortField) {
        case 'priority':
          return ((PRIORITY_ORDER[a.priority] ?? 1) - (PRIORITY_ORDER[b.priority] ?? 1)) * dir
        case 'deadline': {
          if (!a.deadline && !b.deadline) return 0
          if (!a.deadline) return 1 * dir
          if (!b.deadline) return -1 * dir
          return a.deadline.localeCompare(b.deadline) * dir
        }
        case 'category': {
          const catA = catMap[a.category_id]?.name || ''
          const catB = catMap[b.category_id]?.name || ''
          return catA.localeCompare(catB) * dir
        }
        case 'name':
          return a.name.localeCompare(b.name) * dir
        case 'time':
          return ((a.estimated_time_min || 0) - (b.estimated_time_min || 0)) * dir
        case 'created':
          return (a.created_at || '').localeCompare(b.created_at || '') * dir
        default:
          return 0
      }
    })
  }

  const handleSortClick = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev)
      if (next.has(section)) next.delete(section)
      else next.add(section)
      return next
    })
  }

  // catMap — нужен до sortTaskList и buildEpicGroups
  const catMap = useMemo(() => {
    const m: Record<number, Category> = {}
    categories.forEach((c) => (m[c.id] = c))
    return m
  }, [categories])

  // Фильтрация
  const filtered = useMemo(() => {
    let list = [...tasks]
    if (filterCat) list = list.filter((t) => t.category_id === filterCat)
    if (filterPriority) list = list.filter((t) => t.priority === filterPriority)
    if (filterStatuses.length < Object.keys(STATUS_LABELS).length) {
      list = list.filter((t) => filterStatuses.includes(t.status || 'grooming'))
    }
    if (search) {
      const q = search.toLowerCase()
      list = list.filter((t) => t.name.toLowerCase().includes(q))
    }
    return list
  }, [tasks, filterCat, filterPriority, filterStatuses, search])

  // Разделение на регулярные и разовые
  const recurringTasks = useMemo(() => filtered.filter((t) => !t.is_epic && t.is_recurring), [filtered])
  const onetimeTasks = useMemo(() => filtered.filter((t) => !t.is_epic && !t.is_recurring), [filtered])
  const allEpics = useMemo(() => filtered.filter((t) => t.is_epic), [filtered])

  // Эпики и задачи по эпикам — для каждой секции
  const buildEpicGroups = (taskList: Task[]) => {
    const epicIds = new Set(taskList.map((t) => t.epic_id).filter(Boolean) as number[])
    const sectionEpics = allEpics.filter((e) => epicIds.has(e.id))
    const byEpic: Record<number, Task[]> = {}
    taskList.forEach((t) => {
      if (t.epic_id) {
        if (!byEpic[t.epic_id]) byEpic[t.epic_id] = []
        byEpic[t.epic_id].push(t)
      }
    })
    // Сортируем подзадачи эпиков
    for (const key of Object.keys(byEpic)) {
      byEpic[Number(key)] = sortTaskList(byEpic[Number(key)])
    }
    const standalone = sortTaskList(taskList.filter((t) => !t.epic_id))
    return { sectionEpics, byEpic, standalone }
  }

  const recurringGroups = useMemo(() => buildEpicGroups(recurringTasks), [recurringTasks, sortField, sortDir, catMap])
  const onetimeGroups = useMemo(() => buildEpicGroups(onetimeTasks), [onetimeTasks, sortField, sortDir, catMap])

  // Плоский отсортированный список для табличного вида (без эпиков)
  const flatSorted = useMemo(() => sortTaskList(filtered.filter((t) => !t.is_epic)), [filtered, sortField, sortDir, catMap])

  const availableEpics = useMemo(
    () => tasks.filter((t) => t.is_epic && t.id !== editTask?.id),
    [tasks, editTask]
  )

  const handleAdd = (isEpic = false) => {
    setEditTask(null)
    setFormName('')
    setFormCatId(categories[0]?.id || 0)
    setFormPriority('medium')
    setFormStatus('grooming')
    setFormDescription('')
    setFormLink('')
    setFormScheduledDate('')
    setFormHasDeadline(false)
    setFormDeadline('')
    setFormEstTime('')
    setFormRecurring(false)
    setFormRecurDays([])
    setFormRecurTime('')
    setFormRecurDuration('')
    setFormDependsOn('')
    setFormIsEpic(isEpic)
    setFormEpicId('')
    setFormEpicEmoji('')
    setShowForm(true)
  }

  const handleEdit = (task: Task) => {
    setEditTask(task)
    setFormName(task.name)
    setFormCatId(task.category_id)
    setFormPriority(task.priority)
    setFormStatus(task.status || 'grooming')
    setFormDescription(task.description || '')
    setFormLink(task.link || '')
    setFormScheduledDate(task.scheduled_date || '')
    setFormHasDeadline(!!task.deadline)
    setFormDeadline(task.deadline || '')
    setFormEstTime(task.estimated_time_min?.toString() || '')
    setFormRecurring(task.is_recurring)
    setFormRecurDays(task.recur_days || [])
    setFormRecurTime(task.recur_time || '')
    setFormRecurDuration(task.recur_duration_min?.toString() || '')
    setFormDependsOn(task.depends_on?.[0] || '')
    setFormIsEpic(task.is_epic || false)
    setFormEpicId(task.epic_id || '')
    setFormEpicEmoji(task.epic_emoji || '')
    setShowForm(true)
  }

  const handleSave = async () => {
    if (!formName.trim() || !formCatId) return
    setSaving(true)
    setSaveError(null)
    try {
      const data: any = {
        name: formName.trim(),
        category_id: formCatId,
        priority: formPriority,
        status: formStatus,
        description: formDescription.trim() || null,
        link: formLink.trim() || null,
        scheduled_date: formScheduledDate || null,
        deadline: formHasDeadline && formDeadline ? formDeadline : null,
        estimated_time_min: formEstTime ? parseInt(formEstTime) : null,
        spam_enabled: true,
        is_recurring: formRecurring,
        recur_days: formRecurDays,
        recur_time: formRecurTime || null,
        recur_duration_min: formRecurDuration ? parseInt(formRecurDuration) : null,
        tags: [],
        depends_on: formDependsOn ? [Number(formDependsOn)] : [],
        is_epic: formIsEpic,
        epic_id: formIsEpic ? null : (formEpicId ? Number(formEpicId) : null),
        epic_emoji: formIsEpic ? (formEpicEmoji || null) : null,
      }
      let savedTask: any
      if (editTask) {
        savedTask = await api.updateTask(editTask.id, data)
      } else {
        savedTask = await api.createTask(data)
      }

      // Авто-создание блоков для повторяющихся задач с recur_days
      if (data.is_recurring && data.recur_days?.length > 0 && savedTask?.id) {
        try {
          await api.autoCreateRecurring(savedTask.id, weekStart)
        } catch {
          // Не блокируем сохранение задачи — блоки можно создать вручную
        }
      }

      await loadTasks()
      setShowForm(false)
    } catch (e: any) {
      console.error('Ошибка сохранения задачи:', e)
      setSaveError(e.message || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTask) return
    setSaving(true)
    try {
      // Если удаляем эпик — удалить все его задачи тоже
      if (deleteTask.is_epic) {
        const epicTasks = tasks.filter((t) => t.epic_id === deleteTask.id)
        for (const t of epicTasks) {
          await api.deleteTask(t.id)
        }
      }
      await api.deleteTask(deleteTask.id)
      await loadTasks()
      setDeleteTask(null)
    } finally {
      setSaving(false)
    }
  }

  const toggleRecurDay = (day: number) => {
    setFormRecurDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day].sort()
    )
  }

  const toggleEpic = (epicId: number) => {
    setExpandedEpics((prev) => {
      const next = new Set(prev)
      if (next.has(epicId)) next.delete(epicId)
      else next.add(epicId)
      return next
    })
  }

  const renderSection = (
    key: string,
    title: string,
    count: number,
    groups: { sectionEpics: Task[]; byEpic: Record<number, Task[]>; standalone: Task[] }
  ) => {
    if (count === 0 && groups.sectionEpics.length === 0) return null
    const totalCount = count + groups.sectionEpics.length
    const isExpanded = expandedSections.has(key)
    return (
      <div className="backlog-section">
        <div className="backlog-section-header" onClick={() => toggleSection(key)}>
          <span className="backlog-section-arrow">{isExpanded ? '▾' : '▸'}</span>
          <span className="backlog-section-title">{title}</span>
          <span className="backlog-section-count">{totalCount}</span>
        </div>
        {isExpanded && (
          <div className="backlog-section-body">
            {groups.sectionEpics.map((epic) => (
              <div key={epic.id} className="backlog-epic">
                <div className="backlog-epic-header card" onClick={() => toggleEpic(epic.id)}>
                  <span className="backlog-epic-arrow">{expandedEpics.has(epic.id) ? '▼' : '▶'}</span>
                  <span className="backlog-epic-icon">{epic.epic_emoji || '📦'}</span>
                  <span className="backlog-epic-name">{epic.name}</span>
                  <span className="backlog-epic-count">{(groups.byEpic[epic.id] || []).length} задач</span>
                  <button className="btn-icon" onClick={(e) => { e.stopPropagation(); handleEdit(epic) }}>✏️</button>
                  <button className="btn-icon" onClick={(e) => { e.stopPropagation(); setDeleteTask(epic) }}>🗑</button>
                </div>
                {expandedEpics.has(epic.id) && (
                  <div className="backlog-epic-tasks">
                    {(groups.byEpic[epic.id] || []).map((task) => renderTaskCard(task, true))}
                    {(!groups.byEpic[epic.id] || groups.byEpic[epic.id].length === 0) && (
                      <div className="backlog-epic-empty">Нет задач в этой группе</div>
                    )}
                  </div>
                )}
              </div>
            ))}
            <div className="backlog-list">
              {groups.standalone.map((task) => renderTaskCard(task))}
            </div>
          </div>
        )}
      </div>
    )
  }

  const NEXT_STATUS: Record<string, string> = {
    grooming: 'in_progress',
    in_progress: 'done',
    blocked: 'in_progress',
    done: 'grooming',
  }

  const handleQuickStatusChange = async (e: React.MouseEvent, task: Task) => {
    e.stopPropagation()
    const nextStatus = NEXT_STATUS[task.status] || 'grooming'
    try {
      await api.updateTask(task.id, { status: nextStatus })
      await loadTasks()
    } catch {}
  }

  const renderTaskCard = (task: Task, indent = false) => {
    const cat = catMap[task.category_id]
    return (
      <div key={task.id} className={`backlog-item card ${indent ? 'backlog-item-indent' : ''}`} onClick={() => handleEdit(task)}>
        <div className="backlog-item-header">
          <span className="backlog-priority">{PRIORITY_EMOJI[task.priority]}</span>
          <button
            className="backlog-status-quick-btn"
            onClick={(e) => handleQuickStatusChange(e, task)}
            title={`${STATUS_LABELS[task.status]} — нажмите для смены`}
          >
            {STATUS_EMOJI[task.status] || '🔘'}
          </button>
          <span className="backlog-task-name">{task.name}</span>
          <button className="btn-icon" onClick={(e) => { e.stopPropagation(); setDeleteTask(task) }}>🗑</button>
        </div>
        {(task.description || task.link) && (
          <div className="backlog-item-extra">
            {task.description && (
              <span className="backlog-description" title={task.description}>
                {task.description.length > 80 ? task.description.slice(0, 80) + '...' : task.description}
              </span>
            )}
            {task.link && (
              <a
                className="backlog-link"
                href={task.link}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                title={task.link}
              >
                🔗 {task.link.length > 40 ? task.link.slice(0, 40) + '...' : task.link}
              </a>
            )}
          </div>
        )}
        <div className="backlog-item-meta">
          {cat && <span className="backlog-cat">{cat.emoji || '📁'} {cat.name}</span>}
          {task.estimated_time_min && <span className="backlog-time">⏱ {task.estimated_time_min} мин</span>}
          {task.deadline && <span className="backlog-deadline">📅 {task.deadline}</span>}
          {task.scheduled_date && <span className="backlog-scheduled">🗓 {task.scheduled_date}</span>}
          {task.is_recurring && <span className="backlog-badge">🔁</span>}
        </div>
      </div>
    )
  }

  return (
    <div className="backlog-screen">
      <div className="header">
        <h1>📋 Задачи</h1>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <button className="btn btn-secondary btn-sm" onClick={() => handleAdd(true)}>📦 Группа</button>
          <button className="btn btn-primary btn-sm" onClick={() => handleAdd(false)}>+ Задача</button>
          <ThemeToggle />
        </div>
      </div>

      <div className="backlog-filters">
        <input className="input backlog-search" placeholder="🔍 Поиск..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="backlog-filter-row">
          <select className="input backlog-filter-select" value={filterCat} onChange={(e) => setFilterCat(e.target.value ? parseInt(e.target.value) : '')}>
            <option value="">Все категории</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.emoji} {c.name}</option>)}
          </select>
          <select className="input backlog-filter-select" value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)}>
            <option value="">Любой приоритет</option>
            <option value="high">🔴 Высокий</option>
            <option value="medium">🟡 Средний</option>
            <option value="low">🟢 Низкий</option>
          </select>
        </div>
        {/* Фильтр по статусу — мультивыбор */}
        <div className="backlog-status-filter">
          {(Object.keys(STATUS_LABELS) as Array<keyof typeof STATUS_LABELS>).map((st) => (
            <button
              key={st}
              className={`backlog-status-btn${filterStatuses.includes(st) ? ' active' : ''}`}
              onClick={() =>
                setFilterStatuses((prev) =>
                  prev.includes(st) ? prev.filter((s) => s !== st) : [...prev, st]
                )
              }
            >
              {STATUS_EMOJI[st]} {STATUS_LABELS[st]}
            </button>
          ))}
        </div>
        {/* Сортировка + переключатель вида */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div className="backlog-sort-bar" style={{ flex: 1 }}>
            {SORT_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`backlog-sort-btn${sortField === opt.value ? ' active' : ''}`}
                onClick={() => handleSortClick(opt.value)}
                title={opt.label}
              >
                {opt.icon}{sortField === opt.value ? (sortDir === 'asc' ? '↑' : '↓') : ''}
              </button>
            ))}
          </div>
          <div className="backlog-view-toggle">
            <button
              className={`backlog-view-btn${viewMode === 'cards' ? ' active' : ''}`}
              onClick={() => setViewMode('cards')}
              title="Карточки"
            >▦</button>
            <button
              className={`backlog-view-btn${viewMode === 'table' ? ' active' : ''}`}
              onClick={() => setViewMode('table')}
              title="Таблица"
            >☰</button>
          </div>
        </div>
      </div>

      {viewMode === 'cards' ? (
        <>
          {/* Секция: Регулярные */}
          {renderSection('recurring', '🔁 Регулярные', recurringTasks.length, recurringGroups)}

          {/* Секция: Разовые */}
          {renderSection('onetime', '📌 Разовые', onetimeTasks.length, onetimeGroups)}
        </>
      ) : (
        /* Табличный вид */
        <div className="backlog-table-wrap">
          <table className="backlog-table">
            <thead>
              <tr>
                <th style={{ width: 28 }}></th>
                <th style={{ width: 28 }}></th>
                <th>Название</th>
                <th style={{ width: 70 }}>Группа</th>
                <th style={{ width: 80 }}>Категория</th>
                <th style={{ width: 50 }}>Время</th>
                <th style={{ width: 80 }}>Дедлайн</th>
                <th style={{ width: 28 }}></th>
              </tr>
            </thead>
            <tbody>
              {flatSorted.map((task) => {
                const cat = catMap[task.category_id]
                const epic = task.epic_id ? tasks.find((t) => t.id === task.epic_id) : null
                return (
                  <tr key={task.id} className="backlog-table-row" onClick={() => handleEdit(task)}>
                    <td className="backlog-table-priority">{PRIORITY_EMOJI[task.priority]}</td>
                    <td className="backlog-table-status" title={STATUS_LABELS[task.status] || task.status}>{STATUS_EMOJI[task.status] || '🔘'}</td>
                    <td className="backlog-table-name">
                      {task.name}
                      {task.is_recurring && <span className="backlog-badge-sm">🔁</span>}
                    </td>
                    <td className="backlog-table-epic">{epic ? `${epic.epic_emoji || '📦'} ${epic.name}` : '—'}</td>
                    <td className="backlog-table-cat">{cat?.emoji || '📁'} {cat?.name || ''}</td>
                    <td className="backlog-table-time">{task.estimated_time_min ? `${task.estimated_time_min}м` : '—'}</td>
                    <td className="backlog-table-deadline">{task.deadline || '—'}</td>
                    <td>
                      <button className="btn-icon" onClick={(e) => { e.stopPropagation(); setDeleteTask(task) }}>🗑</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          {tasks.length === 0 ? 'Нет задач. Нажмите «+ Задача» чтобы создать первую.' : 'Нет задач по фильтрам.'}
        </div>
      )}

      {/* Форма */}
      {showForm && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowForm(false) }}>
          <div className="dialog backlog-dialog" onMouseDown={(e) => e.stopPropagation()}>
            <h3>{formIsEpic ? (editTask ? 'Редактировать группу' : 'Новая группа задач') : (editTask ? 'Редактировать задачу' : 'Новая задача')}</h3>
            <div className="backlog-form">
              <label className="label">Название *</label>
              {formIsEpic ? (
                <>
                  <input className="input" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Название группы задач" autoFocus />
                  <label className="label" style={{ marginTop: 8 }}>Иконка группы</label>
                  <EmojiPicker selected={formEpicEmoji} onSelect={setFormEpicEmoji} />
                </>

              ) : (
                <input className="input" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Что нужно сделать?" autoFocus />
              )}

              {!formIsEpic && availableEpics.length > 0 && (
                <>
                  <label className="label">Группа задач</label>
                  <select className="input" value={formEpicId} onChange={(e) => {
                    const epicId = e.target.value ? parseInt(e.target.value) : ''
                    setFormEpicId(epicId)
                    // Авто-категория: подставить категорию группы
                    if (epicId) {
                      const epic = tasks.find((t) => t.id === epicId)
                      if (epic) setFormCatId(epic.category_id)
                    }
                  }}>
                    <option value="">Без группы</option>
                    {availableEpics.map((e) => <option key={e.id} value={e.id}>{e.epic_emoji || '📦'} {e.name}</option>)}
                  </select>
                </>
              )}

              <label className="label">Категория *</label>
              <select className="input" value={formCatId} onChange={(e) => setFormCatId(parseInt(e.target.value))}>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.emoji} {c.name}</option>)}
              </select>

              <label className="label">Приоритет</label>
              <select className="input" value={formPriority} onChange={(e) => setFormPriority(e.target.value as any)}>
                <option value="high">🔴 Высокий</option>
                <option value="medium">🟡 Средний</option>
                <option value="low">🟢 Низкий</option>
              </select>

              {!formIsEpic && (
                <>
                  <label className="label">Статус</label>
                  <select
                    className="input"
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value as typeof formStatus)}
                  >
                    {(Object.keys(STATUS_EMOJI) as Array<keyof typeof STATUS_EMOJI>).map((st) => (
                      <option key={st} value={st}>{STATUS_EMOJI[st]} {STATUS_LABELS[st]}</option>
                    ))}
                  </select>

                  <label className="label" style={{ marginTop: 12 }}>Описание</label>
                  <textarea
                    className="input"
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    placeholder="Подробности задачи (опционально)"
                    rows={3}
                    style={{ resize: 'vertical' }}
                  />

                  <label className="label">Ссылка</label>
                  <input
                    className="input"
                    type="url"
                    value={formLink}
                    onChange={(e) => setFormLink(e.target.value)}
                    placeholder="https://..."
                  />

                  <label className="label">Примерное время (мин)</label>
                  <input className="input" type="number" min={1} value={formEstTime} onChange={(e) => setFormEstTime(e.target.value)} placeholder="—" style={{ maxWidth: 140 }} />

                  <label className="label" style={{ marginTop: 12 }}>Запланировать на дату</label>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                      className={`btn btn-sm ${formScheduledDate === new Date().toISOString().slice(0, 10) ? 'btn-primary' : 'btn-secondary'}`}
                      type="button"
                      onClick={() => setFormScheduledDate(new Date().toISOString().slice(0, 10))}
                    >Сегодня</button>
                    <button
                      className={`btn btn-sm ${formScheduledDate === new Date(Date.now() + 86400000).toISOString().slice(0, 10) ? 'btn-primary' : 'btn-secondary'}`}
                      type="button"
                      onClick={() => setFormScheduledDate(new Date(Date.now() + 86400000).toISOString().slice(0, 10))}
                    >Завтра</button>
                    <input
                      className="input"
                      type="date"
                      value={formScheduledDate}
                      onChange={(e) => setFormScheduledDate(e.target.value)}
                      style={{ maxWidth: 160, flex: 1 }}
                    />
                    {formScheduledDate && (
                      <button
                        className="btn btn-sm btn-secondary"
                        style={{ fontSize: 11 }}
                        onClick={() => setFormScheduledDate('')}
                        type="button"
                      >✕</button>
                    )}
                  </div>
                  <span className="hint">На какой день запланирована задача</span>

                  <label className="schedule-toggle" style={{ marginTop: 12 }}>
                    <input type="checkbox" checked={formHasDeadline} onChange={(e) => setFormHasDeadline(e.target.checked)} />
                    <span className="schedule-toggle-label">📅 Есть дедлайн</span>
                  </label>
                  {formHasDeadline && (
                    <div style={{ marginTop: 4 }}>
                      <input className="input" type="date" value={formDeadline} onChange={(e) => setFormDeadline(e.target.value)} />
                      <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          onClick={() => {
                            const d = new Date()
                            setFormDeadline(d.toISOString().split('T')[0])
                          }}
                        >
                          Сегодня
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          onClick={() => {
                            const d = new Date()
                            d.setDate(d.getDate() + 1)
                            setFormDeadline(d.toISOString().split('T')[0])
                          }}
                        >
                          Завтра
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          onClick={() => {
                            const { schedule } = useStore.getState()
                            const today = new Date()
                            const todayDow = (today.getDay() + 6) % 7 // 0=Пн
                            // Ищем последний рабочий день недели
                            let lastWorkDay = 4 // дефолт — пятница
                            for (let d = 6; d >= 0; d--) {
                              const s = schedule.find((s) => s.day_of_week === d)
                              if (s && !s.is_day_off) { lastWorkDay = d; break }
                            }
                            const daysUntil = (lastWorkDay - todayDow + 7) % 7 || 7
                            const end = new Date()
                            end.setDate(today.getDate() + (lastWorkDay >= todayDow ? lastWorkDay - todayDow : daysUntil))
                            setFormDeadline(end.toISOString().split('T')[0])
                          }}
                        >
                          Конец недели
                        </button>
                      </div>
                    </div>
                  )}

                  <label className="label">Зависит от задачи</label>
                  <select className="input" value={formDependsOn} onChange={(e) => setFormDependsOn(e.target.value ? parseInt(e.target.value) : '')}>
                    <option value="">Нет зависимости</option>
                    {tasks.filter((t) => t.id !== editTask?.id && !t.is_epic).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>

                  <div className="backlog-form-checks" style={{ marginTop: 12 }}>
                    <label className="schedule-toggle">
                      <input type="checkbox" checked={formRecurring} onChange={(e) => setFormRecurring(e.target.checked)} />
                      <span className="schedule-toggle-label">🔁 Повторяемая</span>
                      <span className="info-tooltip"><span className="info-icon">?</span><span className="info-tooltip-text">Задача повторяется в выбранные дни недели. При автораспределении будет ставиться в каждый выбранный день.</span></span>
                    </label>
                  </div>

                  {formRecurring && (
                    <div className="backlog-recur-section">
                      <div className="backlog-recur-presets">
                        <button
                          className={`btn btn-sm ${formRecurDays.length === 7 ? 'btn-primary' : 'btn-secondary'}`}
                          onClick={() => setFormRecurDays(formRecurDays.length === 7 ? [] : [0, 1, 2, 3, 4, 5, 6])}
                        >
                          Каждый день
                        </button>
                        <button
                          className={`btn btn-sm ${formRecurDays.length === 5 && [0,1,2,3,4].every(d => formRecurDays.includes(d)) ? 'btn-primary' : 'btn-secondary'}`}
                          onClick={() => {
                            const weekdays = [0, 1, 2, 3, 4]
                            const isWeekdays = formRecurDays.length === 5 && weekdays.every(d => formRecurDays.includes(d))
                            setFormRecurDays(isWeekdays ? [] : weekdays)
                          }}
                        >
                          Будни
                        </button>
                      </div>
                      <div className="backlog-recur-days">
                        {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((name, i) => (
                          <button key={i} className={`btn btn-sm ${formRecurDays.includes(i) ? 'btn-primary' : 'btn-secondary'}`} onClick={() => toggleRecurDay(i)}>{name}</button>
                        ))}
                      </div>
                      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                        <div style={{ flex: 1 }}>
                          <label className="backlog-form-label">Время старта</label>
                          <input
                            type="time"
                            className="input"
                            value={formRecurTime}
                            onChange={(e) => setFormRecurTime(e.target.value)}
                            placeholder="не задано"
                          />
                          <div className="backlog-form-hint">Авто-слот в это время</div>
                        </div>
                        <div style={{ flex: 1 }}>
                          <label className="backlog-form-label">Длительность (мин)</label>
                          <input
                            type="number"
                            className="input"
                            value={formRecurDuration}
                            onChange={(e) => setFormRecurDuration(e.target.value)}
                            min={1}
                            placeholder="не задано"
                          />
                          <div className="backlog-form-hint">Для авто-слота</div>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
            {saveError && <div style={{ color: 'var(--danger)', padding: '8px 16px', fontSize: '0.85rem' }}>{saveError}</div>}
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving || !formName.trim() || !formCatId}>{saving ? '...' : 'Сохранить'}</button>
            </div>
          </div>
        </div>
      )}

      {deleteTask && (
        <div className="overlay" onClick={() => setDeleteTask(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>Удалить {deleteTask.is_epic ? 'группу' : 'задачу'}?</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              «{deleteTask.name}» будет удален{deleteTask.is_epic ? 'а' : 'а'}.
              {deleteTask.is_epic && (() => {
                const count = tasks.filter((t) => t.epic_id === deleteTask.id).length
                return count > 0
                  ? ` Вместе с группой будут удалены ${count} задач${count === 1 ? 'а' : count < 5 ? 'и' : ''}.`
                  : ' В группе нет задач.'
              })()}
            </p>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setDeleteTask(null)}>Отмена</button>
              <button className="btn btn-danger" onClick={handleDelete} disabled={saving}>{saving ? '...' : 'Удалить'}</button>
            </div>
          </div>
        </div>
      )}
      <div style={{ height: 80 }} />
    </div>
  )
}
