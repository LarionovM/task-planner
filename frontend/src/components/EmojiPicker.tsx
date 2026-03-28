// Универсальный эмодзи-пикер с категориями, как в Telegram

import { useState } from 'react'

const EMOJI_CATEGORIES: { name: string; icon: string; emojis: string[] }[] = [
  {
    name: 'Частые',
    icon: '🕐',
    emojis: [
      '💼', '📚', '🏋️', '❤️', '🎯', '🎨', '🎮', '📦',
      '🔧', '💰', '📝', '🏠', '🎵', '🍎', '☕', '🌙',
    ],
  },
  {
    name: 'Люди',
    icon: '😀',
    emojis: [
      '😀', '😂', '🥰', '😎', '🤔', '😴', '🤗', '🥳',
      '😤', '🤯', '🧐', '😇', '🤩', '😈', '👻', '💀',
      '👋', '✌️', '👍', '👎', '👏', '🤝', '💪', '🙏',
      '👨‍💻', '👩‍💻', '👨‍🎓', '👩‍🎓', '👨‍🏫', '👩‍⚕️', '👨‍🍳', '🧑‍🔬',
    ],
  },
  {
    name: 'Природа',
    icon: '🌿',
    emojis: [
      '🐶', '🐱', '🐾', '🦊', '🐻', '🐼', '🐸', '🐵',
      '🦁', '🐯', '🐮', '🐷', '🐔', '🐧', '🦅', '🦋',
      '🌸', '🌺', '🌻', '🌹', '🍀', '🌿', '🌴', '🌳',
      '☀️', '🌙', '⭐', '🌈', '☁️', '⛈️', '❄️', '🔥',
    ],
  },
  {
    name: 'Еда',
    icon: '🍔',
    emojis: [
      '🍎', '🍊', '🍋', '🍇', '🍓', '🍑', '🥑', '🥦',
      '🍕', '🍔', '🌮', '🍜', '🍣', '🥗', '🍰', '🍩',
      '☕', '🍵', '🥤', '🍺', '🍷', '🧃', '🍳', '🥐',
    ],
  },
  {
    name: 'Активности',
    icon: '⚽',
    emojis: [
      '⚽', '🏀', '🏈', '🎾', '🏐', '🎱', '🏓', '🏸',
      '🏋️', '🏃', '🧘', '🚴', '🏊', '⛷️', '🤸', '🧗',
      '🎯', '🎲', '🎰', '🎳', '🎮', '🕹️', '🎪', '🎭',
      '🎨', '🎬', '🎤', '🎵', '🎸', '🎹', '🎻', '🥁',
    ],
  },
  {
    name: 'Путешествия',
    icon: '✈️',
    emojis: [
      '🚗', '🚕', '🚌', '🚁', '✈️', '🚀', '🛸', '🚢',
      '🚂', '🏎️', '🚲', '🛴', '🏍️', '⛵', '🚡', '🛩️',
      '🏖️', '🏔️', '🗻', '🌋', '🏕️', '🏰', '🗽', '🗼',
      '🌍', '🌎', '🌏', '🧭', '🗺️', '🏝️', '🎢', '🎡',
    ],
  },
  {
    name: 'Вещи',
    icon: '💡',
    emojis: [
      '📱', '💻', '⌨️', '🖥️', '🖨️', '📷', '🎥', '📺',
      '💡', '🔦', '🔋', '🔌', '📡', '🔬', '🔭', '🧲',
      '💊', '🩺', '🩹', '💉', '🧬', '🧪', '🧫', '🌡️',
      '📚', '📖', '📝', '✏️', '📌', '📎', '📐', '📏',
      '💼', '🎒', '👜', '🛍️', '🎁', '🏆', '🏅', '🎖️',
      '🔧', '🔨', '⚙️', '🛠️', '🔩', '🗝️', '🔐', '🔓',
    ],
  },
  {
    name: 'Символы',
    icon: '❤️',
    emojis: [
      '❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍',
      '💯', '💢', '💥', '💫', '💬', '💭', '🔔', '🔕',
      '✅', '❌', '⭕', '❗', '❓', '⚠️', '🚫', '♻️',
      '⬆️', '➡️', '⬇️', '⬅️', '↔️', '↕️', '🔄', '🔀',
    ],
  },
  {
    name: 'Флаги',
    icon: '🏳️',
    emojis: [
      '🇷🇺', '🇺🇸', '🇬🇧', '🇩🇪', '🇫🇷', '🇪🇸', '🇮🇹', '🇯🇵',
      '🇨🇳', '🇰🇷', '🇧🇷', '🇮🇳', '🇹🇷', '🇦🇺', '🇨🇦', '🇲🇽',
      '🏳️', '🏴', '🚩', '🏁', '🇦🇪', '🇵🇹', '🇳🇱', '🇸🇪',
    ],
  },
]

interface EmojiPickerProps {
  selected: string
  onSelect: (emoji: string) => void
}

export default function EmojiPicker({ selected, onSelect }: EmojiPickerProps) {
  const [activeTab, setActiveTab] = useState(0)

  return (
    <div className="emoji-picker-full">
      <div className="emoji-picker-tabs">
        {EMOJI_CATEGORIES.map((cat, i) => (
          <button
            key={cat.name}
            className={`emoji-picker-tab ${activeTab === i ? 'active' : ''}`}
            onClick={() => setActiveTab(i)}
            title={cat.name}
          >
            {cat.icon}
          </button>
        ))}
      </div>
      <div className="emoji-picker-grid">
        {EMOJI_CATEGORIES[activeTab].emojis.map((emoji) => (
          <button
            key={emoji}
            className={`emoji-btn ${selected === emoji ? 'active' : ''}`}
            onClick={() => onSelect(emoji)}
          >
            {emoji}
          </button>
        ))}
      </div>
    </div>
  )
}
