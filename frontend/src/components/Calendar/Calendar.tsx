// Экран 5: Календарь недели — drag & drop, блоки, временная шкала

import { useState, useEffect, useMemo } from 'react'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  pointerWithin,
  closestCenter,
  type DragStartEvent,
  type DragEndEvent,
  type CollisionDetection,
} from '@dnd-kit/core'

// Гибридная коллизия: сначала проверяем по острию курсора, потом по центру
const hybridCollision: CollisionDetection = (args) => {
  const pointerHits = pointerWithin(args)
  if (pointerHits.length > 0) return pointerHits
  return closestCenter(args)
}
import { useStore } from '../../store'
import { api } from '../../api/client'
import type { TaskBlock, Task, Category } from '../../types'
import DayColumn from './DayColumn'
import BacklogPanel from './BacklogPanel'
import BlockForm from './BlockForm'
import './Calendar.css'

const DAY_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

// Форматирование даты в YYYY-MM-DD без сдвига часового пояса (toISOString конвертит в UTC!)
function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

interface MoveBlockInfo {
  block: TaskBlock
  newDay: string
  newTime: string
}

export default function Calendar() {
  const { blocks, tasks, categories, schedule, weekStart, setWeekStart, loadBlocks, loadTasks, user } = useStore()
  const [showBacklog, setShowBacklog] = useState(false)
  const [showBlockForm, setShowBlockForm] = useState(false)
  const [editBlock, setEditBlock] = useState<TaskBlock | null>(null)
  const [dragTask, setDragTask] = useState<Task | null>(null)
  const [dragBlock, setDragBlock] = useState<TaskBlock | null>(null)
  const [dragEpic, setDragEpic] = useState<{ epic: Task; epicTasks: Task[] } | null>(null)
  const [dropDay, setDropDay] = useState<string>('')
  const [dropTime, setDropTime] = useState<string>('')
  const [isDragging, setIsDragging] = useState(false)
  const [preselectedTaskIds, setPreselectedTaskIds] = useState<number[]>([])
  const [showConfirm, setShowConfirm] = useState<'auto' | 'carry' | 'clear' | null>(null)
  const [moveBlock, setMoveBlock] = useState<MoveBlockInfo | null>(null)
  const [movingSaving, setMovingSaving] = useState(false)

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))

  useEffect(() => { loadBlocks(); loadTasks() }, [weekStart])

  const weekDays = useMemo(() => {
    const start = new Date(weekStart + 'T00:00:00')
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(start); d.setDate(d.getDate() + i)
      return formatLocalDate(d)
    })
  }, [weekStart])

  const blocksByDay = useMemo(() => {
    const map: Record<string, TaskBlock[]> = {}
    weekDays.forEach((d) => (map[d] = []))
    blocks.forEach((b) => { if (map[b.day]) map[b.day].push(b) })
    return map
  }, [blocks, weekDays])

  const taskMap = useMemo(() => {
    const m: Record<number, Task> = {}; tasks.forEach((t) => (m[t.id] = t)); return m
  }, [tasks])

  const catMap = useMemo(() => {
    const m: Record<number, Category> = {}; categories.forEach((c) => (m[c.id] = c)); return m
  }, [categories])

  // Расширение временных рамок если есть блоки за пределами дня
  const [effectiveStart, effectiveEnd] = useMemo(() => {
    let startMin = user?.day_start_time || '08:00'
    let endMin = user?.day_end_time || '23:50'

    for (const block of blocks) {
      const bTime = block.start_time
      if (bTime < startMin) {
        // Округлить вниз до 30 мин
        const [h, m] = bTime.split(':').map(Number)
        const rounded = Math.floor(m / 30) * 30
        startMin = `${String(h).padStart(2, '0')}:${String(rounded).padStart(2, '0')}`
      }
      // Конец блока
      const [bh, bm] = bTime.split(':').map(Number)
      const dur = block.duration_min || block.max_duration_min || 60
      const endMins = bh * 60 + bm + dur
      const endH = Math.min(23, Math.floor(endMins / 60))
      const endM = Math.ceil((endMins % 60) / 30) * 30
      const blockEnd = endM >= 60
        ? `${String(endH + 1).padStart(2, '0')}:00`
        : `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`
      if (blockEnd > endMin) endMin = blockEnd
    }

    return [startMin, endMin]
  }, [blocks, user?.day_start_time, user?.day_end_time])

  const prevWeek = () => {
    const d = new Date(weekStart + 'T00:00:00'); d.setDate(d.getDate() - 7)
    setWeekStart(formatLocalDate(d))
  }
  const nextWeek = () => {
    const d = new Date(weekStart + 'T00:00:00'); d.setDate(d.getDate() + 7)
    setWeekStart(formatLocalDate(d))
  }
  const toCurrentWeek = () => {
    const d = new Date(); const day = d.getDay()
    const diff = d.getDate() - day + (day === 0 ? -6 : 1)
    const monday = new Date(d.setDate(diff))
    setWeekStart(formatLocalDate(monday))
  }

  const handleDragStart = (event: DragStartEvent) => {
    const { active } = event
    setDragTask(null)
    setDragBlock(null)
    setDragEpic(null)
    if (active.data.current?.type === 'task') {
      setDragTask(active.data.current.task)
      setIsDragging(true)
    } else if (active.data.current?.type === 'block') {
      setDragBlock(active.data.current.block)
      setIsDragging(true)
    } else if (active.data.current?.type === 'epic') {
      setDragEpic({ epic: active.data.current.epic, epicTasks: active.data.current.epicTasks })
      setIsDragging(true)
    }
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    const droppedTask = dragTask
    const droppedBlock = dragBlock
    const droppedEpic = dragEpic
    setDragTask(null)
    setDragBlock(null)
    setDragEpic(null)
    setIsDragging(false)

    if (!over) return
    const overData = over.data.current

    // Задача из бэклога → слот
    if (active.data.current?.type === 'task' && overData?.type === 'slot') {
      setDropDay(overData.day)
      setDropTime(overData.time)
      setEditBlock(null)
      setPreselectedTaskIds(droppedTask ? [droppedTask.id] : [])
      setShowBlockForm(true)
    }

    // Эпик из бэклога → слот (все задачи эпика)
    if (active.data.current?.type === 'epic' && overData?.type === 'slot' && droppedEpic) {
      setDropDay(overData.day)
      setDropTime(overData.time)
      setEditBlock(null)
      setPreselectedTaskIds(droppedEpic.epicTasks.map(t => t.id))
      setShowBlockForm(true)
    }

    // Блок → другой слот (перемещение)
    if (active.data.current?.type === 'block' && overData?.type === 'slot' && droppedBlock) {
      const newDay = overData.day as string
      const newTime = overData.time as string
      // Не показывать диалог если бросили на то же место
      if (newDay === droppedBlock.day && newTime === droppedBlock.start_time) return
      setMoveBlock({ block: droppedBlock, newDay, newTime })
    }
  }

  const handleConfirmMove = async () => {
    if (!moveBlock) return
    setMovingSaving(true)
    try {
      await api.updateBlock(moveBlock.block.id, {
        day: moveBlock.newDay,
        start_time: moveBlock.newTime,
      })
      await loadBlocks()
      setMoveBlock(null)
    } catch (e: any) {
      alert(e.message || 'Ошибка перемещения')
    } finally {
      setMovingSaving(false)
    }
  }

  const handleBlockClick = (block: TaskBlock) => { setEditBlock(block); setShowBlockForm(true) }
  const handleDeleteBlock = async (blockId: number) => { await api.deleteBlock(blockId); await loadBlocks() }
  const handleAddBlock = (day: string, time: string) => {
    setDropDay(day); setDropTime(time); setEditBlock(null); setPreselectedTaskIds([]); setShowBlockForm(true)
  }

  const handleAutoDistribute = async () => {
    await api.autoDistribute(weekStart); await loadBlocks(); setShowConfirm(null)
  }
  const handleCarryOver = async () => {
    await api.carryOver(weekStart); await loadBlocks(); setShowConfirm(null)
  }
  const handleClearBlocks = async () => {
    await api.clearBlocks(weekStart); await loadBlocks(); setShowConfirm(null)
  }

  const formatWeekRange = () => {
    const start = new Date(weekStart + 'T00:00:00')
    const end = new Date(start); end.setDate(end.getDate() + 6)
    const opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }
    return `${start.toLocaleDateString('ru', opts)} — ${end.toLocaleDateString('ru', opts)}`
  }

  // Название блока для диалога перемещения
  const getMoveBlockName = () => {
    if (!moveBlock) return ''
    const b = moveBlock.block
    return b.block_name || (b.task_ids?.length > 0 && taskMap[b.task_ids[0]]?.name) || 'Блок'
  }

  const formatDayShort = (dateStr: string) => {
    const d = new Date(dateStr + 'T00:00:00')
    const dow = d.getDay()
    const dayIdx = dow === 0 ? 6 : dow - 1
    return `${DAY_SHORT[dayIdx]} ${d.getDate()}`
  }

  return (
    <div className={`calendar-screen ${isDragging ? 'is-dragging' : ''}`}>
      <div className="calendar-header">
        <div className="calendar-nav">
          <button className="btn-icon" onClick={prevWeek}>◀</button>
          <button className="calendar-week-label" onClick={toCurrentWeek}>{formatWeekRange()}</button>
          <button className="btn-icon" onClick={nextWeek}>▶</button>
        </div>
        <div className="calendar-actions">
          <button className="btn btn-secondary btn-sm" onClick={() => setShowBacklog(!showBacklog)} title="Панель задач для перетаскивания">
            {showBacklog ? '✕' : '📋'}
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowConfirm('auto')} title="Автоматически расставить задачи по свободным слотам">
            🔄
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowConfirm('carry')} title="Перенести невыполненные блоки на следующую неделю">
            ➡️
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowConfirm('clear')} title="Очистить все запланированные блоки">
            🗑
          </button>
        </div>
      </div>

      <DndContext sensors={sensors} collisionDetection={hybridCollision} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="calendar-body">
          {showBacklog && <BacklogPanel tasks={tasks} catMap={catMap} />}

          <div className="calendar-grid">
            <div className="calendar-day-headers">
              {weekDays.map((day, i) => {
                const d = new Date(day + 'T00:00:00')
                const isToday = day === formatLocalDate(new Date())
                const scheduleDay = schedule.find((s) => s.day_of_week === i)
                return (
                  <div key={day} className={`calendar-day-header ${isToday ? 'today' : ''}`}>
                    <span className="calendar-day-name">{DAY_SHORT[i]}</span>
                    <span className="calendar-day-date">{d.getDate()}</span>
                    {scheduleDay?.is_day_off && <span className="calendar-day-off">вых</span>}
                  </div>
                )
              })}
            </div>

            <div className="calendar-columns">
              {weekDays.map((day, i) => (
                <DayColumn
                  key={day} day={day} dayOfWeek={i}
                  blocks={blocksByDay[day] || []}
                  schedule={schedule.find((s) => s.day_of_week === i)}
                  taskMap={taskMap} catMap={catMap}
                  dayStartTime={effectiveStart}
                  dayEndTime={effectiveEnd}
                  dragBlockId={dragBlock?.id ?? null}
                  onBlockClick={handleBlockClick} onAddBlock={handleAddBlock} onDeleteBlock={handleDeleteBlock}
                />
              ))}
            </div>
          </div>
        </div>

        <DragOverlay dropAnimation={null}>
          {dragTask && (
            <div className="backlog-drag-preview">
              {catMap[dragTask.category_id]?.emoji || '📋'} {dragTask.name}
            </div>
          )}
          {dragBlock && (() => {
            const dur = dragBlock.duration_type === 'fixed'
              ? (dragBlock.duration_min || 30)
              : dragBlock.duration_type === 'range'
                ? Math.round(((dragBlock.min_duration_min || 0) + (dragBlock.max_duration_min || 0)) / 2)
                : (dragBlock.max_duration_min || 60)
            const slotsCount = Math.max(1, Math.ceil(dur / 30))
            const blockName = dragBlock.block_name || (dragBlock.task_ids?.length > 0 && taskMap[dragBlock.task_ids[0]]?.name) || 'Блок'
            const color = (() => {
              if (dragBlock.task_ids?.length > 0) {
                const t = taskMap[dragBlock.task_ids[0]]
                if (t) { const c = catMap[t.category_id]; if (c?.color) return c.color }
              }
              return 'var(--accent)'
            })()
            return (
              <div
                className="cal-block"
                style={{
                  borderLeftColor: color,
                  height: `${slotsCount * 28 - 2}px`,
                  width: 120,
                  boxShadow: 'var(--shadow-lg)',
                  opacity: 0.9,
                }}
              >
                <div className="cal-block-name">{blockName}</div>
                <div className="cal-block-time">{dragBlock.start_time} · {dur} мин</div>
              </div>
            )
          })()}
          {dragEpic && (
            <div className="backlog-drag-preview">
              {catMap[dragEpic.epic.category_id]?.emoji || '📁'} {dragEpic.epic.name} ({dragEpic.epicTasks.length} задач)
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {showBlockForm && (
        <BlockForm
          day={dropDay} time={dropTime} editBlock={editBlock}
          tasks={tasks} taskMap={taskMap} catMap={catMap}
          preselectedTaskIds={preselectedTaskIds}
          onClose={() => setShowBlockForm(false)} onSaved={() => { setShowBlockForm(false); loadBlocks() }}
        />
      )}

      {/* Диалог подтверждения перемещения блока */}
      {moveBlock && (
        <div className="overlay" onClick={() => setMoveBlock(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>📦 Переместить блок?</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              «{getMoveBlockName()}» → {formatDayShort(moveBlock.newDay)} в {moveBlock.newTime}
            </p>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setMoveBlock(null)}>Отмена</button>
              <button className="btn btn-primary" onClick={handleConfirmMove} disabled={movingSaving}>
                {movingSaving ? '...' : 'Переместить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Диалоги подтверждения */}
      {showConfirm === 'auto' && (
        <div className="overlay" onClick={() => setShowConfirm(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>🔄 Автораспределить</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              Бот автоматически расставит задачи из бэклога по свободным слотам в календаре,
              учитывая приоритет и примерное время задач.
            </p>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setShowConfirm(null)}>Отмена</button>
              <button className="btn btn-primary" onClick={handleAutoDistribute}>Распределить</button>
            </div>
          </div>
        </div>
      )}

      {showConfirm === 'carry' && (
        <div className="overlay" onClick={() => setShowConfirm(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>➡️ Перенести невыполненное</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              Все незавершённые блоки (пропущенные, проваленные) будут скопированы
              на следующую неделю в те же временные слоты.
            </p>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setShowConfirm(null)}>Отмена</button>
              <button className="btn btn-primary" onClick={handleCarryOver}>Перенести</button>
            </div>
          </div>
        </div>
      )}

      {showConfirm === 'clear' && (
        <div className="overlay" onClick={() => setShowConfirm(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>🗑 Очистить календарь</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              Все запланированные блоки за эту неделю будут удалены из календаря.
              Задачи останутся в бэклоге.
            </p>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setShowConfirm(null)}>Отмена</button>
              <button className="btn btn-primary btn-danger" onClick={handleClearBlocks}>Очистить</button>
            </div>
          </div>
        </div>
      )}

      <div style={{ height: 80 }} />
    </div>
  )
}
