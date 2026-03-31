// Экран 1: Управление категориями (CRUD + drag для сортировки + emoji picker)

import { useState, useEffect } from 'react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useStore } from '../../store'
import { api } from '../../api/client'
import type { Category } from '../../types'
import EmojiPicker from '../EmojiPicker'
import ThemeToggle from '../ThemeToggle'
import './Categories.css'

function SortableCategory({
  cat,
  onEdit,
  onDelete,
}: {
  cat: Category
  onEdit: (c: Category) => void
  onDelete: (c: Category) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: cat.id })
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }

  return (
    <div ref={setNodeRef} style={style} className="cat-item card">
      <div className="cat-drag" {...attributes} {...listeners}>☰</div>
      <div className="cat-info">
        <span className="cat-emoji">{cat.emoji || '📁'}</span>
        <span className="cat-name">{cat.name}</span>
      </div>
      <div className="cat-actions">
        <button className="btn-icon" onClick={() => onEdit(cat)} title="Редактировать">✏️</button>
        <button className="btn-icon" onClick={() => onDelete(cat)} title="Удалить">🗑</button>
      </div>
    </div>
  )
}

export default function Categories() {
  const { categories, loadCategories, setScreen } = useStore()
  const [items, setItems] = useState<Category[]>([])
  const [showForm, setShowForm] = useState(false)
  const [editCat, setEditCat] = useState<Category | null>(null)
  const [deleteCat, setDeleteCat] = useState<Category | null>(null)
  const [formName, setFormName] = useState('')
  const [formEmoji, setFormEmoji] = useState('')
  const [formColor, setFormColor] = useState('#6366f1')
  const [saving, setSaving] = useState(false)

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))

  useEffect(() => { setItems(categories) }, [categories])

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = items.findIndex((c) => c.id === active.id)
    const newIndex = items.findIndex((c) => c.id === over.id)
    const newItems = arrayMove(items, oldIndex, newIndex)
    setItems(newItems)
    await api.reorderCategories(newItems.map((c) => c.id))
    await loadCategories()
  }

  const handleAdd = () => {
    setEditCat(null); setFormName(''); setFormEmoji(''); setFormColor('#6366f1'); setShowForm(true)
  }

  const handleEdit = (cat: Category) => {
    setEditCat(cat); setFormName(cat.name); setFormEmoji(cat.emoji || ''); setFormColor(cat.color || '#6366f1'); setShowForm(true)
  }

  const handleSave = async () => {
    if (!formName.trim()) return
    setSaving(true)
    try {
      if (editCat) {
        await api.updateCategory(editCat.id, { name: formName.trim(), emoji: formEmoji || null, color: formColor })
      } else {
        await api.createCategory({ name: formName.trim(), emoji: formEmoji || null, color: formColor })
      }
      await loadCategories()
      setShowForm(false)
    } finally { setSaving(false) }
  }

  const handleDelete = async () => {
    if (!deleteCat) return
    setSaving(true)
    try { await api.deleteCategory(deleteCat.id); await loadCategories(); setDeleteCat(null) }
    finally { setSaving(false) }
  }

  return (
    <div className="categories-screen">
      <div className="header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn-icon" onClick={() => setScreen('settings')}>←</button>
          <h1>📁 Категории</h1>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button className="btn btn-primary btn-sm" onClick={handleAdd}>+ Добавить</button>
          <ThemeToggle />
        </div>
      </div>

      <p className="hint" style={{ marginBottom: 12 }}>Перетащите для изменения порядка</p>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={items.map((c) => c.id)} strategy={verticalListSortingStrategy}>
          <div className="cat-list">
            {items.map((cat) => (
              <SortableCategory key={cat.id} cat={cat} onEdit={handleEdit} onDelete={(c) => setDeleteCat(c)} />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      {items.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          Нет категорий. Нажмите «Добавить».
        </div>
      )}

      {showForm && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowForm(false) }}>
          <div className="dialog" onMouseDown={(e) => e.stopPropagation()}>
            <h3>{editCat ? 'Редактировать категорию' : 'Новая категория'}</h3>
            <label className="label">Название</label>
            <input className="input" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Например: Работа" autoFocus />

            <label className="label" style={{ marginTop: 12 }}>Иконка</label>
            <EmojiPicker selected={formEmoji} onSelect={setFormEmoji} />
            {formEmoji && (
              <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
                Выбрано: {formEmoji}
                <button className="btn-icon" style={{ marginLeft: 4, fontSize: 11 }} onClick={() => setFormEmoji('')}>✕</button>
              </div>
            )}

            <label className="label" style={{ marginTop: 12 }}>Цвет</label>
            <div className="cat-colors">
              {['#6366f1', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ef4444', '#06b6d4'].map((c) => (
                <button key={c} className={`cat-color-btn ${formColor === c ? 'active' : ''}`} style={{ background: c }} onClick={() => setFormColor(c)} />
              ))}
            </div>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving || !formName.trim()}>{saving ? '...' : 'Сохранить'}</button>
            </div>
          </div>
        </div>
      )}

      {deleteCat && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setDeleteCat(null) }}>
          <div className="dialog" onMouseDown={(e) => e.stopPropagation()}>
            <h3>Удалить категорию?</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              Категория «{deleteCat.emoji} {deleteCat.name}» будет удалена.
            </p>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setDeleteCat(null)}>Отмена</button>
              <button className="btn btn-danger" onClick={handleDelete} disabled={saving}>{saving ? '...' : 'Удалить'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
