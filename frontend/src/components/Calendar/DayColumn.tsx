// Колонка дня в календаре — временные слоты + блоки (draggable)

import { useDroppable, useDraggable } from '@dnd-kit/core'
import type { TaskBlock, Task, Category, WeeklyScheduleItem } from '../../types'

interface DayColumnProps {
  day: string
  dayOfWeek: number
  blocks: TaskBlock[]
  schedule?: WeeklyScheduleItem
  taskMap: Record<number, Task>
  catMap: Record<number, Category>
  dayStartTime: string  // из настроек пользователя
  dayEndTime: string    // из настроек пользователя
  dragBlockId?: number | null  // ID перетаскиваемого блока — его слоты остаются видимыми
  onBlockClick: (block: TaskBlock) => void
  onAddBlock: (day: string, time: string) => void
  onDeleteBlock: (blockId: number) => void
}

// Генерация временных слотов — одинаковый диапазон для всех дней
function generateSlots(dayStartTime: string, dayEndTime: string): string[] {
  const startHour = parseInt(dayStartTime.split(':')[0])
  const startMin = parseInt(dayStartTime.split(':')[1])
  const endHour = parseInt(dayEndTime.split(':')[0])
  const endMin = parseInt(dayEndTime.split(':')[1])

  const slots: string[] = []
  let h = startHour, m = startMin
  while (h < endHour || (h === endHour && m < endMin)) {
    slots.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
    m += 30
    if (m >= 60) { m = 0; h++ }
  }
  return slots
}

function getBlockDuration(block: TaskBlock): number {
  if (block.duration_type === 'fixed') return block.duration_min || 30
  if (block.duration_type === 'range') {
    return block.min_duration_min && block.max_duration_min
      ? Math.round((block.min_duration_min + block.max_duration_min) / 2)
      : block.max_duration_min || 30
  }
  return block.max_duration_min || 60
}

function getBlockTypeIcon(type: string): string {
  if (type === 'open') return '🔓'
  if (type === 'range') return '↔️'
  return ''
}

function getBlockColor(block: TaskBlock, taskMap: Record<number, Task>, catMap: Record<number, Category>): string {
  if (block.task_ids?.length > 0) {
    const task = taskMap[block.task_ids[0]]
    if (task) {
      const cat = catMap[task.category_id]
      if (cat?.color) return cat.color
    }
  }
  return 'var(--accent)'
}

// Droppable слот — подсвечивается при перетаскивании
function TimeSlot({
  day,
  time,
  children,
  onAdd,
}: {
  day: string
  time: string
  children?: React.ReactNode
  onAdd: () => void
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `slot-${day}-${time}`,
    data: { type: 'slot', day, time },
  })

  return (
    <div
      ref={setNodeRef}
      className={`day-slot ${isOver ? 'droppable' : ''}`}
    >
      <span className="day-slot-time">{time}</span>
      {children}
      {!children && (
        <button className="day-slot-add" onClick={onAdd}>+</button>
      )}
    </div>
  )
}

// Draggable блок в календаре
function DraggableBlock({
  block,
  blockName,
  durText,
  typeIcon,
  color,
  slotsCount,
  taskCount,
  totalCount,
  onBlockClick,
  onDeleteBlock,
}: {
  block: TaskBlock
  blockName: string
  durText: string
  typeIcon: string
  color: string
  slotsCount: number
  taskCount: number
  totalCount: number
  onBlockClick: (block: TaskBlock) => void
  onDeleteBlock: (blockId: number) => void
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `block-${block.id}`,
    data: { type: 'block', block },
  })

  return (
    <div
      ref={setNodeRef}
      className={`cal-block status-${block.status}`}
      style={{
        borderLeftColor: color,
        height: `${slotsCount * 28 - 2}px`,
        opacity: isDragging ? 0.4 : 1,
        cursor: 'grab',
      }}
      title={`${blockName}\n${block.start_time} · ${durText}${totalCount > 1 ? `\n📦 ${taskCount} задач (${totalCount} шт.)` : ''}`}
      onClick={() => onBlockClick(block)}
      {...listeners}
      {...attributes}
    >
      <div className="cal-block-name">{typeIcon} {totalCount > 1 ? `📦 ${taskCount} задач` : blockName}</div>
      <div className="cal-block-time">{block.start_time} · {durText}</div>
      <button className="cal-block-delete" onClick={(e) => { e.stopPropagation(); onDeleteBlock(block.id) }}>✕</button>
    </div>
  )
}

export default function DayColumn({
  day, blocks, schedule, taskMap, catMap,
  dayStartTime, dayEndTime, dragBlockId,
  onBlockClick, onAddBlock, onDeleteBlock,
}: DayColumnProps) {
  // Все дни используют одинаковый диапазон слотов из настроек пользователя
  const slots = generateSlots(dayStartTime, dayEndTime)

  const blockAtSlot: Record<string, TaskBlock> = {}
  const occupiedSlots = new Set<string>()
  // Отслеживаем какой блок занимает каждый слот
  const slotOwner: Record<string, number> = {}

  blocks.forEach((block) => {
    blockAtSlot[block.start_time] = block
    const duration = getBlockDuration(block)
    const [bh, bm] = block.start_time.split(':').map(Number)
    const startMin = bh * 60 + bm
    const slotsCount = Math.ceil(duration / 30)
    for (let i = 1; i < slotsCount; i++) {
      const min = startMin + i * 30
      const h = Math.floor(min / 60)
      const m = min % 60
      const slotKey = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
      occupiedSlots.add(slotKey)
      slotOwner[slotKey] = block.id
    }
  })

  return (
    <div className={`day-column ${schedule?.is_day_off ? 'day-off-column' : ''}`}>
      {slots.map((time) => {
        const block = blockAtSlot[time]
        const isOccupied = occupiedSlots.has(time)
        // При перетаскивании блока — его слоты становятся доступными drop-target'ами
        const isOwnedByDragged = dragBlockId != null && slotOwner[time] === dragBlockId
        // Также скрываем сам блок если он перетаскивается
        const isDraggedBlock = dragBlockId != null && block?.id === dragBlockId
        if (isOccupied && !isOwnedByDragged) return null

        // Если слот освобождён от перетаскиваемого блока — показать пустой слот
        if (isOwnedByDragged || isDraggedBlock) {
          return <TimeSlot key={time} day={day} time={time} onAdd={() => onAddBlock(day, time)} />
        }

        if (block) {
          const blockName = block.block_name || (block.task_ids?.length > 0 && taskMap[block.task_ids[0]]?.name) || 'Блок'
          const duration = getBlockDuration(block)
          const slotsCount = Math.max(1, Math.ceil(duration / 30))
          const color = getBlockColor(block, taskMap, catMap)
          const typeIcon = getBlockTypeIcon(block.duration_type)

          let durText = ''
          if (block.duration_type === 'fixed') durText = `${block.duration_min} мин`
          else if (block.duration_type === 'range') durText = `${block.min_duration_min}–${block.max_duration_min} мин`
          else durText = block.max_duration_min ? `до ${block.max_duration_min} мин` : 'откр.'

          const taskIds = block.task_ids || []
          const taskCount = new Set(taskIds).size
          const totalCount = taskIds.length

          return (
            <TimeSlot key={time} day={day} time={time} onAdd={() => onAddBlock(day, time)}>
              <DraggableBlock
                block={block}
                blockName={blockName}
                durText={durText}
                typeIcon={typeIcon}
                color={color}
                slotsCount={slotsCount}
                taskCount={taskCount}
                totalCount={totalCount}
                onBlockClick={onBlockClick}
                onDeleteBlock={onDeleteBlock}
              />
            </TimeSlot>
          )
        }

        return <TimeSlot key={time} day={day} time={time} onAdd={() => onAddBlock(day, time)} />
      })}
    </div>
  )
}
